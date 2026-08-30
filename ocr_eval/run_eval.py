#!/usr/bin/env python3
"""
OCR Evaluation Script — LumiLab v1.0
=====================================
Evaluates the OCR pipeline against 20 PNG test images using mock_data.json
as ground truth. Computes 12 standardised metrics and writes report.md.

Usage (from project root):
    python data_mock/run_eval.py
    python data_mock/run_eval.py --png-dir data_mock/png_v2 --report data_mock/report_v2.md

Output:
    data_mock/report.md  (or the path given by --report)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_MOCK = ROOT / "data_mock"
PNG_DIR = DATA_MOCK / "png"
GOLDEN_FILE = DATA_MOCK / "mock_data.json"
REPORT_FILE = DATA_MOCK / "report.md"

sys.path.insert(0, str(ROOT))

# Force UTF-8 output on Windows consoles that default to cp1258
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.services.image_processor import ImageProcessor, ImageProcessorError
from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.services.reference_repository import ReferenceRepository

# ── Constants ─────────────────────────────────────────────────────────────────

# test_ocr_N.png  →  OCR-GOLDEN-00N
FILE_MAP: dict[int, str] = {i: f"OCR-GOLDEN-{i:03d}" for i in range(1, 21)}

# Value comparison: 1 % relative tolerance
VALUE_REL_TOL = 0.01
VALUE_ABS_EPS = 0.001  # absolute floor for near-zero golden values

# Decimal shift detection: |log10(ocr/golden)| >= threshold → off by >=10x
DECIMAL_SHIFT_THRESHOLD = 0.5

# Dangerous unit swaps — either direction breaks clinical interpretation
DANGEROUS_UNIT_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("g/l",    "g/dl"),
    ("g/dl",   "g/l"),
    ("mmol/l", "mg/dl"),
    ("mg/dl",  "mmol/l"),
    ("10^12/l","10^9/l"),
    ("10^9/l", "10^12/l"),
    ("10^9/l", "10^6/l"),
    ("10^6/l", "10^9/l"),
    ("g/l",    "mg/l"),
    ("mg/l",   "g/l"),
})


# ── Unit normalisation ────────────────────────────────────────────────────────

def normalize_unit(u: str) -> str:
    """Return a canonical lowercase form of a unit string."""
    if not u:
        return ""
    u = u.strip()
    # Unicode Greek mu / micro sign → plain u
    u = u.replace("μ", "u").replace("µ", "u")
    # Multiplication / cross signs (used in 10×9/L etc.)
    u = u.replace("×", "").replace("⨯", "")
    # Unicode superscript digits → ASCII
    _sup = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    u = u.translate(_sup)
    # Remove spaces
    u = u.replace(" ", "")
    return u.lower()


# ── Metric helpers ────────────────────────────────────────────────────────────

def value_correct(ocr: float, golden: float) -> bool:
    denom = abs(golden) if abs(golden) > VALUE_ABS_EPS else VALUE_ABS_EPS
    return abs(ocr - golden) / denom <= VALUE_REL_TOL


def unit_correct(ocr_unit: str, golden_unit: str) -> bool:
    return normalize_unit(ocr_unit) == normalize_unit(golden_unit)


def decimal_shift(ocr: float, golden: float) -> bool:
    if golden == 0 or ocr == 0:
        return False
    try:
        return abs(math.log10(abs(ocr) / abs(golden))) >= DECIMAL_SHIFT_THRESHOLD
    except (ValueError, ZeroDivisionError):
        return False


def dangerous_unit(ocr_unit: str, golden_unit: str) -> bool:
    return (normalize_unit(ocr_unit), normalize_unit(golden_unit)) in DANGEROUS_UNIT_PAIRS


def compute_flag(value: float, ref_type: str, lower, upper) -> str | None:
    """Recompute clinical flag from OCR value + reference range metadata.
    Returns 'N'/'H'/'L' for RI and ONE_SIDED_LIMIT; None for CDL/BAND."""
    if ref_type == "RI":
        if lower is not None and value < lower:
            return "L"
        if upper is not None and value > upper:
            return "H"
        return "N"
    if ref_type == "ONE_SIDED_LIMIT":
        # upper is an exclusive upper limit (<)
        if upper is not None and value >= upper:
            return "H"
        return "N"
    return None  # CDL / BAND — flag not computed this way


# ── Per-report evaluation ─────────────────────────────────────────────────────

async def evaluate_report(
    report_num: int,
    png_path: Path,
    golden: dict,
    processor: ImageProcessor,
    adapter: VisionAdapter,
    repo: ReferenceRepository,
) -> dict:
    """Run OCR on one PNG and compare to golden indicators."""

    report_id = golden["report_id"]
    scenario   = golden["scenario"]

    golden_by_canonical: dict[str, dict] = {
        ind["analyte_canonical"]: ind for ind in golden["indicators"]
    }
    n_golden = len(golden["indicators"])

    t0 = time.perf_counter()

    # ── Pre-process ──────────────────────────────────────────────────────────
    try:
        raw = png_path.read_bytes()
        t_pre = time.perf_counter()
        processed = processor.process(raw, filename=png_path.name)
        t_preprocess_ms = (time.perf_counter() - t_pre) * 1000
    except Exception as exc:
        return {
            "report_id": report_id, "report_num": report_num,
            "scenario": scenario, "success": False,
            "error": f"Preprocess failed: {exc}",
            "t_total_ms": (time.perf_counter() - t0) * 1000,
        }

    # ── OCR ──────────────────────────────────────────────────────────────────
    try:
        t_ocr = time.perf_counter()
        drafts = await adapter.extract(processed.bytes, processed.mime_type)
        t_ocr_ms = (time.perf_counter() - t_ocr) * 1000
    except Exception as exc:
        return {
            "report_id": report_id, "report_num": report_num,
            "scenario": scenario, "success": False,
            "error": f"OCR failed: {exc}",
            "t_preprocess_ms": t_preprocess_ms,
            "t_total_ms": (time.perf_counter() - t0) * 1000,
        }

    t_total_ms = (time.perf_counter() - t0) * 1000

    # ── Match OCR rows → golden rows ─────────────────────────────────────────
    matched:  list[dict] = []
    phantoms: list[dict] = []
    used: set[str] = set()

    for draft in drafts:
        canonical = repo.resolve_analyte(draft.name)

        if canonical is None or canonical not in golden_by_canonical:
            phantoms.append({
                "ocr_name": draft.name, "canonical": canonical,
                "value": draft.value, "unit": draft.unit,
                "confidence": draft.confidence, "note": "unresolved/phantom",
            })
            continue

        if canonical in used:
            phantoms.append({
                "ocr_name": draft.name, "canonical": canonical,
                "value": draft.value, "unit": draft.unit,
                "confidence": draft.confidence, "note": "duplicate row",
            })
            continue

        used.add(canonical)
        g = golden_by_canonical[canonical]

        ocr_v  = draft.value
        gold_v = g["value_numeric"]
        ocr_u  = draft.unit
        gold_u = g["unit_canonical"]
        ref_t  = g.get("reference_type", "RI")
        gold_f = g.get("flag")

        val_ok  = value_correct(ocr_v, gold_v)
        unit_ok = unit_correct(ocr_u, gold_u)
        complete = val_ok and unit_ok

        dec_err  = decimal_shift(ocr_v, gold_v) and not val_ok
        dang_err = dangerous_unit(ocr_u, gold_u) and not unit_ok

        computed_flag = compute_flag(ocr_v, ref_t,
                                     g.get("reference_lower"),
                                     g.get("reference_upper"))
        ref_ok = None
        if computed_flag is not None and gold_f in ("N", "H", "L"):
            ref_ok = (computed_flag == gold_f)

        matched.append({
            "analyte_canonical": canonical,
            "analyte_id":        g["analyte_id"],
            "ocr_name":          draft.name,
            "ocr_value":         ocr_v,
            "ocr_unit":          ocr_u,
            "golden_value":      gold_v,
            "golden_unit":       gold_u,
            "golden_flag":       gold_f,
            "confidence":        draft.confidence,
            "val_correct":       val_ok,
            "unit_correct":      unit_ok,
            "complete":          complete,
            "decimal_error":     dec_err,
            "dangerous_unit":    dang_err,
            "ref_range_correct": ref_ok,
            "ref_type":          ref_t,
        })

    missing = sorted(set(golden_by_canonical) - used)

    return {
        "report_id":       report_id,
        "report_num":      report_num,
        "scenario":        scenario,
        "success":         True,
        "t_preprocess_ms": t_preprocess_ms,
        "t_ocr_ms":        t_ocr_ms,
        "t_total_ms":      t_total_ms,
        "n_golden":        n_golden,
        "n_ocr":           len(drafts),
        "n_matched":       len(matched),
        "n_phantom":       len(phantoms),
        "n_missing":       len(missing),
        "matched":         matched,
        "phantoms":        phantoms,
        "missing":         missing,
    }


# ── Aggregate metrics ─────────────────────────────────────────────────────────

def aggregate(results: list[dict]) -> dict:
    """Compute the 12 evaluation metrics from per-report results."""

    ok = [r for r in results if r.get("success")]
    n_total = len(results)
    n_ok    = len(ok)

    if not ok:
        return {"error": "No successful reports to aggregate"}

    all_pairs:    list[dict] = []
    all_ref_pairs: list[dict] = []

    total_golden = total_ocr = total_matched = total_phantom = 0
    latencies: list[float] = []

    for r in ok:
        total_golden  += r["n_golden"]
        total_ocr     += r["n_ocr"]
        total_matched += r["n_matched"]
        total_phantom += r["n_phantom"]
        latencies.append(r["t_total_ms"])
        for p in r["matched"]:
            all_pairs.append(p)
            if p["ref_range_correct"] is not None:
                all_ref_pairs.append(p)

    N = len(all_pairs)
    N_ref = len(all_ref_pairs)

    # ── 1. Analyte Precision ─────────────────────────────────────────────────
    # Of all rows OCR returned, what fraction matched a golden analyte?
    analyte_precision = total_matched / total_ocr if total_ocr else 0.0

    # ── 2. Analyte Recall ────────────────────────────────────────────────────
    # Of all 35×n_ok golden analytes, what fraction did OCR find?
    analyte_recall = total_matched / total_golden if total_golden else 0.0

    # ── 3. Analyte F1 ────────────────────────────────────────────────────────
    denom = analyte_precision + analyte_recall
    analyte_f1 = 2 * analyte_precision * analyte_recall / denom if denom else 0.0

    # ── 4. Value Accuracy ────────────────────────────────────────────────────
    n_val_ok = sum(1 for p in all_pairs if p["val_correct"])
    value_accuracy = n_val_ok / N if N else 0.0

    # ── 5. Unit Accuracy ─────────────────────────────────────────────────────
    n_unit_ok = sum(1 for p in all_pairs if p["unit_correct"])
    unit_accuracy = n_unit_ok / N if N else 0.0

    # ── 6. Reference Range Accuracy ──────────────────────────────────────────
    n_ref_ok = sum(1 for p in all_ref_pairs if p["ref_range_correct"])
    ref_range_accuracy = n_ref_ok / N_ref if N_ref else 0.0

    # ── 7. Complete Record Accuracy ──────────────────────────────────────────
    # Row fully correct: analyte matched + value within tol + unit exact
    n_complete = sum(1 for p in all_pairs if p["complete"])
    complete_record_accuracy = n_complete / N if N else 0.0

    # ── 8. Critical OCR Error Rate ───────────────────────────────────────────
    # Decimal shift (10×) OR dangerous unit swap — both are P0 errors
    n_critical = sum(1 for p in all_pairs if p["decimal_error"] or p["dangerous_unit"])
    critical_error_rate = n_critical / N if N else 0.0

    # ── 9. False Positive Analyte Rate ───────────────────────────────────────
    # Phantom rows / total OCR rows
    fp_analyte_rate = total_phantom / total_ocr if total_ocr else 0.0

    # ── 10. Report Success Rate ──────────────────────────────────────────────
    report_success_rate = n_ok / n_total

    # ── 11. Mean Latency ─────────────────────────────────────────────────────
    mean_latency_ms = sum(latencies) / len(latencies)

    # ── 12. P95 Latency ──────────────────────────────────────────────────────
    sorted_lat = sorted(latencies)
    idx = max(0, math.ceil(0.95 * len(sorted_lat)) - 1)
    p95_latency_ms = sorted_lat[idx]

    return {
        # 12 headline metrics
        "analyte_precision":       analyte_precision,
        "analyte_recall":          analyte_recall,
        "analyte_f1":              analyte_f1,
        "value_accuracy":          value_accuracy,
        "unit_accuracy":           unit_accuracy,
        "ref_range_accuracy":      ref_range_accuracy,
        "complete_record_accuracy":complete_record_accuracy,
        "critical_error_rate":     critical_error_rate,
        "fp_analyte_rate":         fp_analyte_rate,
        "report_success_rate":     report_success_rate,
        "mean_latency_ms":         mean_latency_ms,
        "p95_latency_ms":          p95_latency_ms,
        # Raw counts (used in report)
        "n_total":          n_total,
        "n_ok":             n_ok,
        "total_golden":     total_golden,
        "total_ocr":        total_ocr,
        "total_matched":    total_matched,
        "total_phantom":    total_phantom,
        "N":                N,
        "N_ref":            N_ref,
        "n_val_ok":         n_val_ok,
        "n_unit_ok":        n_unit_ok,
        "n_ref_ok":         n_ref_ok,
        "n_complete":       n_complete,
        "n_critical":       n_critical,
        "latencies":        latencies,
        "all_pairs":        all_pairs,
    }


# ── Report generation ─────────────────────────────────────────────────────────

def pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:.{digits}f}%"

def ms(v: float) -> str:
    return f"{v:,.0f} ms"

def status(v: float, good_ge: float, warn_ge: float, lower_is_better: bool = False) -> str:
    if lower_is_better:
        if v <= good_ge:   return "✅ PASS"
        if v <= warn_ge:   return "⚠️ WARN"
        return "❌ FAIL"
    if v >= good_ge:   return "✅ PASS"
    if v >= warn_ge:   return "⚠️ WARN"
    return "❌ FAIL"


def generate_report(m: dict, results: list[dict], run_ts: str) -> str:
    """Build the full report.md content string."""

    failed = [r for r in results if not r.get("success")]
    ok     = [r for r in results if r.get("success")]

    # ── Collect critical errors for error log ────────────────────────────────
    critical_errors: list[dict] = []
    for r in ok:
        for p in r["matched"]:
            if p["decimal_error"] or p["dangerous_unit"]:
                critical_errors.append({
                    "report_id": r["report_id"],
                    "scenario":  r["scenario"],
                    **p,
                })

    # ── Confidence calibration buckets ───────────────────────────────────────
    buckets = {
        "[0.0–0.5)": {"total": 0, "val_ok": 0},
        "[0.5–0.7)": {"total": 0, "val_ok": 0},
        "[0.7–0.9)": {"total": 0, "val_ok": 0},
        "[0.9–1.0]": {"total": 0, "val_ok": 0},
    }
    for p in m.get("all_pairs", []):
        c = p["confidence"]
        if   c < 0.5: k = "[0.0–0.5)"
        elif c < 0.7: k = "[0.5–0.7)"
        elif c < 0.9: k = "[0.7–0.9)"
        else:         k = "[0.9–1.0]"
        buckets[k]["total"] += 1
        if p["val_correct"]:
            buckets[k]["val_ok"] += 1

    lines: list[str] = []
    a = lines.append

    # ─────────────────────────────────────────────────────────────────────────
    a("# OCR Evaluation Report — LumiLab")
    a("")
    a(f"**Run timestamp:** {run_ts}  ")
    a(f"**Test images:** `data_mock/png/` (20 PNG files)  ")
    a(f"**Ground truth:** `data_mock/mock_data.json`  ")
    a(f"**OCR engine:** Gemini Vision (primary) / OpenRouter (fallback)  ")
    a(f"**Value tolerance:** ±{int(VALUE_REL_TOL*100)}% relative  ")
    a("")
    a("---")
    a("")

    # ── 1. Executive Summary ─────────────────────────────────────────────────
    a("## 1. Executive Summary")
    a("")
    a("| # | Metric | Value | Threshold | Status |")
    a("|---|--------|-------|-----------|--------|")
    a(f"| 1 | **Analyte Precision** | {pct(m['analyte_precision'])} | ≥ 90% | {status(m['analyte_precision'], 0.90, 0.80)} |")
    a(f"| 2 | **Analyte Recall** | {pct(m['analyte_recall'])} | ≥ 85% | {status(m['analyte_recall'], 0.85, 0.75)} |")
    a(f"| 3 | **Analyte F1-score** | {pct(m['analyte_f1'])} | ≥ 87% | {status(m['analyte_f1'], 0.87, 0.78)} |")
    a(f"| 4 | **Value Accuracy** | {pct(m['value_accuracy'])} | ≥ 90% | {status(m['value_accuracy'], 0.90, 0.80)} |")
    a(f"| 5 | **Unit Accuracy** | {pct(m['unit_accuracy'])} | ≥ 95% | {status(m['unit_accuracy'], 0.95, 0.88)} |")
    a(f"| 6 | **Reference Range Accuracy** | {pct(m['ref_range_accuracy'])} | ≥ 90% | {status(m['ref_range_accuracy'], 0.90, 0.80)} |")
    a(f"| 7 | **Complete Record Accuracy** | {pct(m['complete_record_accuracy'])} | ≥ 80% | {status(m['complete_record_accuracy'], 0.80, 0.70)} |")
    a(f"| 8 | **Critical OCR Error Rate** | {pct(m['critical_error_rate'])} | = 0% | {status(m['critical_error_rate'], 0.0, 0.01, lower_is_better=True)} |")
    a(f"| 9 | **False Positive Analyte Rate** | {pct(m['fp_analyte_rate'])} | ≤ 5% | {status(m['fp_analyte_rate'], 0.0, 0.05, lower_is_better=True)} |")
    a(f"| 10 | **Report Success Rate** | {pct(m['report_success_rate'])} | ≥ 95% | {status(m['report_success_rate'], 0.95, 0.85)} |")
    a(f"| 11 | **Mean Latency** | {ms(m['mean_latency_ms'])} | ≤ 10 000 ms | {status(m['mean_latency_ms'], 10000, 15000, lower_is_better=True)} |")
    a(f"| 12 | **P95 Latency** | {ms(m['p95_latency_ms'])} | ≤ 15 000 ms | {status(m['p95_latency_ms'], 15000, 20000, lower_is_better=True)} |")
    a("")

    n_pass = sum(1 for x in [
        m['analyte_precision'] >= 0.90,
        m['analyte_recall']    >= 0.85,
        m['analyte_f1']        >= 0.87,
        m['value_accuracy']    >= 0.90,
        m['unit_accuracy']     >= 0.95,
        m['ref_range_accuracy']>= 0.90,
        m['complete_record_accuracy'] >= 0.80,
        m['critical_error_rate'] == 0.0,
        m['fp_analyte_rate']   <= 0.05,
        m['report_success_rate'] >= 0.95,
        m['mean_latency_ms']   <= 10000,
        m['p95_latency_ms']    <= 15000,
    ] if x)
    a(f"> **Overall: {n_pass}/12 metrics passed their target threshold.**")
    a("")
    a("---")
    a("")

    # ── 2. Metric Definitions ────────────────────────────────────────────────
    a("## 2. Metric Definitions & Computation")
    a("")
    a("All metrics are computed across the **matched indicator pairs** (OCR row that successfully")
    a("resolved to a supported canonical analyte present in the golden dataset).")
    a("")
    a("| # | Metric | Formula | Notes |")
    a("|---|--------|---------|-------|")
    a("| 1 | Analyte Precision | matched / total_ocr_rows | Of all rows OCR returned, how many mapped to a known golden analyte |")
    a("| 2 | Analyte Recall | matched / 35 per report | Of all 35 golden analytes, how many did OCR detect |")
    a("| 3 | Analyte F1 | 2·P·R / (P+R) | Harmonic mean of Precision and Recall |")
    a("| 4 | Value Accuracy | val_ok_rows / matched | OCR value within ±1 % of golden value_numeric |")
    a("| 5 | Unit Accuracy | unit_ok_rows / matched | normalize(OCR.unit) == golden.unit_canonical |")
    a("| 6 | Reference Range Accuracy | flag_ok / RI_ONE_SIDED_rows | Recomputed flag from OCR value matches golden flag (RI + ONE_SIDED_LIMIT only) |")
    a("| 7 | Complete Record Accuracy | complete_rows / matched | Name matched **AND** value OK **AND** unit OK |")
    a("| 8 | Critical OCR Error Rate | critical_rows / matched | Decimal shift (≥10×) OR dangerous unit swap (g/L↔g/dL, mmol/L↔mg/dL, …) |")
    a("| 9 | False Positive Analyte Rate | phantom_rows / total_ocr_rows | OCR hallucinated a row not in the golden analyte set |")
    a("| 10 | Report Success Rate | successful_api_calls / 20 | API returned parseable structured output |")
    a("| 11 | Mean Latency | mean(t_total_ms) | End-to-end: preprocess + OCR per report |")
    a("| 12 | P95 Latency | 95th_pct(t_total_ms) | Tail latency; target ≤ 15 000 ms |")
    a("")
    a("---")
    a("")

    # ── 3. Detailed Results ───────────────────────────────────────────────────
    a("## 3. Detailed Results")
    a("")

    a("### 3.1 Analyte Detection (Metrics 1–3)")
    a("")
    a(f"- Total golden analyte slots: **{m['total_golden']}** ({m['n_ok']} reports × 35 indicators)")
    a(f"- Total OCR rows returned:    **{m['total_ocr']}**")
    a(f"- Successfully matched rows:  **{m['total_matched']}**")
    a(f"- Phantom (unresolved) rows:  **{m['total_phantom']}**")
    a(f"- Missing (not found by OCR): **{m['total_golden'] - m['total_matched']}**")
    a("")
    a(f"| Metric | Value |")
    a(f"|--------|-------|")
    a(f"| Analyte Precision | {pct(m['analyte_precision'], 2)} ({m['total_matched']}/{m['total_ocr']}) |")
    a(f"| Analyte Recall    | {pct(m['analyte_recall'],    2)} ({m['total_matched']}/{m['total_golden']}) |")
    a(f"| Analyte F1-score  | {pct(m['analyte_f1'],        2)} |")
    a("")

    a("### 3.2 Value Accuracy (Metric 4)")
    a("")
    a(f"- Tolerance: ±1 % relative (absolute floor {VALUE_ABS_EPS})")
    a(f"- Correct:   **{m['n_val_ok']} / {m['N']}** matched rows  →  {pct(m['value_accuracy'], 2)}")
    a(f"- Incorrect: **{m['N'] - m['n_val_ok']}** rows")
    a("")

    a("### 3.3 Unit Accuracy (Metric 5)")
    a("")
    a(f"- Correct:   **{m['n_unit_ok']} / {m['N']}**  →  {pct(m['unit_accuracy'], 2)}")
    a(f"- Incorrect: **{m['N'] - m['n_unit_ok']}** rows")
    a("")

    a("### 3.4 Reference Range Accuracy (Metric 6)")
    a("")
    a(f"- Applicable rows (RI + ONE_SIDED_LIMIT): **{m['N_ref']}**")
    a(f"- Correct flag:   **{m['n_ref_ok']} / {m['N_ref']}**  →  {pct(m['ref_range_accuracy'], 2)}")
    a(f"- Incorrect flag: **{m['N_ref'] - m['n_ref_ok']}** rows")
    a("")

    a("### 3.5 Complete Record Accuracy (Metric 7)")
    a("")
    a(f"- Complete (name matched + value OK + unit OK): **{m['n_complete']} / {m['N']}**  →  {pct(m['complete_record_accuracy'], 2)}")
    a("")

    a("### 3.6 Critical OCR Error Rate (Metric 8)")
    a("")
    a("Critical errors are **decimal shifts** (OCR value is ≥10× off: e.g. 1.7 read as 17) "
      "or **dangerous unit swaps** (g/L↔g/dL, mmol/L↔mg/dL, 10⁹/L↔10¹²/L) that would change clinical interpretation.")
    a("")
    a(f"- Critical errors found: **{m['n_critical']}** / {m['N']} matched rows  →  {pct(m['critical_error_rate'], 2)}")
    a("")

    if critical_errors:
        a("**Critical error log:**")
        a("")
        a("| Report | Scenario | Analyte | OCR value | Golden value | OCR unit | Golden unit | Error type |")
        a("|--------|----------|---------|-----------|--------------|----------|-------------|------------|")
        for e in critical_errors:
            err_type = []
            if e["decimal_error"]:  err_type.append("decimal shift")
            if e["dangerous_unit"]: err_type.append("dangerous unit")
            a(f"| {e['report_id']} | {e['scenario']} | {e['analyte_canonical']} "
              f"| {e['ocr_value']} | {e['golden_value']} "
              f"| {e['ocr_unit']} | {e['golden_unit']} "
              f"| {', '.join(err_type)} |")
        a("")
    else:
        a("> ✅ No critical errors detected.")
        a("")

    a("### 3.7 False Positive Analyte Rate (Metric 9)")
    a("")
    a(f"- Phantom rows (OCR hallucinated / unresolvable): **{m['total_phantom']}** / {m['total_ocr']}  →  {pct(m['fp_analyte_rate'], 2)}")
    a("")

    a("### 3.8 Confidence Calibration")
    a("")
    a("Value accuracy broken down by OCR self-reported confidence bucket:")
    a("")
    a("| Confidence bucket | OCR rows | Value-correct rows | Accuracy |")
    a("|-------------------|---------|--------------------|----------|")
    for bk, bv in buckets.items():
        acc = pct(bv["val_ok"] / bv["total"]) if bv["total"] else "—"
        a(f"| {bk} | {bv['total']} | {bv['val_ok']} | {acc} |")
    a("")
    a("> A well-calibrated model shows monotonically increasing accuracy as confidence rises.")
    a("")
    a("---")
    a("")

    # ── 4. Per-Report Breakdown ───────────────────────────────────────────────
    a("## 4. Per-Report Breakdown")
    a("")
    a("| Report | Scenario | OCR rows | Matched | Phantom | Missing | Val OK | Unit OK | Complete | Total (ms) |")
    a("|--------|----------|----------|---------|---------|---------|--------|---------|----------|------------|")
    for r in results:
        if not r.get("success"):
            a(f"| {r['report_id']} | {r['scenario']} | — | — | — | — | — | — | — | ❌ {r.get('error', '')[:40]} |")
            continue
        n_m = r["n_matched"]
        n_v = sum(1 for p in r["matched"] if p["val_correct"])
        n_u = sum(1 for p in r["matched"] if p["unit_correct"])
        n_c = sum(1 for p in r["matched"] if p["complete"])
        a(f"| {r['report_id']} | {r['scenario'][:30]} "
          f"| {r['n_ocr']} | {n_m} | {r['n_phantom']} | {r['n_missing']} "
          f"| {n_v}/{n_m} | {n_u}/{n_m} | {n_c}/{n_m} "
          f"| {r['t_total_ms']:,.0f} |")
    a("")
    a("---")
    a("")

    # ── 5. Latency Profile ────────────────────────────────────────────────────
    a("## 5. Latency Profile (Metrics 11–12)")
    a("")
    lats = sorted(m["latencies"])
    if lats:
        p50_idx = max(0, math.ceil(0.50 * len(lats)) - 1)
        p95_idx = max(0, math.ceil(0.95 * len(lats)) - 1)
        p99_idx = max(0, math.ceil(0.99 * len(lats)) - 1)
        a(f"| Percentile | Latency |")
        a(f"|------------|---------|")
        a(f"| Min        | {ms(min(lats))} |")
        a(f"| P50        | {ms(lats[p50_idx])} |")
        a(f"| P95        | {ms(lats[p95_idx])} |")
        a(f"| P99        | {ms(lats[p99_idx])} |")
        a(f"| Max        | {ms(max(lats))} |")
        a(f"| Mean       | {ms(m['mean_latency_ms'])} |")
    a("")

    # per-report latency table
    a("**Per-report latency breakdown:**")
    a("")
    a("| Report | Preprocess (ms) | OCR API (ms) | Total (ms) |")
    a("|--------|----------------|--------------|------------|")
    for r in results:
        if not r.get("success"):
            a(f"| {r['report_id']} | — | — | ❌ |")
        else:
            a(f"| {r['report_id']} | {r['t_preprocess_ms']:,.0f} | {r['t_ocr_ms']:,.0f} | {r['t_total_ms']:,.0f} |")
    a("")
    a("---")
    a("")

    # ── 6. Failure Log ────────────────────────────────────────────────────────
    if failed:
        a("## 6. Failed Reports")
        a("")
        a("| Report | Scenario | Error |")
        a("|--------|----------|-------|")
        for r in failed:
            a(f"| {r['report_id']} | {r['scenario']} | {r.get('error', 'unknown')} |")
        a("")
        a("---")
        a("")

    # ── 7. Recommendations ────────────────────────────────────────────────────
    a("## 7. Recommendations")
    a("")
    recs: list[str] = []

    if m["report_success_rate"] < 0.95:
        n_fail = m["n_total"] - m["n_ok"]
        recs.append(
            f"**[P0] Report Success Rate = {pct(m['report_success_rate'])} ({n_fail}/{m['n_total']} phiếu thất bại)** — "
            "Gemini trả về response không khớp schema `_GeminiOCRPayload`. Nguyên nhân thường gặp: "
            "(a) model trả `null` hoặc string thay vì float cho trường `value`; "
            "(b) model trả thinking tokens trước JSON làm hỏng parse; "
            "(c) rate-limit trả HTML error page thay vì JSON. "
            "Hành động: bật DEBUG logging trong `vision_adapter.py` để in `response.text` raw khi schema fail, "
            "xác định pattern, sau đó thêm fallback parse hoặc kích hoạt OpenRouter fallback khi schema không hợp lệ."
        )

    if m["analyte_recall"] < 0.85:
        recs.append("**Recall thấp** — OCR bỏ sót nhiều chỉ số. Kiểm tra layout recognition: bảng nhiều cột, chữ quá nhỏ (< 8pt sau resize), hoặc deskew chưa đủ. Cân nhắc nâng max_edge từ 2048→4096px hoặc tăng JPEG quality.")
    if m["analyte_precision"] < 0.90:
        recs.append("**Precision thấp** — OCR trả về nhiều phantom row (hallucination hoặc đọc nhầm footer/header thành chỉ số). Cần tăng cường system prompt với ví dụ negative.")
    if m["value_accuracy"] < 0.90:
        recs.append("**Value Accuracy thấp** — Nhiều giá trị số đọc sai. Phân tích xem lỗi chủ yếu là digit substitution (3↔8, 1↔7) hay decimal shift. Nếu là digit: cân nhắc tăng resolution. Nếu là decimal: xem xét post-processing rule dựa trên expected range.")
    if m["unit_accuracy"] < 0.95:
        recs.append("**Unit Accuracy thấp** — Thêm unit normalisation layer ở server-side trước khi so sánh, hoặc chuẩn hoá alias trong system prompt.")
    if m["critical_error_rate"] > 0.0:
        recs.append(f"**Critical errors: {m['n_critical']} trường hợp** (decimal shift hoặc dangerous unit) — ĐÂY LÀ P0. Cần immediate fix: thêm post-OCR sanity check dựa vào expected value range của từng chỉ số.")
    if m["fp_analyte_rate"] > 0.05:
        recs.append("**False Positive Rate cao** — Nhiều phantom row. Tăng độ nghiêm của EXTRACTION_SYSTEM_PROMPT: chỉ đọc dòng trong bảng chỉ số, bỏ qua header, footer, khoảng tham chiếu.")
    if m["ref_range_accuracy"] < 0.90:
        recs.append("**Reference Range Accuracy thấp** — Flag sai do value sai. Xử lý theo gốc rễ (cải thiện Value Accuracy) thay vì patch flag logic.")
    if m["p95_latency_ms"] > 15000:
        recs.append(f"**P95 Latency = {ms(m['p95_latency_ms'])} vượt ngưỡng 15 000 ms** — Kiểm tra retry pattern, backoff delay, và image size. Cân nhắc aggressive resize trước khi gửi API.")
    if not recs:
        recs.append("Tất cả metric đạt hoặc vượt threshold. Duy trì monitoring định kỳ với test set mới.")

    for i, r in enumerate(recs, 1):
        a(f"{i}. {r}")
        a("")

    a("---")
    a("")
    a("*Report generated by `data_mock/run_eval.py`. Do not edit manually — re-run the script to refresh.*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="LumiLab OCR Evaluation")
    parser.add_argument("--png-dir", default=str(PNG_DIR),
                        help="Directory containing test_ocr_N.png files")
    parser.add_argument("--report", default=str(REPORT_FILE),
                        help="Output report.md path")
    args = parser.parse_args()

    png_dir     = Path(args.png_dir)
    report_file = Path(args.report)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[eval] Started at {run_ts}")
    print(f"[eval] Golden file : {GOLDEN_FILE}")
    print(f"[eval] PNG dir     : {png_dir}")
    print(f"[eval] Report out  : {report_file}")
    print()

    # Load golden data
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden_data = json.load(f)

    golden_by_id: dict[str, dict] = {
        r["report_id"]: r for r in golden_data["reports"]
    }

    # Init shared objects
    processor = ImageProcessor()
    adapter   = VisionAdapter()
    repo      = ReferenceRepository.from_default_files()

    results: list[dict] = []

    for i in range(1, 21):
        report_id = FILE_MAP[i]
        png_path  = png_dir / f"test_ocr_{i}.png"
        golden    = golden_by_id.get(report_id)

        if golden is None:
            print(f"  [{i:02d}/20] {report_id} — ⚠ not found in golden data, skip")
            continue
        if not png_path.exists():
            print(f"  [{i:02d}/20] {report_id} — ⚠ PNG not found: {png_path.name}, skip")
            continue

        print(f"  [{i:02d}/20] {report_id} ({golden['scenario']}) ...", end=" ", flush=True)
        result = await evaluate_report(i, png_path, golden, processor, adapter, repo)
        results.append(result)

        if result["success"]:
            print(
                f"matched {result['n_matched']}/35 | "
                f"val {sum(p['val_correct'] for p in result['matched'])}/{result['n_matched']} | "
                f"{result['t_total_ms']:,.0f} ms"
            )
        else:
            print(f"FAIL: {result.get('error', '')}")

    print()
    print("[eval] Computing aggregate metrics …")
    m = aggregate(results)

    if "error" in m:
        print(f"[eval] ❌ {m['error']}")
        return

    print(f"[eval] Analyte Precision : {pct(m['analyte_precision'])}")
    print(f"[eval] Analyte Recall    : {pct(m['analyte_recall'])}")
    print(f"[eval] Analyte F1        : {pct(m['analyte_f1'])}")
    print(f"[eval] Value Accuracy    : {pct(m['value_accuracy'])}")
    print(f"[eval] Unit Accuracy     : {pct(m['unit_accuracy'])}")
    print(f"[eval] Ref Range Acc     : {pct(m['ref_range_accuracy'])}")
    print(f"[eval] Complete Record   : {pct(m['complete_record_accuracy'])}")
    print(f"[eval] Critical Errors   : {pct(m['critical_error_rate'])}")
    print(f"[eval] FP Analyte Rate   : {pct(m['fp_analyte_rate'])}")
    print(f"[eval] Report Success    : {pct(m['report_success_rate'])}")
    print(f"[eval] Mean Latency      : {ms(m['mean_latency_ms'])}")
    print(f"[eval] P95 Latency       : {ms(m['p95_latency_ms'])}")
    print()

    print(f"[eval] Writing report → {report_file}")
    report_md = generate_report(m, results, run_ts)
    report_file.write_text(report_md, encoding="utf-8")
    print(f"[eval] Done. Report: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())
