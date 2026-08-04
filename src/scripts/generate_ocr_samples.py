"""Sinh bộ ảnh phiếu xét nghiệm mẫu cho OCR baseline (ADR-006).

Mỗi phiếu: tiêu đề + bảng chỉ số (3 chỉ số giống mock demo) + footer.
4 biến thể: normal, blur (mờ), skew (nghiêng), lowlight (thiếu sáng).

Usage:
    .venv/bin/python src/scripts/generate_ocr_samples.py
    # -> data/ocr_samples/{normal,blur,skew,lowlight}/report.png
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data" / "ocr_samples"

# Chỉ số mẫu — giữ khớp các chỉ số trong explanations.json để dễ đối chiếu.
SAMPLE_ROWS = [
    ("Glucose", "5.2", "mmol/L"),
    ("LDL-Cholesterol", "2.2", "mmol/L"),
    ("Kali", "4.0", "mmol/L"),
]

WIDTH, HEIGHT = 900, 700


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Ưu tiên font hệ thống có hỗ trợ Unicode; fallback default font."""
    for name in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(name):
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def _draw_report(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    # Viền ngoài + tiêu đề.
    draw.rectangle([10, 10, WIDTH - 10, HEIGHT - 10], outline=(0, 0, 0), width=2)
    draw.text((40, 30), "PHIẾU XÉT NGHIỆM MÁU", font=_load_font(28), fill=(0, 0, 0))
    draw.text((40, 70), "Ngày: 2026-08-01   BN: Nguyễn Văn A   Nam, 35 tuổi", font=_load_font(16), fill=(60, 60, 60))

    # Header bảng.
    x_cols = (40, 330, 500, 700)
    headers = ("Chỉ số", "Kết quả", "Đơn vị", "Khoảng TK")
    draw.rectangle([30, 120, WIDTH - 30, 160], outline=(0, 0, 0), width=1)
    for x, h in zip(x_cols, headers):
        draw.text((x, 130), h, font=_load_font(16), fill=(0, 0, 0))

    y = 180
    for i, (name, value, unit) in enumerate(SAMPLE_ROWS):
        row_y = y + i * 60
        draw.rectangle([30, row_y - 10, WIDTH - 30, row_y + 50], outline=(180, 180, 180), width=1)
        draw.text((x_cols[0], row_y), name, font=_load_font(20), fill=(0, 0, 0))
        draw.text((x_cols[1], row_y), value, font=_load_font(22), fill=(0, 0, 0))
        draw.text((x_cols[2], row_y), unit, font=_load_font(18), fill=(60, 60, 60))
        draw.text((x_cols[3], row_y), "Bình thường" if i < 2 else "Bình thường", font=_load_font(14), fill=(90, 90, 90))

    draw.text((40, HEIGHT - 80), "Ghi chú: Kết quả chỉ mang tính tham khảo.", font=_load_font(14), fill=(120, 120, 120))


def _blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=2.2))


def _skew(img: Image.Image) -> Image.Image:
    return img.rotate(3.2, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))


def _lowlight(img: Image.Image) -> Image.Image:
    from PIL import ImageEnhance

    # Giảm độ sáng + tương phản để mô phỏng ảnh thiếu sáng.
    img = ImageEnhance.Brightness(img).enhance(0.45)
    return ImageEnhance.Contrast(img).enhance(0.7)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = {
        "normal": lambda img: img,
        "blur": _blur,
        "skew": _skew,
        "lowlight": _lowlight,
    }
    for name, fn in variants.items():
        img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
        _draw_report(img)
        out = fn(img)
        dest = OUTPUT_DIR / name
        dest.mkdir(exist_ok=True)
        out.save(dest / "report.png")
        print(f"  wrote {dest / 'report.png'} ({out.size[0]}x{out.size[1]})")


if __name__ == "__main__":
    main()
