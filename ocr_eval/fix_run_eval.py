#!/usr/bin/env python3
"""
Fix Plan B — Increase max_output_tokens to 8192
================================================
Root cause confirmed from fix_plan_A.py logs:
  - Every failure is "EOF while parsing" (JSON truncation), NOT schema mismatch
  - Compact JSON cuts at ~char 4050 (indicator 33 of 35)
  - Pretty JSON cuts at line 183 (also ~indicator 23 of 35)
  - GEMINI_VISION_THINKING_LEVEL=low burns ~600 tokens from the 2048 budget
  - Remaining ~1400 tokens ≈ exactly 33 indicators × 40 tokens → truncation

Fix: override GEMINI_VISION_MAX_OUTPUT_TOKENS=8192 for this run.
Uses the original VisionAdapter (no Plan A retry patching needed).

Run (from project root):
    python ocr_eval/fix_plan_B.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Override BEFORE loading .env so pydantic-settings picks it up
os.environ["GEMINI_VISION_MAX_OUTPUT_TOKENS"] = "4096"

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)  # env var above takes precedence

import logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.services.image_processor import ImageProcessor
from src.services.reference_repository import ReferenceRepository

# ── Constants ─────────────────────────────────────────────────────────────────

PNG_DIR     = ROOT / "ocr_eval" / "png_v2"
GOLDEN_FILE = ROOT / "ocr_eval" / "mock_data.json"
FILE_MAP    = {i: f"OCR-GOLDEN-{i:03d}" for i in range(1, 21)}


async def run_one(
    i: int,
    png_path: Path,
    golden: dict,
    processor: ImageProcessor,
    adapter: VisionAdapter,
    repo: ReferenceRepository,
) -> dict:
    report_id = golden["report_id"]
    t0 = time.perf_counter()

    try:
        raw = png_path.read_bytes()
        processed = processor.process(raw, filename=png_path.name)
    except Exception as exc:
        return {
            "report_id": report_id,
            "success": False,
            "error": f"preprocess: {exc}",
            "t_total_ms": (time.perf_counter() - t0) * 1000,
        }

    try:
        drafts = await adapter.extract(processed.bytes, processed.mime_type)
    except Exception as exc:
        return {
            "report_id": report_id,
            "success": False,
            "error": f"ocr: {exc}",
            "t_total_ms": (time.perf_counter() - t0) * 1000,
            "provider": getattr(adapter, "last_provider", "?"),
        }

    t_total_ms = (time.perf_counter() - t0) * 1000

    golden_by_canonical = {ind["analyte_canonical"]: ind for ind in golden["indicators"]}
    matched = 0
    val_ok = 0
    used: set[str] = set()

    for draft in drafts:
        canonical = repo.resolve_analyte(draft.name)
        if canonical is None or canonical not in golden_by_canonical or canonical in used:
            continue
        used.add(canonical)
        matched += 1
        g = golden_by_canonical[canonical]
        denom = abs(g["value_numeric"]) if abs(g["value_numeric"]) > 0.001 else 0.001
        if abs(draft.value - g["value_numeric"]) / denom <= 0.01:
            val_ok += 1

    return {
        "report_id":  report_id,
        "success":    True,
        "n_ocr":      len(drafts),
        "matched":    matched,
        "val_ok":     val_ok,
        "provider":   adapter.last_provider,
        "t_total_ms": t_total_ms,
    }


async def main() -> None:
    print("[fix-plan-b] max_output_tokens overridden →", os.environ["GEMINI_VISION_MAX_OUTPUT_TOKENS"])
    print("[fix-plan-b] Loading golden data …")
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden_data = json.load(f)
    golden_by_id = {r["report_id"]: r for r in golden_data["reports"]}

    processor = ImageProcessor()
    adapter   = VisionAdapter()
    repo      = ReferenceRepository.from_default_files()

    # Confirm the setting was picked up
    print(f"[fix-plan-b] Adapter max_output_tokens = {adapter.settings.gemini_vision_max_output_tokens}")
    print(f"[fix-plan-b] thinking_level = {adapter.settings.gemini_vision_thinking_level}")
    print(f"[fix-plan-b] Running on {PNG_DIR.name} (20 files) …\n")

    results = []
    for i in range(1, 21):
        report_id = FILE_MAP[i]
        png_path  = PNG_DIR / f"test_ocr_{i}.png"
        golden    = golden_by_id.get(report_id)
        if not golden or not png_path.exists():
            print(f"  [{i:02d}] {report_id} — skip (missing)")
            continue

        print(f"  [{i:02d}] {report_id} …", end=" ", flush=True)
        r = await run_one(i, png_path, golden, processor, adapter, repo)
        results.append(r)

        if r["success"]:
            provider_tag = f"[{r['provider']}]" if r.get("provider") != "gemini" else ""
            print(
                f"OK  matched {r['matched']}/35  val {r['val_ok']}/{r['matched']}"
                f"  {r['t_total_ms']:,.0f} ms {provider_tag}"
            )
        else:
            print(f"FAIL: {r.get('error', '')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    ok = [r for r in results if r["success"]]
    fail = [r for r in results if not r["success"]]
    success_rate = len(ok) / len(results) * 100 if results else 0

    print()
    print("=" * 60)
    print("  Fix Plan B — Results (max_output_tokens=4096)")
    print("=" * 60)
    print(f"  Report Success Rate : {len(ok)}/{len(results)} = {success_rate:.1f}%")
    print(f"  Baseline (Plan A)   : 12/20 = 60.0%")
    print(f"  Baseline (original) :  8/20 = 40.0%")

    if ok:
        avg_lat = sum(r["t_total_ms"] for r in ok) / len(ok)
        lats = sorted(r["t_total_ms"] for r in ok)
        p95 = lats[int(len(lats) * 0.95)] if len(lats) >= 2 else lats[-1]
        providers = [r.get("provider", "?") for r in ok]
        print()
        print(f"  Mean latency (success) : {avg_lat:,.0f} ms")
        print(f"  P95 latency (success)  : {p95:,.0f} ms")
        print(f"  Gemini / OpenRouter    : {providers.count('gemini')} / {providers.count('openrouter')}")
        total_matched = sum(r["matched"] for r in ok)
        total_val_ok  = sum(r["val_ok"] for r in ok)
        total_possible = len(ok) * 35
        print(f"  Analyte match rate     : {total_matched}/{total_possible} = {total_matched/total_possible*100:.1f}%")
        print(f"  Value accuracy (match) : {total_val_ok}/{total_matched} = {total_val_ok/total_matched*100:.1f}%" if total_matched else "  N/A")

    if fail:
        print(f"\n  Still failing ({len(fail)}):")
        for r in fail:
            print(f"    {r['report_id']} — {r.get('error', '')[:90]}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
