"""Đo baseline OCR trên bộ ảnh mẫu (ADR-006).

Với mỗi ảnh trong data/ocr_samples/*/report.png: preprocess -> VLM -> so
với giá trị kỳ vọng (SAMPLE_ROWS trong generate_ocr_samples.py). In sai số
theo từng biến thể. KHÔNG ghi vào AgentState — chỉ đánh giá Adapter_Vision.

Usage (cần GOOGLE_API_KEY trong .env):
    .venv/bin/python src/scripts/eval_ocr.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from src.adapters.vision_adapter import VisionAdapter, close_vision_clients
from src.models.ocr_schemas import OCRIndicatorDraft
from src.services.image_processor import ImageProcessor

logging.basicConfig(level=logging.INFO)

ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = ROOT / "data" / "ocr_samples"

# Khớp SAMPLE_ROWS trong generate_ocr_samples.py.
EXPECTED: list[dict] = [
    {"name": "Glucose", "value": 5.2, "unit": "mmol/L"},
    {"name": "LDL-Cholesterol", "value": 2.2, "unit": "mmol/L"},
    {"name": "Kali", "value": 4.0, "unit": "mmol/L"},
]


def _match_by_name(drafts: list[OCRIndicatorDraft]) -> dict[str, OCRIndicatorDraft]:
    """Map tên chỉ số (chứa sub-string để dung hoà cách viết) -> draft."""
    out: dict[str, OCRIndicatorDraft] = {}
    for d in drafts:
        key = d.name.strip().lower()
        if "gluc" in key or "đư" in key or "duong" in key:
            out["glucose"] = d
        elif "ldl" in key or "cholesterol" in key:
            out["ldl"] = d
        elif "kali" in key or "potassium" in key:
            out["kali"] = d
    return out


def _rel_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), 1e-9)


async def evaluate_folder(
    processor: ImageProcessor, adapter: VisionAdapter, folder: Path
) -> dict:
    report_path = folder / "report.png"
    raw = report_path.read_bytes()
    processed = processor.process(raw, filename="report.png")
    drafts = await adapter.extract(processed.bytes, processed.mime_type)

    matched = _match_by_name(drafts)
    results: list[dict] = []
    for exp in EXPECTED:
        draft = matched.get(
            "glucose" if "Glucose" in exp["name"] else "ldl" if "LDL" in exp["name"] else "kali"
        )
        if draft is None:
            results.append({**exp, "found": False, "abs_err": None, "confidence": None})
            continue
        results.append(
            {
                **exp,
                "found": True,
                "abs_err": abs(draft.value - exp["value"]),
                "rel_err": _rel_error(draft.value, exp["value"]),
                "confidence": draft.confidence,
                "read_as": draft.value,
            }
        )
    return {"variant": folder.name, "results": results}


async def main() -> None:
    if not SAMPLES_DIR.exists():
        raise SystemExit("Chưa có ảnh mẫu. Chạy: python src/scripts/generate_ocr_samples.py")

    processor = ImageProcessor()
    adapter = VisionAdapter()
    summary: list[dict] = []
    try:
        for folder in sorted(SAMPLES_DIR.iterdir()):
            if not folder.is_dir():
                continue
            print(f"\n=== {folder.name} ===")
            out = await evaluate_folder(processor, adapter, folder)
            summary.append(out)
            for r in out["results"]:
                status = f"abs_err={r['abs_err']:.3f}" if r["found"] else "NOT FOUND"
                conf = (
                    f"conf={r['confidence']:.2f}"
                    if r.get("confidence") is not None
                    else ""
                )
                print(
                    f"  {r['name']:<16} expected={r['value']:>5} "
                    f"{status:<16} {conf}"
                )
    finally:
        await close_vision_clients()

    report = {"expected": EXPECTED, "runs": summary}
    dest = ROOT / "eval" / "ocr_baseline.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved -> {dest}")


if __name__ == "__main__":
    asyncio.run(main())
