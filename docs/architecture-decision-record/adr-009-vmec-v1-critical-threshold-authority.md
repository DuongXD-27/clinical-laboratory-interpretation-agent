# ADR-009 — VMEC-05 V1 Critical Threshold Authority and Coverage

**Status:** ACCEPTED

**Human approval date:** 2026-08-14

**Decision owner:** Human Product/Technical Owner

**ADR number:** ADR-009

---

## Context

### Background

The VMEC-05 Critical Detector is responsible for identifying critical laboratory results (results that may require rapid clinical attention to avert significant patient morbidity or mortality) and generating emergency alerts requiring prompt clinician notification under declared laboratory policy. This is a safety-critical function — a false positive produces unnecessary alarm and alert fatigue; a false negative fails to alert when rapid clinical attention may be required.

Prior to Phase 2A/2B:

- `data/reference/critical_thresholds.json` contained numeric thresholds and units for 8 active analytes (Potassium, Glucose, WBC, HGB, LDL-C, HbA1c, HDL-C, Creatinine) plus an inactive RBC sentinel.
- None of these entries had any `source_url`, `citation`, `institution`, `revision`, `population`, `specimen`, or `operator` metadata.
- ADR-003 (2026-07-29) acknowledged that Potassium values were "temporary and not source-verified."
- The LDL-C critical high value (4.91 mmol/L) was found to be an exact numeric duplicate of a CDL category boundary (`EXPV2-LDLC-005.range_lower = 4.91 mmol/L`), indicating probable CDL contamination.

