# Data Description - Laboratory Report Data

This document describes the data structure in the `data/` directory. The dataset
is designed to support an AI Agent that generates simple, patient-friendly
explanations for laboratory test reports.

## 1. Directory Structure

```text
data/
|-- data.md
|-- reference/
|   |-- metrics_range.csv
|   |-- metrics_range.json
|   `-- units_metric.csv
`-- mock/
    |-- templates/
    |   |-- cbc_with_differential.mock.json
    |   |-- electrolytes.mock.json
    |   |-- general_health_check.mock.json
    |   |-- glycemic_profile.mock.json
    |   |-- lipid_profile.mock.json
    |   |-- liver_function_basic.mock.json
    |   `-- renal_function_blood.mock.json
    `-- generated/
        |-- normal.json
        |-- abnormal.json
        `-- edge_case.json
```

## 2. Purpose of Each Data Group

`reference/` contains reference data used to standardize metric names, units,
normal value ranges, decision limits, and source provenance. This is the
foundation for comparing laboratory results before generating explanations.

`mock/templates/` contains JSON templates for each laboratory report type. Each
file is a complete sample report with a representative list of indicators, useful
as an input schema or seed data.

`mock/generated/` contains generated mock reports grouped by scenario: normal
results, abnormal results, and edge cases. These files are suitable for testing
analysis logic, validation, and how the Agent handles missing data or statuses
other than `final`.

## 3. Reference Data

### 3.1. `metrics_range.json`

This JSON file contains an array of objects. Each object describes one reference
range or clinical decision interval for a laboratory metric. The file is derived
from `adult_outpatient_laboratory_reference_map.csv` and keeps source metadata
for traceability.

```json
{
  "test_name": "WBC",
  "standardized_unit": "10^9/L",
  "gender": "A",
  "lower_range": 4.72,
  "upper_range": 11.3,
  "special_note": "Normal Range",
  "source_priority_tier": "T1",
  "source_type": "VN_peer_reviewed_lab_RI",
  "source_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
  "evidence_location": "Table 3.3, combined adults"
}
```

Fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `test_name` | string | Standardized metric name. It should match `indicators[].name` in mock data when range comparison is needed. |
| `standardized_unit` | string | Standard unit for the metric. |
| `gender` | string | Gender that the reference range applies to: `M` for male, `F` for female, `A` for all genders. |
| `lower_range` | number | Lower bound of the normal range. |
| `upper_range` | number or null | Upper bound of the range. This may be `null` for one-sided thresholds such as `>= 7.0 mmol/L` glucose or high lipid categories. |
| `special_note` | string | Short interpretation note for the interval, for example `Normal Range`, `Borderline high`, `High`, `Prediabetes`, or a decision-limit note. |
| `source_priority_tier` | string | Source quality tier copied from the source map. `T1` is the highest-priority source group used here, followed by `T2` and `T3`. |
| `source_type` | string | Source category, such as Vietnamese peer-reviewed laboratory reference interval, official hospital laboratory reference, public health guideline, or accredited laboratory article. |
| `source_url` | string | URL of the source used for the metric range or decision limit. |
| `evidence_location` | string | Location inside the source where the evidence appears, such as a table name, section title, abstract note, or guideline table. |

The current file contains 80 rows covering CBC, glycemic profile, lipid profile,
liver function, renal function, electrolytes, proteins, and bilirubin metrics.
It includes both reference intervals (`RI`) and clinical decision limits (`CDL`)
from the source map. Some indicators have gender-specific ranges, such as `RBC`,
`HGB`, `HCT`, `PLT`, `Creatinine`, `Uric Acid`, `GGT`, and `HDL-Cholesterol`.
Some indicators use a shared range with `gender = A`, such as `WBC`, `Fasting
Blood Glucose`, `HbA1c`, `Total Cholesterol`, and `Sodium (Na)`.

Lipid rows in the source map are stored in `mmol/L`, but the project mock data
and `units_metric.csv` use `mg/dL` for lipid metrics. The generated
`metrics_range.*` files therefore convert lipid intervals back to `mg/dL` using
the source conversion formulas:

| Metric | Source formula | Applied reverse conversion |
| --- | --- | --- |
| `Total Cholesterol` | `mg/dL × 0.0259` | `mg/dL = mmol/L / 0.0259` |
| `HDL-Cholesterol` | `mg/dL × 0.0259` | `mg/dL = mmol/L / 0.0259` |
| `LDL-Cholesterol` | `mg/dL × 0.0259` | `mg/dL = mmol/L / 0.0259` |
| `Triglycerides` | `mg/dL × 0.0113` | `mg/dL = mmol/L / 0.0113` |

### 3.2. `metrics_range.csv`

This CSV file contains the same logical content as `metrics_range.json`, but in a
tabular format for quick inspection or import into data processing tools.

Header:

```csv
test_name,standardized_unit,gender,lower_range,upper_range,special_note,source_priority_tier,source_type,source_url,evidence_location
```

Use `metrics_range.json` as the convenient format for Python/JavaScript code, and
`metrics_range.csv` as the convenient format for spreadsheets, pandas, or manual
review.

### 3.3. `units_metric.csv`

This CSV file is used to look up the standard unit for every metric currently
appearing in the mock data.

Header:

```csv
test_name,standardized_unit
```

The file contains 38 metrics covering CBC, glycemic profile, lipid profile, liver
function, renal function, electrolytes, and proteins. Note that this file only
contains units; it does not include `lower_range`, `upper_range`, or source
metadata. Use `metrics_range.csv` or `metrics_range.json` when the Agent needs
both ranges and source provenance.

## 4. Mock Report Schema

All files in `mock/templates/` and `mock/generated/` use the same report schema:

```json
{
  "report_id": "CBC-20260729-0001",
  "report_type": "cbc_with_differential",
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-07-29",
  "status": "final",
  "indicators": [
    {
      "name": "WBC",
      "value": 7.2,
      "unit": "10^9/L"
    }
  ]
}
```

Report-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `report_id` | string | Unique report identifier. It usually includes the report group, date, and sequence number. |
| `report_type` | string | Laboratory report type, used to determine the expected set of indicators. |
| `patient_age` | number | Patient age. |
| `patient_gender` | string | Patient gender: `male`, `female`, or `unknown`. For reference matching, map these to `M`, `F`, or fallback to `A`. |
| `test_date` | string | Test date in `YYYY-MM-DD` format. |
| `status` | string | Report status. Current values include `final`, `draft`, and `cancelled`. |
| `indicators` | array | List of laboratory indicators. This may be empty in edge cases. |

Indicator-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Laboratory metric name. It should match `test_name` in the reference data for standardization or evaluation. |
| `value` | number | Laboratory result value. It may be an integer or a decimal with multiple digits. |
| `unit` | string | Unit used in the report. This should be compared with `units_metric.csv` or `metrics_range.*`. |

## 5. Template Reports

`mock/templates/` contains 7 template files:

| File | `report_type` | Indicator Count | Main Indicator Group |
| --- | --- | ---: | --- |
| `cbc_with_differential.mock.json` | `cbc_with_differential` | 20 | Complete blood count: WBC, RBC, HGB, HCT, PLT, leukocyte absolute/percentage values, MCV, MCH, MCHC, RDW, MPV. |
| `electrolytes.mock.json` | `electrolytes_basic` | 3 | Electrolytes: Sodium, Potassium, Chloride. |
| `general_health_check.mock.json` | `general_health_check` | 38 | Combined CBC, glycemic, lipid, liver, renal, electrolyte, and protein metrics. |
| `glycemic_profile.mock.json` | `glycemic_profile` | 2 | Blood sugar: Fasting Blood Glucose, HbA1c. |
| `lipid_profile.mock.json` | `lipid_profile` | 4 | Lipids: Total Cholesterol, Triglycerides, HDL, LDL. |
| `liver_function_basic.mock.json` | `liver_function_basic` | 5 | Liver/protein metrics: AST, ALT, GGT, Total Protein, Albumin. |
| `renal_function_blood.mock.json` | `renal_function_blood` | 8 | Renal and electrolyte metrics: Urea, Creatinine, Uric Acid, eGFR, Sodium, Potassium, Chloride, Albumin. |

All current templates use a sample 35-year-old male patient, test date
`2026-07-29`, and status `final`.

## 6. Generated Mock Data

### 6.1. `normal.json`

Contains 5 generated reports with generally normal-looking values:

| Report | `report_type` | Gender | Status | Notes |
| --- | --- | --- | --- | --- |
| `NORMAL-CBC-0001` | `cbc_with_differential` | `female` | `final` | Complete CBC with 20 indicators. |
| `NORMAL-GLY-0002` | `glycemic_profile` | `male` | `final` | Glycemic profile with 2 indicators. |
| `NORMAL-LIPID-0003` | `lipid_profile` | `female` | `draft` | Contains only 3 lipid indicators and is missing `LDL-Cholesterol` compared with the template. |
| `NORMAL-LIVER-0004` | `liver_function_basic` | `female` | `final` | Complete liver/protein report. |
| `NORMAL-RENAL-0005` | `renal_function_blood` | `male` | `final` | Complete renal/electrolyte report. |

### 6.2. `abnormal.json`

Contains 5 generated reports with several abnormal-looking values:

| Report | `report_type` | Gender | Status | Notes |
| --- | --- | --- | --- | --- |
| `ABNORMAL-CBC-0001` | `cbc_with_differential` | `male` | `final` | Contains CBC values outside the available reference ranges, such as high WBC, low HGB, low MCHC, and high RDW. |
| `ABNORMAL-GLY-0002` | `glycemic_profile` | `female` | `final` | Glucose and HbA1c are high by the decision-limit rows now available in `metrics_range.*`. |
| `ABNORMAL-LIPID-0003` | `lipid_profile` | `male` | `draft` | Cholesterol and triglycerides are high-looking, and `LDL-Cholesterol` is missing compared with the template. |
| `ABNORMAL-LIVER-0004` | `liver_function_basic` | `unknown` | `final` | AST, ALT, and GGT are high-looking; patient gender is unknown. |
| `ABNORMAL-RENAL-0005` | `renal_function_blood` | `female` | `final` | Urea, Creatinine, and Uric Acid are high-looking, while eGFR is low-looking by common clinical interpretation. |

### 6.3. `edge_case.json`

Contains 5 reports for testing boundary conditions:

| Report | `report_type` | Gender | Status | Notes |
| --- | --- | --- | --- | --- |
| `EDGE-ELECTROLYTES-0001` | `electrolytes_basic` | `male` | `draft` | Empty `indicators` array. |
| `EDGE-GLY-0002` | `glycemic_profile` | `unknown` | `draft` | Contains only one indicator, with a value using 3 decimal places. |
| `EDGE-CANCELLED-0003` | `liver_function_basic` | `female` | `cancelled` | Cancelled report with no indicators. |
| `EDGE-GENERAL-0004` | `general_health_check` | `male` | `final` | General report with only 25 indicators; many values are near typical thresholds. |
| `EDGE-RENAL-0005` | `renal_function_blood` | `female` | `draft` | Contains only `Creatinine`, with a value using 5 decimal places. |

## 7. Relationship Between Mock and Reference Data

When the Agent processes a report, the recommended flow is:

1. Read `report_type` to identify the report category and expected indicator set.
2. Iterate through `indicators[]`, then standardize `name` and `unit` using
   `units_metric.csv`.
3. If the metric exists in `metrics_range.json`, select the reference range by
   patient gender:
   - `male` -> prefer `gender = M`.
   - `female` -> prefer `gender = F`.
   - `unknown` -> use `gender = A` if available; otherwise do not classify by range.
4. Compare `value` with `lower_range` and `upper_range` to assign `low`,
   `normal`, or `high`.
5. Use the source fields when the Agent needs to explain where a range came from
   or audit why a threshold was selected.
6. Generate a natural-language explanation for the patient. If no reference
   range is available, say that the current dataset does not include a reference
   range instead of over-interpreting the result.

## 8. Validation Notes

- `indicators` may be empty, especially for `draft` or `cancelled` reports.
- `status = draft` does not mean the data is incorrect; it only means the report
  is not the final version.
- `status = cancelled` should be handled as a report that is not valid for
  medical explanation generation.
- A report may be missing indicators compared with its template, such as lipid
  reports missing `LDL-Cholesterol`.
- Some values include many decimal places. The Agent may round values when
  explaining them to patients, but should not modify the raw source value.
- `upper_range` may be empty in CSV and `null` in JSON for one-sided thresholds.
- Some rows represent clinical decision limits rather than healthy-population
  reference intervals. Check `special_note` and the source fields before
  presenting the result.
- Lipid ranges in `metrics_range.*` are stored as `mg/dL` to match mock data,
  even though the upstream source map stores lipid ranges as `mmol/L`.
- The unit `µmol/L` contains the micro sign. Make sure the data pipeline reads
  files as UTF-8.

## 9. AI Agent Usage

This dataset is suitable for:

- Testing JSON report schema parsing.
- Standardizing metric names and units.
- Comparing results against gender-specific reference ranges and decision-limit
  intervals.
- Detecting high, low, normal, borderline, or category-based values when ranges
  are available.
- Showing or auditing source provenance through `source_priority_tier`,
  `source_type`, `source_url`, and `evidence_location`.
- Generating concise explanations without diagnostic language.
- Testing missing data, draft reports, cancelled reports, and unknown gender
  handling.

The Agent should generate explanations that help patients understand their
results, but should not replace a clinician's diagnosis. For abnormal indicators
or reports with substantial missing data, the Agent should recommend discussing
the result with a healthcare professional.
