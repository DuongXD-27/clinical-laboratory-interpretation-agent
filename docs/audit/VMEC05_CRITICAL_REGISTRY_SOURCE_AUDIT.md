# VMEC-05 — Phase 2A Critical Registry Source Audit (Correction Pass)

**Task:** VMEC-05 Phase 2A source audit correction pass
**Audit date:** 2026-08-14
**Scope:** `data/reference/critical_thresholds.json`
**Change constraint:** documentation only; no code, data/config, or threshold changes
**Decision state:** no Human source-policy or analyte-specific decision has been made

---

## 1. Corrected executive finding

The repository provides **no traceable production provenance** for any active critical threshold. The current JSON contains numbers and units but no source URL, citation, institution, document version, population, specimen, or operator metadata. External similarity is supporting evidence only. It does not make an external document the declared operational source for VMEC-05.

These statements are deliberately distinct:

1. **External occurrence:** a number appears in an external laboratory policy or professional guidance.
2. **VMEC production provenance:** that exact document has been selected by a Human as the operational authority for VMEC-05, with its population, specimen, units, and operators adopted consistently.

Only statement 2 can establish production provenance. It is currently false for every active analyte.

The previous unconditional `KEEP_ACTIVE` recommendations are withdrawn. No operational critical source has been selected, and no production critical value is ready for approval.

---

## 2. Current repository state

The runtime compares inclusively: `value <= low` and `value >= high`. A configured `-1.0` side is inactive because the runtime first requires the threshold to be non-negative.

| Canonical analyte | Current registry threshold | Runtime operator | Active? | Repository provenance |
|---|---:|---|---|---|
| Potassium | 2.5 / 6.5 mmol/L | `<=` / `>=` | Yes | **NONE** |
| Glucose | 3.0 / 27.8 mmol/L | `<=` / `>=` | Yes | **NONE** |
| WBC | 2.5 / 30.0 ×10^9/L | `<=` / `>=` | Yes | **NONE** |
| HGB | 60 / 200 g/L | `<=` / `>=` | Yes | **NONE** |
| LDL-C | high 4.91 mmol/L | `>=` | Yes | **NONE** |
| HbA1c | high 9.0% | `>=` | Yes | **NONE** |
| HDL-C | 0.7 / 2.1 mmol/L | `<=` / `>=` | Yes | **NONE** |
| Creatinine | high 353.6 µmol/L | `>=` | Yes | **NONE** |
| RBC | -1.0 / -1.0 ×10^12/L | inactive sentinel | No | **NONE** |

Internal evidence does not cure the missing provenance:

- ADR-003 describes the Potassium numbers as temporary and not source-verified.
- `critical_thresholds.json` has no provenance fields for any entry.
- `critical_thresholds.json` LDL-C high is exactly `4.91 mmol/L`, and CDL rule `EXPV2-LDLC-005.range_lower` is exactly `4.91 mmol/L`.

The LDL-C equality is **STRONG_EVIDENCE_OF_POSSIBLE_CDL_CONTAMINATION**. It does not prove copying or historical causation because no supporting commit, authorship record, or documentation was found. The classification therefore remains **POSSIBLE_CDL_CONTAMINATION**, not confirmed contamination.

---

## 3. Verified source pack

Only directly inspectable, specific official documents/pages are retained in the authoritative evidence set. The previous generic Stanford homepage, merged Kost 1990/1993 record, generic RCPath homepage/version description, and generic Ministry homepage are removed from this source pack. Their earlier numeric claims are not relied upon here.

### SRC-CRIT-001 — RCPath

- **Organization:** The Royal College of Pathologists
- **Exact title:** *Best practice recommendations: The communication of critical and unexpected pathology results*
- **Document identifier:** G158
- **Exact version/revision:** Version 2; document footer `PGD 270325 ... V2 Draft`
- **Publication/date active:** March 2025
- **Review date shown:** March 2030
- **Status:** **DRAFT 2025**, consultation 27 March 2025 to 24 April 2025; not a finalized 2017/2020 document
- **Exact URL:** https://www.rcpath.org/static/f800366a-e432-47d0-9114154f8a51d3b1/draft-G158-BPR-The-communication-of-critical-and-unexpected-pathology-results.pdf
- **Source terminology:** suggested cut points/thresholds and **action limits** for rapid communication; type A means rapid communication within two hours, usually by telephone
- **Population/specimen:** clinical biochemistry table is adult serum/plasma unless otherwise stated; haematology table gives suggested criteria for local SOPs
- **Exact relevant analytes present:** K, Creatinine, Glucose, Haemoglobin, Neutrophils, Lymphocytes
- **Not present as numeric total-count rules:** total WBC
- **Not found:** LDL-C, HbA1c, HDL-C, RBC count

