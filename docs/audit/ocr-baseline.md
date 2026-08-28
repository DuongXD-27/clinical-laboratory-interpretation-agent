# Baseline OCR — Phiếu Xét Nghiệm (ADR-006)

**Cập nhật:** 2026-08-04 (model `google/gemma-4-26b-a4b-it:free`)
**Đo đầu tiên:** 2026-08-04 (model `nvidia/nemotron-nano-12b-v2-vl:free`)

## Cách tái lập

```bash
# 1. Sinh ảnh mẫu (4 biến thể)
.venv/bin/python src/scripts/generate_ocr_samples.py

# 2. Chạy đo baseline (gọi VLM thật — free-tier có thể mất vài phút cho 4 ảnh)
.venv/bin/python -m src.scripts.eval_ocr
# Kết quả thô -> eval/ocr_baseline.json
```

## Bộ ảnh mẫu

Mỗi ảnh chứa 3 chỉ số kỳ vọng:

| Chỉ số | Giá trị | Đơn vị |
|---|---|---|
| Glucose | 5.2 | mmol/L |
| LDL-Cholesterol | 2.2 | mmol/L |
| Kali | 4.0 | mmol/L |

| Biến thể | Mô tả |
|---|---|
| `normal` | Phiếu sạch, thẳng, đủ sáng |
| `blur` | GaussianBlur radius 2.2 — mô phỏng ảnh mờ |
| `skew` | Xoay 3.2° — mô phỏng phiếu chụp nghiêng |
| `lowlight` | Giảm brightness 0.45 / contrast 0.7 — thiếu sáng |

## Cấu hình model

- Provider: OpenRouter (OpenAI-compatible)
- Model hiện tại: `google/gemma-4-26b-a4b-it:free` (đổi qua `VISION_MODEL`)

## Kết quả — gemma (hiện tại, 2026-08-04)

Model `google/gemma-4-26b-a4b-it:free`. Độ chính xác: đọc đúng cả 3 chỉ số ở
4/4 biến thể (abs_err=0, conf=1.00). Tốc độ VLM theo từng ảnh: 11–42s
(free-tier — chậm hơn model trả phí nhưng ổn định hơn nemotron, ít rate-limit).

| Variant | Glucose abs_err | LDL abs_err | Kali abs_err | VLM time | Nhận xét |
|---|---|---|---|---|---|
| normal | 0.000 | 0.000 | 0.000 | 42.0s | conf=1.00 |
| blur | 0.000 | 0.000 | 0.000 | 11.2s | conf=1.00 |
| skew | 0.000 | 0.000 | 0.000 | 25.8s | Deskew chỉnh -3.03°, conf=1.00 |
| lowlight | 0.000 | 0.000 | 0.000 | 23.0s | 1 lần retry, conf=1.00 |

## Kết quả — nemotron (baseline đầu tiên, 2026-08-04)

Model `nvidia/nemotron-nano-12b-v2-vl:free` — giữ lại để đối chiếu.
Đọc đúng 4/4 biến thể nhưng **không ổn định**: hay rate-limit, trả rỗng,
cần retry nhiều lần.

| Variant | Glucose abs_err | LDL abs_err | Kali abs_err | Nhận xét |
|---|---|---|---|---|
| normal | 0.000 | 0.000 | 0.000 | conf=1.00 |
| blur | 0.000 | 0.000 | 0.000 | conf=1.00 |
| skew | 0.000 | 0.000 | 0.000 | Deskew chỉnh -3.03°, conf=0.90 |
| lowlight | 0.000 | 0.000 | 0.000 | conf=1.00 |

> Trạng thái: **2 model đều đạt 4/4 biến thể, abs_err=0**. Gemma được chọn
> làm mặc định vì ổn định hơn nemotron (ít rate-limit/trả rỗng). Cả 2 vẫn là
> free-tier nên chậm (10–40s/ảnh); preprocess (deskew cho ảnh nghiêng,
> auto-contrast cho ảnh thiếu sáng) hoạt động đúng trên cả 4 ca. Đạt đầy đủ
> tiêu chí chấp nhận ở phần dưới.

## Tiêu chí chấp nhận

- 100% chỉ số ở biến thể `normal` được nhận diện.
- 100% giá trị đọc được sai số < 0.3 đơn vị.
- Biến thể degrade (blur/skew/lowlight) không tệ hơn `normal` quá 2 chỉ số
  bị sai/NOT FOUND — nếu không, xem xét: tăng cường preprocess, đổi model,
  hoặc bắt buộc UI_Review với `confidence` thấp.
