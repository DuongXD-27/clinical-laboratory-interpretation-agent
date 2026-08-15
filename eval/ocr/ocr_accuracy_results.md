# VMEC-05 G2 OCR field-level accuracy

**PILOT OCR EVALUATION**  
**N = 4 simulated reports**

These results must not be generalized to real-world clinical documents.

The four images were uploaded through the real `POST /api/v1/ocr/upload` endpoint with consent acknowledged. All four calls returned HTTP 200 from the configured real provider/model, Google Gemini `gemini-3.5-flash-lite`. A transient signed `review_token` was intentionally omitted from stored artifacts; all OCR result fields were preserved.

Ground truth provenance: deterministic `SAMPLE_ROWS` in `src/scripts/generate_ocr_samples.py`, not OCR output. Each ground-truth JSON records the image SHA-256 and transform provenance.

Scoring policy:

- Analyte name: canonical/alias equality via the current approved repository when resolvable; otherwise exact normalized name equality. This keeps the intentionally unsupported generic `Glucose` row scoreable as OCR text without treating it as fasting glucose.
- Value: exact numeric equality after numeric parsing; no tolerance.
- Unit: equality after `ReferenceRepository.normalize_unit()`.
- Complete row: all three fields correct for the same row.

| Condition | Name | Value | Unit | Complete row | API result |
|---|---:|---:|---:|---:|---|
| normal | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | HTTP 200 |
| blur | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | HTTP 200 |
| lowlight | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | HTTP 200 |
| skew | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | HTTP 200 |
| **Overall** | **12/12 (100%)** | **12/12 (100%)** | **12/12 (100%)** | **12/12 (100%)** | **4/4 successful** |

Evidence: `eval/ocr/ground_truth/*.json` and `eval/ocr/raw_outputs/*.json`.
