# Wave 2 plausibility authority audit

Audit date: 2026-08-27  
Scope: Potassium, fasting plasma glucose, and HGB input-integrity activation

## External authority reviewed

- Roche `cobas pro` product brochure: the potassium assay lists a technical
  measuring range of 1–100 mmol/L by default and 1–150 mmol/L with an alternate
  sample volume.
- Siemens Healthineers `epoc` system documentation: potassium lists a
  measurement range of 1.5–12.0 mmol/L.
- Roche `cobas pulse` product information: glucose lists 0.6–33.3 mmol/L
  (10–600 mg/dL).
- FDA 510(k) K032203 for HemoCue Hb 201+: results above 25.6 g/dL display `HHH`,
  while linearity is documented only through 23.5 g/dL.
- FDA 510(k) K181751 for HemoCue Hb 801: linearity is documented from
  1.0–25.6 g/dL.

Source URLs:

- https://diagnostics.roche.com/content/dam/diagnostics/Blueprint/en/pdf/cps/cobas-pro/cobas%20pro%20product%20brochure-Digital%20RGB-Single%20pages.pdf
- https://doclib.siemens-healthineers.com/rest/v1/view?document-id=857400
- https://diagnostics.roche.com/de/de/products/instruments/cobas-pulse-system-ins-6473.html
- https://www.accessdata.fda.gov/CDRH510K/K032203.pdf
- https://www.accessdata.fda.gov/cdrh_docs/pdf18/K181751.pdf

## Decision

These are device-specific analytical or reportable ranges. They differ by
analyzer and may also depend on method, sample type, dilution behavior, and
display rules. LumiLab's analysis input currently provides analyte, value, and
unit but not analyzer, method, or specimen identity. Therefore none of these
ranges authorizes a universal production rejection or `NEED_REVIEW` boundary.

| Analyte | Example under review | Active rule | Decision |
| --- | --- | --- | --- |
| Potassium | 500 mmol/L | None | `BLOCKED_BY_MEDICAL_DATA_AUTHORITY` |
| Fasting plasma glucose | 83 mmol/L | None | `BLOCKED_BY_MEDICAL_DATA_AUTHORITY` |
| HGB | extreme OCR/input value | None | `BLOCKED_BY_MEDICAL_DATA_AUTHORITY` |

Production configuration remains at zero active input-integrity rules. A future
activation requires an approved authority that matches the precise runtime
analyzer/method/specimen context or a separately governed cross-device policy.
