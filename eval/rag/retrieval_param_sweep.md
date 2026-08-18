# Retrieval parameter sweep (RETRIEVAL_MIN_SCORE x top_k)

Analyte/status pairs tested: 85 (full curated corpus: ['albumin', 'alt', 'ast', 'chloride', 'creatinine', 'eosinophils_%', 'eosinophils_abs', 'fasting_plasma_glucose', 'ggt', 'hba1c', 'hct', 'hdl_c', 'hgb', 'ldl_c', 'lymphocytes_%', 'lymphocytes_abs', 'mch', 'mchc', 'mcv', 'monocytes_%', 'monocytes_abs', 'neutrophils_%', 'neutrophils_abs', 'plt', 'potassium', 'rbc', 'rdw_cv', 'sodium', 'total_bilirubin', 'total_cholesterol', 'total_protein', 'triglyceride', 'urea', 'uric_acid', 'wbc'])

| min_score | top_k | fallback_rate | primary_hit_rate@1 | avg_chunks | avg_context_chars |
|---|---|---|---|---|---|
| 0.4 | 1 | 0.624 | 0.938 | 1.0 | 161.8 |
| 0.4 | 2 | 0.624 | 0.938 | 1.31 | 208.2 |
| 0.4 | 3 | 0.624 | 0.938 | 1.53 | 240.1 |
| 0.4 | 5 | 0.624 | 0.938 | 1.69 | 257.3 |
| 0.45 | 1 | 0.871 | 0.818 | 1.0 | 165.5 |
| 0.45 | 2 | 0.871 | 0.818 | 1.45 | 217.5 |
| 0.45 | 3 | 0.871 | 0.818 | 1.55 | 235.4 |
| 0.45 | 5 | 0.871 | 0.818 | 1.55 | 235.4 |
| 0.5 | 1 | 0.953 | 1.0 | 1.0 | 141.2 |
| 0.5 | 2 | 0.953 | 1.0 | 1.25 | 176.8 |
| 0.5 | 3 | 0.953 | 1.0 | 1.25 | 176.8 |
| 0.5 | 5 | 0.953 | 1.0 | 1.25 | 176.8 |
| 0.55 | 1 | 0.988 | 1.0 | 1.0 | 68.0 |
| 0.55 | 2 | 0.988 | 1.0 | 1.0 | 68.0 |
| 0.55 | 3 | 0.988 | 1.0 | 1.0 | 68.0 |
| 0.55 | 5 | 0.988 | 1.0 | 1.0 | 68.0 |
| 0.6 | 1 | 1.0 | None | 0 | 0 |
| 0.6 | 2 | 1.0 | None | 0 | 0 |
| 0.6 | 3 | 1.0 | None | 0 | 0 |
| 0.6 | 5 | 1.0 | None | 0 | 0 |
| 0.65 | 1 | 1.0 | None | 0 | 0 |
| 0.65 | 2 | 1.0 | None | 0 | 0 |
| 0.65 | 3 | 1.0 | None | 0 | 0 |
| 0.65 | 5 | 1.0 | None | 0 | 0 |
| 0.7 | 1 | 1.0 | None | 0 | 0 |
| 0.7 | 2 | 1.0 | None | 0 | 0 |
| 0.7 | 3 | 1.0 | None | 0 | 0 |
| 0.7 | 5 | 1.0 | None | 0 | 0 |
| 0.75 | 1 | 1.0 | None | 0 | 0 |
| 0.75 | 2 | 1.0 | None | 0 | 0 |
| 0.75 | 3 | 1.0 | None | 0 | 0 |
| 0.75 | 5 | 1.0 | None | 0 | 0 |
| 0.8 | 1 | 1.0 | None | 0 | 0 |
| 0.8 | 2 | 1.0 | None | 0 | 0 |
| 0.8 | 3 | 1.0 | None | 0 | 0 |
| 0.8 | 5 | 1.0 | None | 0 | 0 |
| 0.85 | 1 | 1.0 | None | 0 | 0 |
| 0.85 | 2 | 1.0 | None | 0 | 0 |
| 0.85 | 3 | 1.0 | None | 0 | 0 |
| 0.85 | 5 | 1.0 | None | 0 | 0 |
