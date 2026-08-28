"""Sequential provider-only OCR latency benchmark.

Preprocessing happens once before the timer.  Each measured interval contains
only ``VisionAdapter.extract``.  No image, prompt, or extracted value is logged.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.vision_adapter import (  # noqa: E402
    VisionAdapter,
    close_vision_clients,
)
from src.config import get_settings  # noqa: E402
from src.services.image_processor import ImageProcessor  # noqa: E402

DEFAULT_SAMPLE = ROOT / "data" / "ocr_samples" / "normal" / "report.png"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.provider == "gemini" and not settings.google_api_key.strip():
        raise SystemExit("Thiếu GOOGLE_API_KEY")
    if args.provider == "openrouter" and not settings.openrouter_api_key.strip():
        raise SystemExit("Thiếu OPENROUTER_API_KEY")

    raw = args.sample.read_bytes()
    processed = ImageProcessor().process(raw, filename=args.sample.name)
    adapter = VisionAdapter(
        primary_provider=args.provider,
        fallback_enabled=False,
    )
    durations: list[float] = []
    failures = 0
    try:
        for run_number in range(1, args.runs + 1):
            started_at = time.perf_counter()
            try:
                await adapter.extract(processed.bytes, processed.mime_type)
            except Exception:
                duration_ms = (time.perf_counter() - started_at) * 1000
                failures += 1
                print(f"run={run_number} provider={args.provider} duration_ms={duration_ms:.3f} outcome=fail")
            else:
                duration_ms = (time.perf_counter() - started_at) * 1000
                durations.append(duration_ms)
                print(f"run={run_number} provider={args.provider} duration_ms={duration_ms:.3f} outcome=success")
            if run_number < args.runs and args.delay_seconds:
                await asyncio.sleep(args.delay_seconds)
    finally:
        await close_vision_clients()

    success_rate = len(durations) / args.runs * 100
    if not durations:
        print(f"summary provider={args.provider} runs={args.runs} success_rate=0.0% failures={failures}")
        return 1
    print(
        f"summary provider={args.provider} runs={args.runs} "
        f"success_rate={success_rate:.1f}% failures={failures} "
        f"min_ms={min(durations):.3f} p50_ms={statistics.median(durations):.3f} "
        f"p95_ms={percentile(durations, 0.95):.3f} max_ms={max(durations):.3f}"
    )
    return 0 if failures == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "openrouter"), required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds cannot be negative")
    if not args.sample.is_file():
        parser.error(f"sample does not exist: {args.sample}")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
