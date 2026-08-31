# Issue: Gemini OCR JSON Truncation — max_output_tokens Too Low

**Severity:** P0 → **RESOLVED**  
**Component:** `src/adapters/vision_adapter.py` + `.env`  
**Observed in:** OCR evaluation runs (2026-08-30)  
**Resolved in:** Fix Plan B (2026-08-31) — increase `GEMINI_VISION_MAX_OUTPUT_TOKENS` from 2048 → 4096

---

## Mô tả ban đầu

60% request gọi Gemini Vision (`gemini-3.5-flash-lite`) raise `VisionAdapterError`:

```
ValidationError: Invalid JSON: EOF while parsing a string
```

Báo cáo: 40% Report Success Rate (8/20 phiếu) qua 2 lần chạy trên 2 bộ ảnh khác nhau.

---

## Root Cause Confirmed

**JSON bị truncate do `max_output_tokens=2048` quá thấp.**

`GEMINI_VISION_THINKING_LEVEL=low` tiêu tốn ~600 token thinking từ ngân sách output, chỉ còn ~1400 token cho JSON thực. Mỗi phiếu có 35 chỉ số × ~40 token/chỉ số ≈ 1400 token — ở ngưỡng giới hạn, khiến JSON bị cắt giữa chừng tại indicator #33 của 35.

**Bằng chứng từ `fix_plan_A.py` log:**

```
ValidationError: Invalid JSON: EOF while parsing a string at line 183 column 11
```
- Compact JSON: luôn cắt ở ký tự ~4050 (tương đương indicator #33)
- Pretty-printed JSON: luôn cắt ở dòng 183 (tương đương indicator #23 trong format 9-dòng/indicator)
- Tất cả failure đều là `EOF while parsing` — không phải schema mismatch

**Tại sao non-deterministic?** Gemini đôi khi dùng compact JSON, đôi khi pretty-printed — dẫn đến số indicator được fit vào ngân sách khác nhau; những file có indicator cuối nhỏ hơn đôi khi may mắn vừa.

---

## Evidence Table

| Run | Script | max_tokens | Success Rate | Ghi chú |
|-----|--------|-----------|-------------|---------|
| v1 baseline | `run_eval.py` | 2048 | 8/20 = **40%** | Original |
| v2 baseline | `run_eval.py` | 2048 | 8/20 = **40%** | `png_v2/` |
| Plan A | `fix_plan_A.py` | 2048 | 10/20 = **50%** | Retry schema fail → partially helps |
| Plan A re-run | `fix_plan_A.py` | 2048 | 12/20 = **60%** | Non-deterministic |
| **Plan B** | `fix_plan_B.py` | **4096** | **20/20 = 100%** | **Fix confirmed** |
| **v3 final** | `run_eval.py` | **4096** | **20/20 = 100%** | All 12 metrics |

---

## Fix Applied

**`.env`** — tăng token limit:

```diff
- GEMINI_VISION_MAX_OUTPUT_TOKENS=2048
+ GEMINI_VISION_MAX_OUTPUT_TOKENS=4096
```

`Settings` model cho phép tối đa 4096. Giá trị này đủ cho 35 indicator × ~40 token + ~600 token thinking = ~2000 token tổng, trong ngân sách 4096.

**Không cần thay đổi code** — chỉ cần tăng config.

---

## Kết quả sau khi fix (report_v3.md)

| Metric | Kết quả |
|--------|---------|
| Report Success Rate | **100%** (20/20) |
| Analyte Precision / Recall / F1 | **100%** |
| Value Accuracy | **100%** |
| Unit Accuracy | 94.4% |
| Reference Range Accuracy | 99.8% |
| Complete Record Accuracy | 94.4% |
| Critical OCR Error Rate | 0% |
| Mean Latency | 6,903 ms |
| P95 Latency | 9,434 ms |

Unit Accuracy 94.4% và Complete Record Accuracy 94.4% là giới hạn nhận dạng của model đối với một số đơn vị hiếm — không phải lỗi truncation.

---

## Lessons Learned

1. `GEMINI_VISION_THINKING_LEVEL=low` với Gemini 2.5 Flash Lite tiêu tốn ~600 token từ ngân sách `max_output_tokens` — cần tính vào capacity planning.
2. Response text bị truncate → `json.JSONDecodeError` → bị wrap bởi `ValidationError` → dẫn đến lỗi trông giống như schema mismatch nhưng thực chất là truncation.
3. Logging `str(exc)` thay vì `type(exc).__name__` là bước chẩn đoán quan trọng — nếu message là `EOF while parsing`, đó là truncation, không phải schema incompatibility.
4. Cần monitor `len(response.text)` và check xem response có kết thúc bằng `}` hợp lệ không khi schema validation fail.

---

## Files liên quan

- `ocr_eval/fix_plan_A.py` — Plan A (schema fail → retry + fallback): cải thiện 40% → 50-60%, không đủ
- `ocr_eval/fix_plan_B.py` — Plan B (tăng max_output_tokens=4096): giải quyết 100%
- `ocr_eval/report_v3.md` — Báo cáo đánh giá cuối cùng với tất cả 12 metric

---

*Documented by `ocr_eval/run_eval.py`. Resolved 2026-08-31.*
