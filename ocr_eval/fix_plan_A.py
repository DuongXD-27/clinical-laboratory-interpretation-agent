#!/usr/bin/env python3
"""
Fix Plan A — Schema failure treated as retryable + OpenRouter fallback
======================================================================
Subclasses VisionAdapter to patch _extract_gemini():
  - Schema ValidationError → retry once (with 0.5s backoff)
  - Schema fail on both attempts → fall through to OpenRouter fallback
  - Adds WARNING log with response.text preview for diagnosis

Run (from project root):
    python ocr_eval/fix_plan_A.py

Compares result against original 40% Report Success Rate (v1/v2 baseline).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fix_plan_a")

import asyncio as _asyncio

from pydantic import ValidationError
from src.adapters.vision_adapter import (
    VisionAdapter,
    VisionAdapterError,
    _GeminiOCRPayload,
    _is_transient,
    _status_code,
)
from src.models.ocr_schemas import OCRIndicatorDraft
from src.services.image_processor import ImageProcessor, ImageProcessorError
from src.services.reference_repository import ReferenceRepository
from src.services.request_timing import timing_span, add_timing_event
from google.genai import types


# ── Patched adapter ────────────────────────────────────────────────────────────

class FixedVisionAdapter(VisionAdapter):
    """
    Plan A patch: treat schema ValidationError as a retryable failure.

    Original behaviour (dòng 276-279 vision_adapter.py):
        schema fail → raise VisionAdapterError immediately (no retry, no fallback)

    Fixed behaviour:
        schema fail attempt 1 → log warning + retry with 0.5s sleep
        schema fail attempt 2 → log warning + fall through to OpenRouter fallback
    """

    # Counters for reporting
    schema_fail_count:   int = 0
    schema_retry_ok:     int = 0   # recovered on 2nd attempt
    schema_fallback_cnt: int = 0   # fell through to OpenRouter

    async def _extract_gemini(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> list[OCRIndicatorDraft]:
        config = types.GenerateContentConfig(
            system_instruction=self._get_system_prompt(),
            temperature=0,
            max_output_tokens=self.settings.gemini_vision_max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=_GeminiOCRPayload.model_json_schema(),
            thinking_config=types.ThinkingConfig(
                thinking_level=self.settings.gemini_vision_thinking_level
            ),
        )
        contents = [
            self._get_user_prompt(),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ]

        last_transient: BaseException | None = None
        for attempt in range(1, 3):
            started_at = time.perf_counter()
            try:
                response = await _asyncio.wait_for(
                    self._gemini_client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self.settings.gemini_vision_timeout_seconds,
                )
            except Exception as exc:
                transient = _is_transient(exc)
                duration_ms = (time.perf_counter() - started_at) * 1000
                self._record_attempt(
                    "gemini", self.model, attempt,
                    "transient_error" if transient else "error", duration_ms,
                )
                if not transient:
                    raise VisionAdapterError(
                        f"Gemini OCR bi tu choi hoac loi cau hinh (HTTP {_status_code(exc) or 'unknown'})."
                    ) from exc
                last_transient = exc
                if attempt == 1:
                    delay = 0.5 + self._jitter(0.0, 0.25)
                    await self._sleep(delay)
                    continue
                break

            duration_ms = (time.perf_counter() - started_at) * 1000
            self._record_attempt("gemini", self.model, attempt, "response", duration_ms)

            try:
                with timing_span("vision-parse"):
                    payload = _GeminiOCRPayload.model_validate_json(response.text or "")
                    drafts = [OCRIndicatorDraft(**item.model_dump()) for item in payload.indicators]

            except (ValidationError, TypeError, ValueError) as exc:
                # ── PLAN A FIX ────────────────────────────────────────────────
                # Original: raise VisionAdapterError immediately.
                # Fixed:    treat as retryable; fallback to OpenRouter after
                #           both attempts fail.
                FixedVisionAdapter.schema_fail_count += 1
                txt = response.text or ""
                preview = txt[:400]
                tail = txt[-200:] if len(txt) > 200 else ""
                logger.warning(
                    "[Plan-A] schema_fail attempt=%d exc_type=%s err=%s preview=%r tail=%r",
                    attempt, type(exc).__name__, str(exc)[:300], preview, tail,
                )
                self._record_attempt(
                    "gemini", self.model, attempt, "schema_fail", duration_ms
                )
                last_transient = exc          # mark as transient so fallback runs
                if attempt == 1:
                    await self._sleep(0.5 + self._jitter(0.0, 0.25))
                    continue
                break                         # fall through to OpenRouter fallback
                # ── END FIX ───────────────────────────────────────────────────

            if attempt == 2 and isinstance(last_transient, (ValidationError, TypeError, ValueError)):
                FixedVisionAdapter.schema_retry_ok += 1

            self.last_provider = "gemini"
            self.last_model = self.model
            return drafts

        if self.fallback_enabled and self.settings.openrouter_api_key.strip():
            if isinstance(last_transient, (ValidationError, TypeError, ValueError)):
                FixedVisionAdapter.schema_fallback_cnt += 1
                logger.warning(
                    "[Plan-A] schema_fail_fallback → openrouter after 2 gemini attempts"
                )
            add_timing_event(
                "vision-fallback", 0.0,
                from_provider="gemini", to_provider="openrouter",
                reason="schema_fail_exhausted",
            )
            return await self._extract_openrouter(image_bytes, mime_type)

        raise VisionAdapterError(
            "Gemini OCR schema fail, openrouter not configured."
        ) from last_transient

    # ── Helpers to avoid importing EXTRACTION_* constants directly ────────────

    @staticmethod
    def _get_system_prompt() -> str:
        from src.adapters.vision_adapter import EXTRACTION_SYSTEM_PROMPT
        return EXTRACTION_SYSTEM_PROMPT

    @staticmethod
    def _get_user_prompt() -> str:
        from src.adapters.vision_adapter import EXTRACTION_USER_PROMPT
        return EXTRACTION_USER_PROMPT


# ── Minimal eval loop ─────────────────────────────────────────────────────────

PNG_DIR     = ROOT / "ocr_eval" / "png_v2"
GOLDEN_FILE = ROOT / "ocr_eval" / "mock_data.json"
FILE_MAP    = {i: f"OCR-GOLDEN-{i:03d}" for i in range(1, 21)}


async def run_one(i: int, png_path: Path, golden: dict,
                  processor: ImageProcessor,
                  adapter: FixedVisionAdapter,
                  repo: ReferenceRepository) -> dict:
    report_id = golden["report_id"]
    t0 = time.perf_counter()

    try:
        raw = png_path.read_bytes()
        processed = processor.process(raw, filename=png_path.name)
    except Exception as exc:
        return {"report_id": report_id, "success": False,
                "error": f"preprocess: {exc}",
                "t_total_ms": (time.perf_counter() - t0) * 1000}

    try:
        drafts = await adapter.extract(processed.bytes, processed.mime_type)
    except Exception as exc:
        return {"report_id": report_id, "success": False,
                "error": f"ocr: {exc}",
                "t_total_ms": (time.perf_counter() - t0) * 1000,
                "provider": getattr(adapter, "last_provider", "?")}

    t_total_ms = (time.perf_counter() - t0) * 1000

    golden_by_canonical = {ind["analyte_canonical"]: ind
                           for ind in golden["indicators"]}
    matched = 0
    val_ok  = 0
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
    print("[fix-plan-a] Loading golden data …")
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden_data = json.load(f)
    golden_by_id = {r["report_id"]: r for r in golden_data["reports"]}

    processor = ImageProcessor()
    adapter   = FixedVisionAdapter()
    repo      = ReferenceRepository.from_default_files()

    results = []
    print(f"[fix-plan-a] Running on {PNG_DIR.name} (20 files) …\n")

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
            print(f"OK  matched {r['matched']}/35  val {r['val_ok']}/{r['matched']}"
                  f"  {r['t_total_ms']:,.0f} ms {provider_tag}")
        else:
            print(f"FAIL: {r.get('error', '')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    ok = [r for r in results if r["success"]]
    success_rate = len(ok) / len(results) * 100 if results else 0

    print()
    print("=" * 60)
    print("  Fix Plan A — Results")
    print("=" * 60)
    print(f"  Report Success Rate : {len(ok)}/{len(results)} = {success_rate:.1f}%"
          f"   (baseline: 8/20 = 40.0%)")
    print()
    print(f"  Schema failures detected   : {FixedVisionAdapter.schema_fail_count}")
    print(f"  Recovered via retry        : {FixedVisionAdapter.schema_retry_ok}")
    print(f"  Fell back to OpenRouter    : {FixedVisionAdapter.schema_fallback_cnt}")
    print()

    if ok:
        providers = [r.get("provider", "?") for r in ok]
        gemini_ok = providers.count("gemini")
        or_ok     = providers.count("openrouter")
        print(f"  Successful via Gemini      : {gemini_ok}")
        print(f"  Successful via OpenRouter  : {or_ok}")
        avg_lat = sum(r["t_total_ms"] for r in ok) / len(ok)
        print(f"  Mean latency (success)     : {avg_lat:,.0f} ms")

    print("=" * 60)

    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\n  Still failing ({len(failed)}):")
        for r in failed:
            print(f"    {r['report_id']} — {r.get('error', '')[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