Literal values and operators:

- The chemistry table prints K `2.5 / 6.5 mmol/L`, Creatinine upper `354 µmol/L`, and Glucose `2.5 / 25 mmol/L`. Footnote (a) says lower and upper action-limit cut points are assumed to be `<=` and `>=`, respectively.
- Haemoglobin is explicitly `<50 g/L` for microcytic/macrocytic anaemia, `<70 g/L` for normochromic/normocytic presentations, and `>190 g/L` at the high side with contextual qualification.
- The haematology table does **not** supply VMEC-style total WBC limits. It lists Neutrophils `<0.5 ×10^9/L` and `>50 ×10^9/L`, and Lymphocytes `>50 ×10^9/L`. These are not interchangeable with total WBC.

Suitability: authoritative professional supporting evidence, but currently a draft and explicitly designed for local adaptation. It cannot be VMEC production provenance unless a Human declares it as the benchmark and accepts its draft status and exact semantics.

### SRC-CRIT-002 — Mayo Clinic Laboratories

- **Organization:** Mayo Clinic Laboratories, Department of Laboratory Medicine and Pathology
- **Exact title:** *Mayo Clinic Laboratories Critical Values / Semi-Urgent Results List*
- **Exact version/revision:** no revision number printed
- **Update date:** Updated June 2026
- **Status:** **FINAL/current list**; the landing page warns that values are valid only on the day of printing
- **Exact URL:** https://www.mayocliniclabs.com/-/media/it-mmfiles/Special-Instructions/4/2/A/critical-values-semi-urgent-results-list.pdf
- **Source terminology:** **Critical Value / Critical Result** and **Semi-Urgent Result**; these terms have separate definitions in the document
- **Scope:** testing performed at Rochester, Arizona, Florida, Mayo Clinic Health System, and Mayo Clinic Laboratories performing sites
- **Exact relevant analytes present:** Hemoglobin, Leukocytes, Absolute Neutrophil Count, Neutrophils, Creatinine (pediatric ages only), Glucose, Potassium
- **Not found:** LDL-C, HbA1c, HDL-C, RBC count

Literal critical values and operators:

- Hemoglobin: age 0–7 weeks `<=6.0` or `>=24.0 g/dL`; age >7 weeks `<=6.0` or `>=20.0 g/dL`.
- Leukocytes: high only `>=100.0 ×10^9/L`; the source label is **Leukocytes**.
- Absolute Neutrophil Count and Neutrophils: low only `<=0.5 ×10^9/L`.
- Creatinine, blood/plasma/serum: pediatric-only high values through age 17 (`>=1.5`, `>=2.0`, `>=2.5`, `>=3.0`, and `>=10.0 mg/dL` by age band). **No adult creatinine critical value is present.**
- Glucose, plasma/serum: `<4 weeks: <=40 or >=400 mg/dL`; `>=4 weeks: <=50 or >=400 mg/dL`.
- Potassium: `<=2.5` or `>=6.0 mmol/L`.

Suitability: a current institutional critical-values policy and strong supporting evidence for analytes/populations actually listed. It is not adult creatinine provenance and does not establish VMEC provenance unless selected by a Human.

### SRC-CRIT-003 — ARUP Laboratories

- **Organization:** ARUP Laboratories
- **Exact title:** *CRITICAL VALUES LIST*
- **Exact version/revision:** `CORP-APPEND-0104A, Rev. 34`
- **Publication/update date:** April 2019
- **Status:** **FINAL** official list; no draft marking
- **Exact URL:** https://www.aruplab.com/Testing-Information/resources/PDF_Brochures/ARUP_Critical_Values.pdf
- **Source terminology:** **critical values**; ARUP separately defines alert values on its official Critical and Alert Values page
- **Exact relevant analytes present:** Potassium, Glucose, Hemoglobin, White Blood Cell Count
- **Not found in the inspected critical list:** Creatinine, LDL-C, HbA1c, HDL-C, RBC count

Literal values and operators:

