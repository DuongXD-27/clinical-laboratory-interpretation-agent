# TIP-P0-INPUT-001 — Input-integrity source audit

Audit date: 2026-08-27  
Scope: repository-approved data; superseded for external Wave 2 investigation
by `WAVE2_PLAUSIBILITY_AUTHORITY_AUDIT.md`

## Searched artifacts

- `data/reference/reference_ranges.json` and `reference_checker_config.json`
- `data/reference/critical_thresholds.json`
- `data/reference/units_metric.csv`
- `data/reference/analyte_catalog.json`
- `data/reference/explanations.json`
- repository ADRs, audit documents, handoffs, tests, and source code matching
  `plausibility`, `reportable measurement range`, `analytical measurement
  range`, `biologically plausible`, `impossible value`, `sanity`, `Potassium`,
  and `Fasting plasma glucose`

## Authority decision

No repository artifact explicitly approves a reportable measurement range,
analytical measurement range, biological-plausibility bound, impossible-value
bound, or input-sanity limit for Potassium or fasting plasma glucose.

The available Potassium and glucose numbers are reference intervals, clinical
decision limits, or critical/panic thresholds. Those sources define medical
classification and escalation behavior; they do not authorize rejecting an
input as implausible. They were therefore not reused, multiplied, or otherwise
derived into input-integrity limits.

## Activation matrix

| Analyte | Canonical unit | Production rule | Decision | Reason |
| --- | --- | --- | --- | --- |
| Potassium | mmol/L | None | `BLOCKED_BY_MEDICAL_DATA_AUTHORITY` | No approved integrity-bound source and section |
| Fasting plasma glucose | mmol/L | None | `BLOCKED_BY_MEDICAL_DATA_AUTHORITY` | No approved integrity-bound source and section |

Production configuration intentionally contains zero active rules. Synthetic
numbers exist only inside tests and are labeled `TEST-ONLY` / `NON-MEDICAL` to
verify engine and pipeline behavior without making a medical claim.
