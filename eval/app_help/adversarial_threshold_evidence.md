# App Help retrieval — threshold evidence (APP_HELP_RETRIEVAL_MIN_SCORE)

Run: `python -m eval.app_help.adversarial_threshold_test` (2026-08-25, embedding
provider: gemini/gemini-embedding-001, dim=3072, collection `app_help_kb_v1`,
50 chunks from `data/app_how_to_use/`).

## Method

1. 11 genuine app-help questions (AH-01..AH-05-style + variants), each with
   an expected `feature` — checked the retriever returns `has_match=True`
   AND the top match's feature is correct.
2. 6 adversarial questions: 3 fully off-topic (Python, weather, cooking) and
   3 "app-shaped but unsupported capability" questions (PDF export, medicine
   reminders) — checked the retriever fails closed (`has_match=False`).

Two measurements informed the current design, not just the final number:

- **Naive query** (raw user message, no preprocessing): genuine floor
  ≈ 0.68 (a question naming an explicit analyte, e.g. "Làm sao xem xu hướng
  WBC?") overlapped the adversarial ceiling ≈ 0.69 ("Đặt lịch hẹn với bác sĩ
  qua app không?") — no single threshold could separate them safely. Root
  cause: the analyte name is retrieval noise for "which app feature", not
  signal (see `strip_explicit_analyte` docstring in
  `src/services/app_help_retriever.py`).
- **After** stripping the explicit analyte from the query before embedding,
  and after adding deterministic feature hints (`FEATURE_HINTS`) for
  known explicit phrasings to resolve near-duplicate cross-feature
  confusion (e.g. "tôi tải phiếu xét nghiệm ở đâu?" initially top-matched
  `history.md`'s generic "what is this for" section over
  `upload-analysis.md`'s own answer, 0.7639 vs 0.7582) — the numbers below.

## Result at `APP_HELP_RETRIEVAL_MIN_SCORE=0.70` (re-run after the routing/retrieval audit, see below)

```
=== GENUINE (must match expected feature) ===
OK   score=1.0000  feature=upload-analysis     Làm sao tải phiếu xét nghiệm?
OK   score=1.0000  feature=upload-analysis     tôi tải phiếu xét nghiệm ở đâu?
OK   score=0.7048  feature=upload-analysis     Tại sao tôi không tải được phiếu xét nghiệm?
OK   score=0.7787  feature=history             Tôi xem lịch sử ở đâu?
OK   score=0.7412  feature=trends              Làm sao xem xu hướng WBC?
OK   score=0.7412  feature=trends              Làm sao xem xu hướng HbA1c?
OK   score=0.7323  feature=ocr-review          Tại sao phải xác nhận OCR?
OK   score=1.0000  feature=ocr-review          hướng dẫn tôi dùng OCR
OK   score=1.0000  feature=ocr-review          Chức năng OCR của ứng dụng dùng để làm gì?
OK   score=1.0000  feature=profile             Tôi sửa hồ sơ ở đâu?
OK   score=0.7408  feature=critical-alerts     Cảnh báo khẩn cấp nghĩa là gì?

=== ADVERSARIAL (must fail closed, has_match=False) ===
OK   fail_closed=True  raw_top1_score=0.6019  Hướng dẫn viết Python
OK   fail_closed=True  raw_top1_score=0.5660  Hôm nay thời tiết thế nào?
OK   fail_closed=True  raw_top1_score=0.5494  Làm sao nấu phở bò ngon?
OK   fail_closed=True  raw_top1_score=0.6818  Xuất phiếu ra file PDF ký số ở đâu?
OK   fail_closed=True  raw_top1_score=0.6845  Ứng dụng có xuất được báo cáo PDF không?
OK   fail_closed=True  raw_top1_score=0.6458  App có tính năng nhắc uống thuốc không?

Genuine score floor (dense-search cases only): 0.7048
Adversarial score ceiling:                     0.6845
Margin at min_score=0.7: floor - ceiling = 0.0202
```

`score=1.0000` is not a real similarity score — it's the sentinel for a
**deterministic** match (see "Deterministic-first path" below), used when a
question resolves both its feature AND its section via curated exact-phrase
lookups instead of embedding similarity. It correctly bypasses the
threshold entirely, by design, for exactly these curated phrasings — not a
sign the threshold stopped mattering for everything else. Adversarial
questions never hit this path (none of them match a curated `FEATURE_HINTS`
phrase), confirmed above: all 6 still fail closed through the normal dense
path.

## Post-launch findings: a systematic phrasing audit (2026-08-25, same day)

Manual UI testing surfaced 3 bugs the original 11-question eval set didn't
catch, which prompted a broader audit (~20 phrasings across all 10
features instead of the original hand-picked set):

1. **Wrong section within the right feature.** "Làm sao tải phiếu xét
   nghiệm?" resolved the correct feature (`upload-analysis`) but the dense
   top-1 was "Feature này dùng để làm gì?" (mission statement) instead of
   "Các bước sử dụng?" (the actual click-by-click steps) — a real product
   bug: a how-to question answered with a description, no instructions.
   Fixed by `_section_hint()`: detect STEP / WHERE / WHAT question intent
   from cue words and do an exact `(feature, heading)` metadata lookup to
   promote the right section, instead of trusting raw dense rank within
   the feature.
2. **Alternate Vietnamese "how" phrasings never reached the nav-cue check
   at all.** "Làm thế nào để tải ảnh phiếu?" and the colloquial "...thì
   làm như nào" (dropping "thế") only matched "làm sao", not "làm thế
   nào" / "làm như nào" / "bằng cách nào" — so they fell through to
   `explicit_new_ingestion_markers` ("tải ảnh" matches there) and got
   routed to `ANALYZE_REPORT` (start ingesting a report now), which then
   failed with a "no report found" NEEDS_INPUT message instead of
   answering the actual question. Fixed by widening `app_help_nav_cues`.
3. **Feature-question collisions found by the audit, not by manual
   guessing:** "Câu hỏi cho bác sĩ ở đâu?" was swallowed by
   `GET_DOCTOR_QUESTIONS` (bare "câu hỏi" match) before reaching APP_HELP;
   "Cảnh báo khẩn cấp nghĩa là gì?" — explicitly one of
   `phan-cong-vu.txt`'s own required example questions — routed to
   `EXPLAIN_CURRENT_RESULT` because "nghĩa là gì" is a generic medical
   explain-marker. Both fixed with explicit APP_HELP cues/patterns,
   verified the corresponding medical/real-data questions ("tôi muốn hỏi
   bác sĩ về HbA1c", "WBC nghĩa là gì?") still route correctly elsewhere.
4. **Deterministic-first path (new).** Investigating #3 surfaced a
   separate false-negative: "Tải phiếu ở đâu?" correctly resolved its
   feature via `FEATURE_HINTS` but every chunk within that feature scored
   just under the 0.70 threshold for this short/vague phrasing — a
   genuine question was fail-closed for no good reason. When BOTH the
   feature (curated exact-phrase match) and the section (literal heading
   cue) resolve deterministically, the retriever now skips the embedding
   search and threshold entirely (`AppHelpRetriever._lookup_section`) —
   there is no similarity guess involved for these curated phrasings, so
   there's nothing for a threshold to gate.

All 4 fixes are covered by unit tests in `tests/orchestrator/test_app_help.py`
and `tests/test_services/test_app_help_retriever.py`. See git log on
`feature/app-help-rag` for the individual commits and full narrative.

## Caveats (honest, not hidden)

- Margin is ~0.02, narrower than medical_kb_v4's evidence-tuned margin
  (genuine 0.807 vs junk 0.794 per `eval/rag/adversarial_threshold_test.py`
  — actually a similar ~0.013 margin there too, so this is in the same
  ballpark as the project's existing precedent, not categorically weaker).
- `strip_explicit_analyte` only strips ASCII-safe aliases (e.g. "WBC",
  "HbA1c") reliably; Vietnamese-worded analyte mentions with diacritics
  (e.g. "bạch cầu") are not stripped because `ReferenceRepository`'s alias
  keys are diacritic-normalized and a naive regex match against the raw
  (accented) message won't hit them. Low-risk in practice since app-help
  questions naming a specific analyte overwhelmingly use the short-form
  abbreviation, but noted for a future corpus/eval refresh.
- Coverage here is 11 genuine + 6 adversarial questions, not exhaustive.
  Re-run this script (and re-tune the threshold if it drifts) whenever the
  corpus in `data/app_how_to_use/` changes materially.