- Potassium `<3.0` or `>6.1 mmol/L`.
- Glucose `<55` or `>450 mg/dL`.
- Hemoglobin `<=7.0` or `>21.0 g/dL`.
- White Blood Cell Count `<=2.0` or `>=40 ×10^3/µL` (numerically equivalent to ×10^9/L).

Suitability: directly inspectable official institutional critical-value evidence. Its 2019 revision must not be mislabeled as 2024/2026. It is not VMEC provenance unless selected by a Human.

### SRC-CRIT-004 — University of Iowa Health Care

- **Organization:** University of Iowa Health Care, Department of Pathology
- **Exact page title:** *Critical Laboratory Tests and Values*
- **Version/revision:** not stated on the page
- **Publication/update date:** not stated on the page; inspected 2026-08-14
- **Status:** **FINAL/current live institutional page**; no draft marking
- **Exact URL:** https://www.healthcare.uiowa.edu/path_handbook/appendix/common/un_crit_lab_val.html
- **Source terminology:** **critical tests**, **critical values**, and separately identified **significant values**
- **Exact relevant analytes present:** Potassium, Glucose, Hemoglobin, White Blood Count
- **Not found on the inspected critical-values page:** Creatinine, LDL-C, HbA1c, HDL-C, RBC count

Literal values and operators:

- Chemistry table headings are **Less Than / Greater Than**: adult Potassium `<2.8 / >6.2 mEq/L`; Glucose age >1 month through adults `<50 / >450 mg/dL`.
- Haematology table headings are **Less Than or Equal to / Greater Than or Equal to**: Hemoglobin `<=6 / >=22 g/dL` (with `<7` noted for outpatients at the low side); White Blood Count `<=1.0 / >=50.0 k/mm3`.

Suitability: directly inspectable current institutional evidence. It does not provide a published revision/date and is not VMEC provenance unless selected by a Human.

---

## 4. Exact official-source comparison

Conversions below are explanatory only; the source literal and source operator remain controlling. Operators are never normalized silently.

| Analyte | VMEC inclusive runtime | RCPath V2 DRAFT 2025 | Mayo updated Jun 2026 | ARUP Rev. 34 Apr 2019 | UIowa current page |
|---|---|---|---|---|---|
| Potassium | `<=2.5 / >=6.5 mmol/L` | `<=2.5 / >=6.5 mmol/L` | `<=2.5 / >=6.0 mmol/L` | `<3.0 / >6.1 mmol/L` | adult `<2.8 / >6.2 mEq/L` |
| Glucose | `<=3.0 / >=27.8 mmol/L` | `<=2.5 / >=25 mmol/L` | age >=4 weeks `<=50 / >=400 mg/dL` (~`<=2.78 / >=22.2 mmol/L`) | `<55 / >450 mg/dL` (~`<3.05 / >25.0 mmol/L`) | >1 month–adult `<50 / >450 mg/dL` (~`<2.78 / >25.0 mmol/L`) |
| HGB | `<=60 / >=200 g/L` | `<50` or `<70`; high `>190 g/L` | >7 weeks `<=6 / >=20 g/dL` (= `<=60 / >=200 g/L`) | `<=7 / >21 g/dL` | `<=6 / >=22 g/dL` (low `<7` for outpatients) |
| Creatinine | `>=353.6 µmol/L` | adult `>=354 µmol/L` | pediatric only through 17; no adult value | absent | absent |

### Operator mismatches requiring later Human decision

- **Potassium:** VMEC matches RCPath draft operators and values. ARUP and UIowa use strict `<`/`>` and different values; VMEC uses inclusive `<=`/`>=`. Mayo uses inclusive operators but has a different high value.
- **Glucose:** VMEC uses inclusive operators. ARUP and UIowa use strict `<`/`>`; RCPath and Mayo use inclusive operators. All four reviewed source pairs differ numerically from VMEC.
- **HGB:** VMEC exactly matches Mayo's >7-week values and inclusive operators. RCPath and ARUP use strict operators for at least one side; UIowa uses inclusive operators but a different high value.
- **Creatinine:** RCPath draft and VMEC both use `>=`, but the literal thresholds differ (`354` versus `353.6 µmol/L`). The 0.4 difference cannot be silently treated as exact. Mayo is pediatric-only and cannot support VMEC's unspecified/adult population.

Every mismatch remains a Human decision item, but only after source policy selection.

