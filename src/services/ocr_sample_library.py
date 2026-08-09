"""Bộ ảnh phiếu xét nghiệm mẫu dùng cho bản demo public (V3).

Hai mục đích, tách bạch:

1. **Giảm động lực đưa ảnh thật lên.** Người dùng thử được ngay bằng ảnh có
   sẵn nên không cần chụp phiếu của chính mình.
2. **Làm cho `OCR_UPLOAD_MODE=demo_only` có hiệu lực thật.** Chế độ này đối
   chiếu SHA-256 của ảnh tải lên với bộ mẫu; ảnh lạ bị từ chối ngay ở backend.
   Nếu chỉ ẩn nút upload ở giao diện thì bất kỳ ai gọi thẳng API vẫn đẩy được
   ảnh thật vào — đó là lớp trải nghiệm, không phải lớp bảo vệ.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.config import get_settings


class OCRSampleLibraryError(Exception):
    """Không đọc được bộ ảnh mẫu."""


@dataclass(frozen=True)
class OCRSample:
    sample_id: str
    label: str
    description: str
    path: Path
    sha256: str
    size_bytes: int


# Nhãn tiếng Việt cho từng thư mục mẫu. Thư mục nào không có trong đây vẫn
# được nạp, chỉ là hiển thị bằng chính tên thư mục.
_SAMPLE_LABELS: dict[str, tuple[str, str]] = {
    "normal": ("Phiếu rõ nét", "Ảnh chụp thẳng, đủ sáng — OCR đọc tốt nhất"),
    "blur": ("Phiếu bị mờ", "Ảnh rung/mất nét — thử xem OCR đọc sai chỗ nào"),
    "lowlight": ("Phiếu thiếu sáng", "Chụp trong điều kiện tối"),
    "skew": ("Phiếu bị nghiêng", "Ảnh chụp lệch góc"),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache
def load_samples() -> tuple[OCRSample, ...]:
    """Quét thư mục mẫu một lần rồi cache lại (ảnh là tài sản tĩnh trong repo)."""
    settings = get_settings()
    root = Path(settings.ocr_samples_dir)
    if not root.is_dir():
        return ()

    samples: list[OCRSample] = []
    for image_path in sorted(root.glob("*/*")):
        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        sample_id = image_path.parent.name
        label, description = _SAMPLE_LABELS.get(sample_id, (sample_id, ""))
        try:
            data = image_path.read_bytes()
        except OSError as exc:
            raise OCRSampleLibraryError(f"Không đọc được ảnh mẫu '{image_path}': {exc}") from exc
        samples.append(
            OCRSample(
                sample_id=sample_id,
                label=label,
                description=description,
                path=image_path,
                sha256=_sha256(data),
                size_bytes=len(data),
            )
        )
    return tuple(samples)


def get_sample(sample_id: str) -> OCRSample | None:
    return next((s for s in load_samples() if s.sample_id == sample_id), None)


def is_known_sample(raw_bytes: bytes) -> bool:
    """True nếu ảnh tải lên đúng là một ảnh mẫu (so khớp SHA-256)."""
    digest = _sha256(raw_bytes)
    return any(s.sha256 == digest for s in load_samples())