Phase 2A (audit document: [`docs/audit/VMEC05_CRITICAL_REGISTRY_SOURCE_AUDIT.md`](file:///d:/vin-ai/project/P-056/docs/audit/VMEC05_CRITICAL_REGISTRY_SOURCE_AUDIT.md)) audited the external medical provenance of all current registry values and found:

- **Potassium, Glucose, WBC, HGB, Creatinine:** recognized acute critical analytes with institutional variation in exact thresholds.
- **LDL-C, HbA1c, HDL-C:** absent from all reviewed hospital critical-value lists; no applicable critical-value rule was found in the sources reviewed during Phase 2A.
- **No analyte had a traceable declared operational source.**

Fix 1 (evidence: [`docs/version-handoff/fix1-critical-detector-safety-evidence.md`](file:///d:/vin-ai/project/P-056/docs/version-handoff/fix1-critical-detector-safety-evidence.md)) resolved detector software blockers: raw-name fallback removed, upstream `unknown` preserved, shared unit normalizer enforced. The software layer is now fail-closed.

Phase 2B (planning document: [`docs/audit/VMEC05_ARUP_REV46_CRITICAL_MIGRATION_PLAN.md`](file:///d:/vin-ai/project/P-056/docs/audit/VMEC05_ARUP_REV46_CRITICAL_MIGRATION_PLAN.md)) compared the current VMEC registry against ARUP Rev.46, identified exact source literals, operator semantics, and applicability qualifiers, and presented the mapping to the Human owner for a governance decision.

### Problem statement

A critical/emergency alert is a stronger claim than LOW/HIGH. Generating a critical alert without a declared operational authority is:

1. **Medically unsafe** — a hospital-specific policy threshold cannot be safely generalized to another product's patient population without explicit justification.
2. **Audit-incoherent** — different institutions use different thresholds; selecting arbitrarily produces an ungoverned hybrid.
3. **Anti-fabrication violating** — VMEC-05 requires grounded medical behavior; a critical alert without traceable source violates that requirement.

A single operational authority must therefore be declared, and its applicability qualifiers must be respected exactly.

---

## Decision

### CRIT-ARUP-02 — VMEC-05 V1 Critical Threshold Authority and Coverage

The following decisions were made by the Human Product/Technical Owner on **2026-08-14**. They are recorded here, not proposed by the AI.

**1. Single declared operational benchmark for VMEC-05 V1 Critical Detector:**

> ARUP Laboratories  
> *CRITICAL VALUES LIST*  
> Document ID: `CORP-APPEND-0104A`  
> Revision: **Rev. 46**  
> Date: **April 2026**  
> Official URL: https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf  

**2. No threshold mixing from other sources.**

VMEC-05 V1 will NOT combine thresholds from:
- Mayo Clinic
- University of Iowa (UIHC)
- Royal College of Pathologists (RCPath)
- Kost national surveys
- Vinmec educational articles
- ADA (American Diabetes Association)
- AHA/ACC (American Heart Association / American College of Cardiology)
- or any other sources

to fill gaps where ARUP Rev.46 does not provide a rule.

**3. Any analyte or critical side NOT defined by the applicable ARUP Rev.46 policy is INACTIVE in VMEC-05 V1.**

**4. ARUP rows explicitly marked:**

> "Test performed for University of Utah Health System only"

are NOT generalized to VMEC-05.

The Hemoglobin and White Blood Cell Count rows in ARUP Rev.46 carry this asterisk qualifier. They are therefore **NOT active VMEC-05 V1 critical rules.**

**5. V1 critical coverage for the current 9 analytes:**

| Analyte | Critical V1 state | Reason |
|---|---|---|
| **Potassium** | ELIGIBLE (pending implementation) | ARUP Rev.46 provides applicable, non-asterisked rule: `<3.0 / >6.1 mmol/L`. Operator and value migration required. |
| **Fasting plasma glucose** | ELIGIBLE (pending implementation and unit conversion policy) | ARUP Rev.46 provides applicable, non-asterisked rule for `Glucose >30 days to adult`: `<55 / >450 mg/dL`. Canonical analyte identity confirmed as the same measured substance; unit conversion policy required; mapping scope is Critical Detector only. |
| **WBC** | NO ACTIVE V1 CRITICAL RULE | ARUP Rev.46 row (White Blood Cell Count) is explicitly asterisked as University of Utah Health System only. |
| **HGB** | NO ACTIVE V1 CRITICAL RULE | ARUP Rev.46 Hemoglobin row is explicitly asterisked as University of Utah Health System only. |
| **LDL-C** | NO ACTIVE V1 CRITICAL RULE | Not listed in ARUP Rev.46. Previous value was likely CDL contamination. |
| **HbA1c** | NO ACTIVE V1 CRITICAL RULE | Not listed in ARUP Rev.46. No applicable critical-value rule found in reviewed sources. |
| **HDL-C** | NO ACTIVE V1 CRITICAL RULE | Not listed in ARUP Rev.46. No applicable critical-value rule found in reviewed sources. |
| **Creatinine** | NO ACTIVE V1 CRITICAL RULE | Not listed in ARUP Rev.46 (adult). |
| **RBC** | NO ACTIVE V1 CRITICAL RULE | ARUP Rev.46 contains no RBC-count critical rule. Current `-1/-1` is a legacy sentinel (technical debt). |

*Source literals for Potassium and Glucose are preserved from the ARUP document. Implementation-converted threshold numbers are NOT inserted here; they require separate approval in the implementation phase.*

**6. Critical-layer mapping for Glucose:**

ARUP's generic "Glucose" analyte label maps to the VMEC canonical "Fasting plasma glucose" **for Critical Detector evaluation only.**

The scope of this identity decision is: **CRITICAL_LAYER_ONLY.**

**7. This Critical-layer mapping MUST NOT be used to justify the existing Reference Range alias** (generic "Glucose" → "Fasting plasma glucose"). The issue of generic Glucose silently implying fasting in the Reference Range checker is a separate correctness problem and will be addressed in a separate fix.

**8. An inactive Critical rule does NOT mean the analyte is unsupported.**

Example:
- `LDL-C = abnormal` → Reference Range still classifies LOW/HIGH → explanation still generated → only emergency/critical escalation is inactive.
- `WBC = high` → Reference Range checker still evaluates it → critical escalation simply does not fire.

**9. Product priority:**

> Provenance + auditability + avoidance of false emergency alerts is prioritized over maximizing Critical Detector coverage in VMEC-05 V1.

---

## Layer Separation

The following layers are explicitly distinct and must not be conflated:

```
Reference Interval (RI) / Reference Range
    ≠
Critical / Panic Value (Critical Detector)
    ≠
Clinical Decision Bands / CDL categories
```

And critically:

```
inactive critical rule
    ≠
unsupported analyte
```

An analyte may be:
- Fully supported at the Reference Range layer (RI classification, explanation generation)
- Absent from the Critical Detector layer (no emergency alert triggered)

This is a deliberate and correct state for LDL-C, HbA1c, HDL-C, Creatinine, WBC, HGB, and RBC in VMEC-05 V1.

Furthermore:
- No clinical decision limit or CDL category boundary may be reused as a critical threshold without explicit critical-value provenance from a declared operational source.
- A value being HIGH or VERY HIGH on a RI or CDL scale does NOT automatically qualify it as a critical/panic value.

---

## Rationale

1. **VMEC-05 requires grounded medical behavior and anti-fabrication.** An emergency alert without a traceable, declared source violates the product's core correctness requirements, regardless of whether the number appears clinically plausible.

2. **A critical/emergency alert is a stronger claim than LOW/HIGH.** The critical flag signals a result that may require rapid clinical attention to avert significant patient morbidity or mortality and is designed to trigger urgent clinician notification under declared laboratory policy. It must not be activated without a declared institutional policy as authority.

3. **Institution-specific rules cannot be generalized without explicit justification.** The University of Utah qualifier on ARUP's Hemoglobin and WBC rows is not administrative boilerplate — it is an explicit applicability restriction. Generalizing it to VMEC-05 (a different product serving a different patient population) would be an unauthorized extension of scope.

4. **Mixing thresholds from multiple institutions creates a hybrid ungoverned registry.** No single institution would endorse the resulting combined policy. The product would be unable to declare which clinical authority it follows.

5. **Limited but well-grounded V1 coverage is acceptable.** The assignment explicitly cites extreme glucose and potassium as examples of critical-value detection. Delivering verified, traceable critical detection for these two analytes is a meaningful safety capability. Other analytes retain full Reference Range functionality.

6. **Under the selected ARUP Rev.46 operational benchmark, LDL-C, HbA1c, and HDL-C have no active VMEC-05 V1 critical rule.** No applicable critical-value rule for these analytes was found in the sources reviewed during Phase 2A. Their deactivation in the V1 critical registry eliminates unverified alert triggers.

---

## Rejected Alternatives

### A. Mix thresholds from multiple institutions
**Rejected.** Mixing Mayo, RCPath, UIowa, ARUP, or Kost survey values creates a hybrid policy with no coherent operational authority. No institution endorses the resulting combination. Each institution's values are calibrated against their own patient population, instrumentation, and clinical context.

### B. Generalize University of Utah-only rows (ARUP WBC and HGB)
**Rejected.** The ARUP document explicitly restricts these rows to the University of Utah Health System. Applying them to VMEC-05 would violate the stated applicability scope of the source document.

### C. Keep old thresholds because they appear clinically plausible
**Rejected.** Plausibility is not provenance. A threshold that happens to fall within a commonly observed range still requires a declared operational authority. Deploying untraced thresholds that trigger emergency alerts is a patient safety risk.

### D. Disable the entire Critical Detector
**Rejected.** ARUP Rev.46 provides directly applicable, non-asterisked rules for Potassium and Glucose. The project explicitly requires demonstration of critical-value detection capability. Disabling all critical evaluation when valid evidence exists would reduce safety unnecessarily.

---

## Implementation Implications

**This ADR does not implement any changes.** The following work items are required in the Phase 2B implementation sprint and are explicitly deferred:

1. **Operator encoding:** Implement strict operator support (`<`, `<=`, `>`, `>=`) in the critical threshold schema and detector. Current VMEC detector uses inclusive comparison for all sides; ARUP uses strict operators for Potassium and Glucose.

2. **Sentinel removal:** Replace `-1.0` inactive-side sentinels with explicit `null` or schema-level `active: false`. The `-1` encoding is an implicit convention that breaks type safety and requires runtime guards.

3. **Provenance attachment:** Add `source_id`, `source_revision`, `source_date`, `source_url`, `source_analyte_label`, `source_low_operator`, `source_high_operator`, `population`, and `specimen` fields to each active critical threshold entry.

4. **Alias deduplication:** Remove alias key duplication (`"Kali"`, `"Hemoglobin"`, `"Fasting Plasma Glucose"`) from `critical_thresholds.json`. The canonical-only detector (Fix 1) makes alias entries redundant and potentially inconsistent.

5. **Glucose unit conversion policy:** No raw cross-unit numeric comparison. Critical comparison may execute only when: A. input unit and threshold unit normalize to the same canonical unit, OR B. an explicitly approved, analyte-specific deterministic conversion has converted one measurement into the other unit under the documented V1 conversion policy.

Raw numeric values expressed in different units must never be compared
directly.

If neither canonical equivalence nor an approved conversion exists:
fail closed.

6. **Source literal preservation:** The production JSON must store the source literal alongside the converted operational value. The source literal must not be overwritten by the conversion result.

7. **Fail-closed behavior:** Preserve all Fix 1 safety invariants (no raw-name fallback, no upstream unknown override, shared unit normalizer only).

8. **Critical golden tests:** Update `tests/test_agents/test_critical_detector_node.py` to:
   - Prove ARUP-derived Potassium boundary semantics with correct operators.
   - Prove ARUP-derived Glucose boundary semantics with correct operators and converted values.
   - Prove WBC/HGB/LDL-C/HbA1c/HDL-C/Creatinine produce no critical alert.
   - Prove RBC remains inactive.

---

## Safety Invariants

The following invariants are binding and must not be violated in any future implementation or configuration change:

1. **No active critical threshold without a declared operational source.** Every entry in the critical registry must have an attached `source_id` pointing to a declared benchmark document.

2. **No secondary-source gap filling.** If the declared benchmark does not define a rule for an analyte or side, that entry is inactive. Other sources may not be used to fill the gap without a new ADR and new Human approval.

3. **No raw-name critical bypass.** Canonicalization failure → critical evaluation does not run. (Established in Fix 1; must be preserved.)

4. **No raw cross-unit numeric comparison.** Critical comparison is performed only when the normalized input unit matches the normalized threshold unit. Unit mismatch → fail closed. (Established in Fix 1; must be preserved.)

5. **Upstream unknown cannot become critical.** If the Reference Range checker returns `status = "unknown"`, the Critical Detector must preserve that status and not escalate. (Established in Fix 1; must be preserved.)

6. **Missing critical rule means NOT_EVALUATED_FOR_CRITICAL, not medically "safe."** The absence of a critical rule does not imply the measured value is clinically safe. It means the system does not have enough declared policy to evaluate critical status.

7. **LOW/HIGH must not automatically become CRITICAL.** A Reference Range classification of HIGH does not qualify an analyte for critical escalation. Critical escalation requires a separate, declared critical threshold.

8. **No clinical decision boundary may be reused as a critical threshold without explicit critical provenance.** CDL bands (e.g., LDL-C "very_high" at 4.91 mmol/L) are clinical decision categories, not critical/panic thresholds. Copying a CDL value into the critical registry without declared critical-value provenance constitutes POSSIBLE_CDL_CONTAMINATION.

---

## Validation / Acceptance Criteria

This ADR is satisfied when all of the following are true:

- [ ] The declared operational source is ARUP Rev.46 (`CORP-APPEND-0104A`), and no other source has contributed threshold values.
- [ ] Only source-applicable rules (non-asterisked rows) are active in the VMEC-05 V1 critical registry.
- [ ] ARUP's exact operators (`<`, `>`) are encoded as strict comparisons in the detector.
- [ ] Each active critical entry has an attached provenance record.
- [ ] The `-1.0` sentinel encoding no longer exists in `critical_thresholds.json`.
- [ ] Alias keys (`"Kali"`, `"Hemoglobin"`, `"Fasting Plasma Glucose"`) are not present as independent records in `critical_thresholds.json`.
- [ ] Golden tests verify exact boundary semantics for Potassium and Glucose.
- [ ] Golden tests verify that WBC, HGB, LDL-C, HbA1c, HDL-C, Creatinine, and RBC produce no critical alert.
- [ ] Reference Range classification behavior is independent of the Critical Detector layer.

---

## Consequences

### Positive
- **Traceable:** Every active critical threshold is backed by a named document with revision and date.
- **Deterministic:** A single operational authority eliminates threshold ambiguity.
- **Auditable:** Source literals, operators, and provenance metadata can be inspected and verified independently.
- **Prevents false emergency alerts:** LDL-C, HbA1c, HDL-C, WBC (U of U only), and HGB (U of U only) no longer generate critical alerts.
- **Prevents source mixing:** The registered benchmark is authoritative and complete; no hybrid policy.

### Negative / Trade-offs
- **Lower critical coverage in V1:** Only Potassium and Glucose are eligible for active critical rules in the current 9 analytes.
- **WBC and HGB critical alerts unavailable in V1:** These analytes retain Reference Range support but will not generate critical alerts under the ARUP-only, U-of-U-excluded policy.
- **Operational benchmark is a demo authority, NOT a Vinmec clinical SOP:** ARUP Rev.46 is the selected V1 operational authority to enable a traceable demonstration. If VMEC-05 is deployed in production at Vinmec, a formally endorsed Vinmec Laboratory critical-value policy must replace or supplement ARUP Rev.46 via a new ADR.

---

## Future Work

**Post-V1 / V2 roadmap item:**

> Evaluate a single alternative authoritative adult critical-value benchmark — or a validated target-laboratory/Vinmec Laboratory official critical-results policy — if broader Critical Detector coverage is required. Do not combine multiple operational sources within the same registry layer without a new ADR and new Human approval.

Specifically:
- WBC and HGB critical rules would require either a non-restricted ARUP-equivalent source or an explicitly validated Vinmec lab policy.
- Creatinine critical rules would require an adult-applicable source (Mayo provides pediatric only; RCPath G158 is currently in draft).
- Any future 9→25 analyte expansion must repeat this same governance process for each new critical analyte.

---

## Referenced Documents

| Document | Role |
|---|---|
| [`docs/audit/VMEC05_CRITICAL_REGISTRY_SOURCE_AUDIT.md`](file:///d:/vin-ai/project/P-056/docs/audit/VMEC05_CRITICAL_REGISTRY_SOURCE_AUDIT.md) | Phase 2A — External provenance verification for all current 9 analytes |
| [`docs/audit/VMEC05_ARUP_REV46_CRITICAL_MIGRATION_PLAN.md`](file:///d:/vin-ai/project/P-056/docs/audit/VMEC05_ARUP_REV46_CRITICAL_MIGRATION_PLAN.md) | Phase 2B — ARUP Rev.46 source-literal extraction, VMEC mapping, and per-analyte migration plan |
| [`docs/version-handoff/fix1-critical-detector-safety-evidence.md`](file:///d:/vin-ai/project/P-056/docs/version-handoff/fix1-critical-detector-safety-evidence.md) | Fix 1 — Critical Detector software safety evidence and blocker resolution |
| [`docs/architecture-decision-record/adr-003-critical-value-detection.md`](file:///d:/vin-ai/project/P-056/docs/architecture-decision-record/adr-003-critical-value-detection.md) | ADR-003 — Rule-based critical detection architecture decision |
| [`docs/architecture-decision-record/adr-005-basic-critical-value.md`](file:///d:/vin-ai/project/P-056/docs/architecture-decision-record/adr-005-basic-critical-value.md) | ADR-005 — Critical detection classified as basic (V1) requirement |
| [`data/reference/critical_thresholds.json`](file:///d:/vin-ai/project/P-056/data/reference/critical_thresholds.json) | Current critical registry (pre-migration; to be replaced in Phase 2B implementation) |