---

## 5. WBC re-check

WBC, leukocytes, neutrophils, and lymphocytes are recorded exactly as named. Neutrophil and lymphocyte counts are cell subsets and are not substituted for total WBC.

| Source | Source analyte label | Low | High | Operator semantics | Comparison with VMEC WBC 2.5 / 30 ×10^9/L |
|---|---|---:|---:|---|---|
| VMEC | WBC | 2.5 | 30 | `<=` / `>=` | Current unproven registry value |
| Mayo | Leukocytes | absent | 100 | `>=` | Different label and high value; no low total-count limit |
| Mayo | Absolute Neutrophil Count / Neutrophils | 0.5 | absent | `<=` | Cell subset; not WBC |
| ARUP | White Blood Cell Count | 2.0 | 40 | `<=` / `>=` | Same total-count concept; both values differ |
| UIowa | White Blood Count (WBCT) | 1.0 | 50 | `<=` / `>=` | Same total-count concept; both values differ |
| RCPath V2 DRAFT 2025 | Neutrophils | 0.5 | 50 | `<` / `>` | Cell subset; not WBC |
| RCPath V2 DRAFT 2025 | Lymphocytes | absent | 50 | `>` | Cell subset; not WBC |

Conclusion: current official lists confirm that communication policies vary by institution, but none of the reviewed current official lists provides the VMEC total-WBC pair `<=2.5 / >=30`. WBC is classified **INSTITUTION_SPECIFIC_VARIATION** at the analyte-policy level, with only **MODERATE** external evidence for including total WBC in some policies and **WEAK** evidence for VMEC's exact numbers. This does not justify `KEEP_ACTIVE`; the recommendation is `SUSPEND_PENDING_OPERATIONAL_SOURCE`.

---

## 6. LDL-C, HbA1c, HDL-C, and RBC absence review

The precise finding for LDL-C, HbA1c, and HDL-C is:

**NO_CRITICAL_VALUE_FOUND_IN_REVIEWED_SOURCES**

The reviewed critical/action-limit lists were:

1. RCPath G158 Version 2 **DRAFT**, March 2025.
2. Mayo Clinic Laboratories *Critical Values / Semi-Urgent Results List*, updated June 2026.
3. ARUP *CRITICAL VALUES LIST*, Rev. 34, April 2019.
4. University of Iowa *Critical Laboratory Tests and Values*, current live page inspected 2026-08-14.

None contains LDL-C, HbA1c, or HDL-C as a critical/action-limit entry. This is a bounded absence claim about the four inspected lists. It is not a claim that no critical value exists anywhere or could ever exist.

RBC has no active VMEC threshold (`-1/-1` sentinel), and no RBC-count critical entry was found in those four lists. References to red blood cells in transfusion/blood-bank text are not numeric RBC-count critical thresholds.

For LDL-C specifically, the exact `4.91` equality between the critical registry and CDL rule is strong evidence of possible contamination, but causation is unproven. The proper wording is **POSSIBLE_CDL_CONTAMINATION**.

---

## 7. Corrected decision model

`OPERATIONAL_SOURCE_SELECTED` is **NO** for every analyte. Consequently, no unconditional `KEEP_ACTIVE` recommendation is permitted.

| Analyte | REPOSITORY_PROVENANCE | EXTERNAL_EVIDENCE | OPERATIONAL_SOURCE_SELECTED | CURRENT_REGISTRY_RECOMMENDATION | Basis |
|---|---|---|---|---|---|
| Potassium | NONE | STRONG | NO | **CANDIDATE_KEEP_IF_SOURCE_APPROVED** | RCPath draft exactly matches values/operators; Mayo matches low only; no source selected |
| Glucose | NONE | MODERATE | NO | **SUSPEND_PENDING_OPERATIONAL_SOURCE** | Recognized on all four lists, but no reviewed source matches VMEC's full pair and operators |
| WBC | NONE | WEAK | NO | **SUSPEND_PENDING_OPERATIONAL_SOURCE** | ARUP/UIowa total-WBC limits differ; Mayo/RCPath subset/label distinctions prevent substitution |
| HGB | NONE | STRONG | NO | **CANDIDATE_KEEP_IF_SOURCE_APPROVED** | Mayo >7-week values and inclusive operators exactly match VMEC; source still undeclared |
| Creatinine | NONE | MODERATE | NO | **SUSPEND_PENDING_OPERATIONAL_SOURCE** | RCPath draft has `>=354`, not `>=353.6`; Mayo is pediatric-only; ARUP/UIowa absent |
| LDL-C | NONE | NONE | NO | **REMOVE_CANDIDATE_PENDING_HUMAN_APPROVAL** | Possible CDL contamination; no critical value found in reviewed sources |
| HbA1c | NONE | NONE | NO | **REMOVE_CANDIDATE_PENDING_HUMAN_APPROVAL** | No critical value found in reviewed sources |
| HDL-C | NONE | NONE | NO | **REMOVE_CANDIDATE_PENDING_HUMAN_APPROVAL** | No critical value found in reviewed sources |
| RBC | NONE | NONE | NO | **REMOVE_CANDIDATE_PENDING_HUMAN_APPROVAL** | Runtime-inactive sentinel; no numeric RBC-count critical value found in reviewed sources |

