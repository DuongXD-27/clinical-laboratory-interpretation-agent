"""ImageProcessor — tiền xử lý ảnh phiếu xét nghiệm trước khi OCR (ADR-006).

Gồm: validate định dạng/kích thước, deskew (chỉnh nghiêng nhẹ), auto-contrast
(cải thiện ảnh thiếu sáng), xuất JPEG chuẩn hoá. Tất cả thao tác bằng Pillow
và OpenCV headless để không phụ thuộc GUI (phù hợp chạy server).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

from src.config import get_settings
from src.services.request_timing import timing_span

logger = logging.getLogger(__name__)

# Định dạng ảnh chấp nhận được.
SUPPORTED_FORMATS = {"jpeg", "jpg", "png", "webp", "bmp", "tiff"}
MIME_BY_FORMAT = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
}

# Ngưỡng tối thiểu cho cạnh dài của ảnh trước khi deskew (ảnh quá nhỏ thì
# không đủ thông tin để tính góc nghiêng).
MIN_EDGE_FOR_DESKEW = 400


class ImageProcessorError(Exception):
    """Lỗi tiền xử lý ảnh (định dạng, kích thước, không đọc được...)."""


@dataclass
class ProcessedImage:
    """Kết quả sau tiền xử lý."""

    bytes: bytes
    mime_type: str
    width: int
    height: int


class ImageProcessor:
    def __init__(self) -> None:
        self.settings = get_settings()

    def process(self, raw_bytes: bytes, filename: str | None = None) -> ProcessedImage:
        """Validate + tiền xử lý ảnh, trả về ảnh JPEG chuẩn hoá.

        Raises:
            ImageProcessorError: nếu ảnh không hợp lệ hoặc vượt giới hạn.
        """
        if not raw_bytes:
            raise ImageProcessorError("File ảnh rỗng.")

        try:
            with timing_span("image-decode"):
                img = Image.open(io.BytesIO(raw_bytes))
                img.load()
        except Exception as exc:
            raise ImageProcessorError(f"Không đọc được file ảnh: {exc}") from exc

        fmt = (img.format or "").lower()
        if fmt not in SUPPORTED_FORMATS:
            raise ImageProcessorError(
                f"Định dạng không hỗ trợ: {fmt or 'unknown'} (chỉ {sorted(SUPPORTED_FORMATS)})."
            )

        max_mb = self.settings.vision_max_image_mb
        if len(raw_bytes) > max_mb * 1024 * 1024:
            raise ImageProcessorError(
                f"Ảnh vượt giới hạn {max_mb}MB ({len(raw_bytes) / 1024 / 1024:.1f}MB)."
            )

        # Bỏ kênh alpha (JPEG không có alpha) bằng nền trắng.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        img = img.convert("RGB")
        with timing_span("image-auto-contrast"):
            img = self._auto_contrast(img)
        with timing_span("image-deskew"):
            img = self._deskew(img)

        # Giới hạn cạnh dài để không đẩy base64 quá lớn lên VLM.
        max_edge = 2048
        with timing_span("image-resize"):
            if max(img.size) > max_edge:
                img.thumbnail((max_edge, max_edge), Image.LANCZOS)

        out = io.BytesIO()
        with timing_span("image-jpeg-encode"):
            img.save(out, format="JPEG", quality=92)
        return ProcessedImage(
            bytes=out.getvalue(),
            mime_type="image/jpeg",
            width=img.width,
            height=img.height,
        )

    def _auto_contrast(self, img: Image.Image) -> Image.Image:
        """Tự tăng tương phản — hỗ trợ ảnh thiếu sáng/mờ nhạt."""
        return ImageOps.autocontrast(img, cutoff=2)

    def _deskew(self, img: Image.Image) -> Image.Image:
        """Chỉnh nghiêng nhẹ bằng phép chiếu Hough trên phiên bản gray."""
        width, height = img.size
        if min(width, height) < MIN_EDGE_FOR_DESKEW:
            return img

        gray = np.array(img.convert("L"))
        # Nghịch đảo để chữ/đường kẻ (tối) thành vùng trắng — dễ phát hiện cạnh.
        edges = cv2.Canny(gray, 50, 150)
        # Góc dò trong khoảng [-5, 5] độ (phiếu để nghiêng nhẹ).
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180.0,
            threshold=80,
            minLineLength=max(40, int(min(width, height) * 0.1)),
            maxLineGap=10,
        )
        if lines is None:
            return img

        # OpenCV 4.x trả shape (N, 1, 4); OpenCV 5.0 trả (N, 4).
        if lines.ndim == 3:
            lines = lines[:, 0]

        angles: list[float] = []
        for x1, y1, x2, y2 in lines:
            if x2 == x1:
                continue
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Chỉ lấy đường gần ngang (phiếu scan thường lệch < 5 độ).
            if abs(angle) < 5.0:
                angles.append(angle)
        if not angles:
            return img

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.3:
            return img

        logger.info("Deskew %.2f deg", median_angle)
        return img.rotate(median_angle, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