`CANDIDATE_KEEP_IF_SOURCE_APPROVED` means only that an exact external analogue exists. It is not `KEEP_ACTIVE`, does not select that source, and does not establish VMEC provenance.

---

## 8. Human-selectable project source policies

No policy is selected by this audit.

### POLICY A — TARGET LAB POLICY

Use an official Vinmec or target-laboratory validated critical-values list.

Consequences:

- Best alignment with the actual laboratory workflow, patient population, instruments, specimens, escalation paths, and local clinical governance.
- Every threshold must be traced to the exact approved local SOP version.
- If that policy is unavailable or an analyte is absent, the affected VMEC threshold remains suspended.

### POLICY B — DECLARED EXTERNAL DEMO BENCHMARK

A Human explicitly selects one authoritative source/document/version as the VMEC-05 V1 research/demo benchmark.

Consequences:

- Operators, population, specimen, units, age bands, terminology, and numeric values must be adopted consistently from that document; mixing institutions under one source policy is not allowed without an explicit composite-policy decision.
- The UI must disclose that the thresholds are demo benchmark values, not proven Vinmec SOP values.
- Draft status matters: selecting RCPath March 2025 would explicitly select a draft benchmark.
- Analytes absent from the selected benchmark remain suspended unless separately governed by an approved policy.

### POLICY C — NO CRITICAL FEATURE UNTIL LOCAL POLICY

Suspend critical rules until a declared local operational source exists.

Consequences:

- Avoids presenting unproven thresholds as operational medical policy.
- Removes the current critical-alert behavior for affected rules while preserving non-critical RI/CDL processing as separately governed.
- Critical detection can be re-enabled only after source selection, clinical review, version capture, and operator/population/specimen validation.

---

## 9. Correct Human decision queue

### CRIT-POLICY-01 — VMEC-05 V1 critical threshold authority

This is the first and only decision currently ready for Human selection:

- [ ] **A. Vinmec/target lab policy** — use an approved local policy; suspend affected thresholds if unavailable.
- [ ] **B. One declared external benchmark** — select one exact authoritative document/version for the research/demo benchmark and adopt it consistently.
- [ ] **C. Suspend critical feature until local source exists** — keep critical rules suspended until a local operational source is available.

Do **not** ask analyte-specific questions such as “2.5/6.5 or 2.8/6.2?” yet. Numeric, operator, population, specimen, and unit decisions are downstream of `CRIT-POLICY-01` and must be generated only after that policy decision.

---

## 10. Scope guard and final status

No source reviewed here has been silently relabeled: RCPath values remain action limits/suggested criteria for rapid communication; Mayo and ARUP values remain critical values/results; UIowa terminology remains critical or significant according to its page. Supporting suitability for a VMEC Critical Detector is assessed separately from terminology.

- **PHASE_2A_SOURCE_AUDIT_CORRECTED = YES**
- **EXTERNAL_SOURCES_VERSION_VERIFIED = YES**
- **UNVERIFIED_SOURCE_ENTRIES_REMAIN = NO**
- **VMEC_OPERATIONAL_CRITICAL_SOURCE_SELECTED = NO**
- **PRODUCTION_CRITICAL_VALUES_READY_FOR_APPROVAL = NO**
- **READY_FOR_CRITICAL_SOURCE_POLICY_DECISION = YES**
- **CRITICAL_THRESHOLD_DATA_CHANGED = NO**
- **CODE_CHANGED = NO**
