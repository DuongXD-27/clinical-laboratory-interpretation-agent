# REFERENCE DATA CONTRACT V1 — PROPOSAL

Status: Human-approved design decisions incorporated; ready for final document approval; no implementation authorized  
Date: 2026-08-14  
Inputs reviewed: current repository code/data and `VMEC05_DATA_AUDIT_V1.md`  
Scope: Reference Interval (RI) and Clinical Decision Limit/Band (CDL) for the frozen Core 25  
Explicitly out of scope: critical/panic thresholds, medical threshold changes, source replacement, approval-list changes, RAG content

## A. Current Problem

### A.1 P0-02 — CDL rules are silently discarded

The current config allows only RI:

```json
{
  "allowed_reference_types": ["RI"]
}
```

`ReferenceRepository.select_rule()` filters candidates by this set before unit, age and sex selection (`src/services/reference_repository.py:238-242`). Consequently:

- Fasting plasma glucose, HbA1c, LDL-C, HDL-C and Potassium collapse to one RI; their CDL records never participate in classification.
- Total cholesterol and Triglyceride are CDL-only, so they have no usable rule even if canonical alias and runtime approval are later added.
- Simply changing the config to include `CDL` is unsafe. The current resolver expects one demographic rule, does not evaluate the value across bands, and returns `ambiguous_reference_rule` when multiple candidates remain (`reference_repository.py:263-267`).

The current state model hints at a detailed `category`, but runtime does not populate it from CDL (`src/agents/state.py:28-34`). The API, history model and frontend still expose one overloaded `status` (`src/models/schemas.py:151-171`, `src/models/db.py:237-244`, `frontend/src/types/analysis.ts:8-19`). The critical detector later overwrites that same status with `critical_low`/`critical_high`, so three distinct meanings are currently compressed into one field.

### A.2 P0-03 — Boundary semantics are unresolved

Rules currently carry `range_lower` and `range_upper` but no lower/upper inclusive flags. Runtime RI classification hard-codes an inclusive interval and serializes a legacy three-state value based on whether the measurement is below, within or above that interval (`src/agents/nodes/reference_range_checker_node.py:68-83`). That legacy vocabulary and convention cannot safely represent the V1 RI/CDL contract.

The audit found:

- exact same-system overlaps, such as HbA1c 5.7 and Potassium 3.0/7.0;
- exact gaps, such as Triglyceride 2.25 and 5.64 and HDL-C 1.54 after declared two-decimal conversion;
- adjacent decimal boundaries whose completeness depends on an unstated precision policy;
- RI/CDL numeric overlap that is not inherently a conflict because RI and CDL answer different questions.

The required correction is a data contract and two selection algorithms, not a precedence rule between RI and CDL.

## B. Design Principles

### B.1 Normative invariants

```text
RI != CDL
CDL != Critical
RI and CDL may both classify the same canonical measurement
No RI-over-CDL or CDL-over-RI precedence
WITHIN_REFERENCE does not mean clinically normal and must not override a CDL classification
Critical classification remains an external subsystem
No implicit boundary operators
No numeric sentinel
No first-record-wins behavior
One value matches at most one active band per band_system_id
Multiple band systems may return parallel classifications
Unit conversion is explicit and traceable
Rounding is never implicit
Default precision is RAW with no rounding
Active rules are source-traceable
Runtime consumes structured bounds, never source_range_text
Only context explicitly required by an ACTIVE rule is mandatory
ANY and A applicability values do not create caller-context requirements
V1 supported age scope is 18 through 60 inclusive; it is not unrestricted Adult coverage
Generic analyte naming must not create clinical context
"Glucose" must not create fasting=true
Invalid or ambiguous data fails closed to UNKNOWN/AMBIGUOUS
```

### B.2 Answers to the required design questions

1. **Separate `reference_status` and `clinical_band`: yes.** RI answers `BELOW_REFERENCE`/`WITHIN_REFERENCE`/`ABOVE_REFERENCE` relative to an interval. CDL assigns a source-defined diagnostic/risk/stage/target category. They are parallel results.
2. **Keep the concept behind `clinical_band_type`, but revise it.** A free-form singular field is insufficient. Use required `band_system_id` and a controlled `band_system_kind` per clinical system.
3. **RI + CDL simultaneous match: yes.** This is a normal result, not a resolver conflict.
4. **Multiple CDL matches: across different `band_system_id` values, yes; within one system, no.** Each system returns its own result.
5. **Source overlap inside one active system:** dataset validation must fail before activation. If corrupted data still reaches runtime, return `AMBIGUOUS`, include all candidate rule IDs, and do not select by order or priority.
6. **`UNKNOWN`:** the engine was expected to classify but could not do so safely—unsupported analyte/unit, missing conversion/context, invalid value, no applicable rule despite an RI/system existing, ambiguous rules, incomplete policy, or invalid ruleset.
7. **`NOT_APPLICABLE`: yes.** It means the dimension is intentionally absent, for example a CDL-only analyte with no RI. It must not mean missing data or failure.
8. **Expose `rule_id`: yes.** Matched and conflicting candidate IDs are required for traceability, tests and history snapshots.
9. **Required context is rule-declared:** a caller field is mandatory only when a potentially applicable `ACTIVE` rule requires a concrete value. `specimen=ANY`, `fasting_requirement=ANY` and `sex=A` match without inventing or requiring the corresponding caller context.
10. **Supported population is explicit:** current V1 reviewed scope is `18 <= age <= 60`. A known age outside all reviewed rules is not missing context; it is `UNKNOWN / OUTSIDE_SUPPORTED_POPULATION`.
11. **Canonical names do not manufacture context:** explicit fasting analyte names may resolve directly to Fasting plasma glucose. Generic names such as `Glucose` or `Đường huyết` cannot imply fasting and require fasting evidence plus an explicit reviewed canonicalization policy before resolving to FPG.

### B.3 Minimum-change posture

The proposal retains the current flat rule catalog and existing core fields. It adds the minimum fields needed for executable semantics. It does not require a new database, service, module or dependency. A future implementation may initially load a V1 contract file beside the legacy file and adapt results into the current API during a transition period.

## C. Proposed Domain Model

```text
Raw Indicator
    │
    ├── canonical analyte resolution
    ├── unit validation/conversion
    └── canonical Decimal measurement
                │
                ▼
Reference Data Contract V1
    │
    ├── Reference Classification (RI)
    │       ├── BELOW_REFERENCE
    │       ├── WITHIN_REFERENCE
    │       ├── ABOVE_REFERENCE
    │       ├── UNKNOWN
    │       └── NOT_APPLICABLE
    │
    └── Clinical Classifications (CDL, zero or more systems)
            ├── band_system_id A → zero/one band
            ├── band_system_id B → zero/one band
            └── ...

Canonical measurement ───────────────► Critical Detector
                                        (external subsystem;
                                         separate registry/result)

Reference result + Clinical results + Critical result
                │
                ▼
        Composite API / presentation
```

The Reference Data Contract does not emit `CRITICAL`. A composite application response may show all three outputs, but the critical result is neither derived from `ABOVE_REFERENCE` nor from any clinical band label. Likewise, `WITHIN_REFERENCE` describes only RI interval membership; it does not assert clinical normality and cannot suppress a CDL result.

### C.1 Rule, rule set and band system

- A **rule** is one RI interval or one CDL band with one applicability scope.
- An **RI candidate set** is grouped by canonical analyte and canonical unit, then filtered by specimen, fasting, population, age and sex.
- A **band system** is identified by `band_system_id`; all its bands express one coherent source-defined classification system.
- Precision is a **rule-set policy**, not a free choice per row. The flat file repeats precision fields for minimum migration, but validation requires identical precision policy for all simultaneously applicable rules within the same RI set or `band_system_id`.
- Applicability is evaluated per active rule. `ANY`/`A` means that dimension is unrestricted by that rule; it is not evidence that the caller has a particular specimen, fasting state or sex.
- Canonical analyte resolution may consume clinical context only through an explicit reviewed canonicalization policy. The input label alone cannot create that context.

## D. Proposed Rule Schema

### D.1 Final flat rule contract

Types below are logical JSON types. Numeric bounds are serialized as decimal strings to avoid binary-float drift.

| Field | Type | Required? | Allowed values / constraint | Semantics | Example |
| ----- | ---- | --------- | --------------------------- | --------- | ------- |
| `contract_version` | string | yes | `"1.0"` | Schema version, not medical version | `"1.0"` |
| `rule_id` | string | yes | unique, immutable, non-empty | Audit identity; never reused for changed semantics | `"EXPV2-HBA1C-002"` |
| `rule_status` | string enum | yes | `DRAFT`, `IN_REVIEW`, `INCOMPLETE`, `ACTIVE`, `RETIRED` | Runtime loads only `ACTIVE` | `"IN_REVIEW"` |
| `analyte_canonical` | string | yes | must resolve in canonical catalog | Canonical analyte, never an input alias | `"HbA1c"` |
| `specimen` | string | active: yes | canonical specimen code/name or explicit `ANY` | Applicability dimension. `null` means incomplete, not “any” | `"WHOLE_BLOOD_EDTA"` |
| `fasting_requirement` | string enum | active: yes | `REQUIRED`, `NOT_REQUIRED`, `ANY`; vague `CONDITIONAL` is not active-executable | Replaces ambiguous `fasting_required`; conditional source text must be reviewed into an executable scope | `"REQUIRED"` |
| `sex` | string enum | yes | `M`, `F`, `A` | `A` means all sexes; not missing sex evidence | `"A"` |
| `age_min` | decimal string or null | yes | `>=0`; contract unit is completed years | Inclusive minimum age; `null` is unbounded only | `"18"` |
| `age_max` | decimal string or null | yes | `>= age_min` when both present | Inclusive maximum age; `null` is unbounded only | `"60"` |
| `population_tags` | array[string] | yes | controlled tags; may be empty after review | Extra scope not captured by age/sex/specimen/fasting; all tags must match | `["OUTPATIENT"]` |
| `unit_canonical` | string | yes | must exist in unit registry | Unit in which structured bounds are expressed | `"mmol/L"` |
| `reference_type` | string enum | yes | `RI`, `CDL` | Selects independent classification algorithm | `"CDL"` |
| `band_system_id` | string or null | CDL: yes; RI: null | stable ID within analyte | Groups mutually exclusive bands; never inferred from analyte | `"HBA1C_DIAGNOSTIC_V1"` |
| `band_system_kind` | string enum or null | CDL: yes; RI: null | `DIAGNOSTIC`, `RISK_CATEGORY`, `STAGE`, `TARGET`, `SEVERITY`, `OTHER` | Replaces vague singular `clinical_band_type` | `"DIAGNOSTIC"` |
| `band_system_coverage` | string enum or null | CDL: yes; RI: null | `CONTINUOUS`, `PARTIAL` | Whether every valid value in applicability scope must match a band | `"CONTINUOUS"` |
| `band_label` | string or null | CDL: yes; RI: null | stable machine label | Category result; not user prose and never implies critical | `"prediabetes"` |
| `band_order` | integer or null | CDL: yes; RI: null | unique within system/context; monotonic display order | Sorting, adjacency validation and display only; never conflict precedence | `2` |
| `range_lower` | decimal string or null | yes | at least one bound non-null | `null` means no lower bound | `"5.7"` |
| `range_lower_inclusive` | boolean or null | yes | boolean iff lower non-null; otherwise null | Explicit `>=` versus `>` | `true` |
| `range_upper` | decimal string or null | yes | at least one bound non-null | `null` means no upper bound | `"6.5"` |
| `range_upper_inclusive` | boolean or null | yes | boolean iff upper non-null; otherwise null | Explicit `<=` versus `<` | `false` |
| `precision_mode` | string enum | yes | `RAW`, `QUANTIZE`, `UNSPECIFIED` | Evaluation domain. `UNSPECIFIED` cannot be active when determinism depends on precision | `"RAW"` |
| `precision` | integer or null | conditional | required for `QUANTIZE`; null for `RAW`/`UNSPECIFIED` | Decimal places in canonical unit for evaluation; not display formatting | `1` |
| `rounding_policy` | string enum | yes | `NONE`, `ROUND_HALF_UP`, `ROUND_HALF_EVEN`, `TRUNCATE` | `NONE` for RAW; an actual algorithm for QUANTIZE. No opaque `SOURCE_SPECIFIC` value | `"ROUND_HALF_UP"` |
| `source_id` | string | active: yes | stable non-empty source registry/document ID | Provenance identity independent of URL | `"SRC-ADA-A1C-2026"` |
| `source_url` | string or null | conditional | valid URL when source is web-addressable | Locator; a non-web source may use null only when `source_id` resolves to a retained document | `"https://…"` |
| `source_range_text` | string | active: yes | literal, non-empty | Exact reviewer-visible source semantics; never parsed at runtime | `"5.7–6.4%"` |
| `source_population_text` | string or null | optional | literal source text | Audit context for age/sex/population mapping; never parsed | `"Adults, non-pregnant"` |

### D.2 Conditional validation rules

1. Runtime loads only `rule_status=ACTIVE`.
2. `ACTIVE` requires explicit lower/upper semantics, explicit inclusive/exclusive operators, deterministic boundary behavior, a canonical unit, executable applicability context, source identity/provenance, retained literal source text and a resolved precision policy whenever determinism depends on precision. A source locator must be resolvable through `source_id`.
3. At least one numeric bound must be non-null. Both null is invalid.
4. A null bound requires its inclusive flag to be null. A non-null bound requires a boolean flag.
5. Lower must be less than upper. Equality is allowed only for a point interval with both sides inclusive.
6. RI rules must have all band-system fields null.
7. CDL rules require all band-system fields and a non-empty band label.
8. `band_order` must be unique among bands with the same system and equivalent applicability; it never selects a winner.
9. `precision_mode=RAW` requires `precision=null` and `rounding_policy=NONE`.
10. `precision_mode=QUANTIZE` requires non-negative `precision` and a non-`NONE` rounding algorithm evidenced by the source/review record.
11. `precision_mode=UNSPECIFIED` is allowed only for non-active migration records. If raw mathematical intervals are already disjoint and sufficient, review may activate them as `RAW`; otherwise `MEDICAL_DATA_DECISION_REQUIRED`.
12. Numeric zero is a valid bound. `-1`, `999999`, zero or any other number must never mean “bound absent.”
13. Loader and runtime must not infer missing medical semantics from neighboring rules, band order, source prose, field defaults, generic analyte names or project conventions. A rule that does not satisfy the active gate remains non-active.
14. `specimen=ANY`, `fasting_requirement=ANY` and `sex=A` are executable unrestricted scopes for their respective dimensions. They do not require the caller to supply that context.
15. A concrete applicability constraint, such as `fasting_requirement=REQUIRED`, requires matching caller evidence unless an explicit reviewed canonicalization/context policy supplies it.

### D.3 `age_scope`, population and priority decisions

- **Replace runtime `age_scope` with `age_min`/`age_max`.** The current V1 supported scope is explicitly `18 <= age <= 60`; it must not be labeled or treated as unrestricted “Adult.” Migration may retain literal source wording in `source_population_text`, but runtime must compare reviewed structured bounds.
- **Age bounds are always inclusive in V1.** If future sources require exclusive age boundaries, the contract version must be extended; Core-25 evidence currently does not justify extra fields.
- **Keep both structured bounds and literal source text.** Structured fields execute; literal text enables human audit. Neither substitutes for the other.
- **Population exists outside age/sex.** `population_tags` handles reviewed qualifiers such as setting or pregnancy state without overloading analyte names. Missing caller context produces `UNKNOWN / MISSING_CONTEXT` only when a potentially applicable active rule requires that context.
- **Known unsupported age is distinct from missing age.** If age is absent and required, return `UNKNOWN / MISSING_CONTEXT`. If age is known but no reviewed rule supports that age/population, return `UNKNOWN / OUTSIDE_SUPPORTED_POPULATION`; do not borrow a range reviewed for ages 18–60.
- **Do not add generic `priority` in V1.** Priority can silently mask overlapping sources. Specificity is applied only where this proposal states it; equal applicable RI rules are AMBIGUOUS, and multiple CDL bands in one system are AMBIGUOUS.

### D.4 Context applicability semantics

Applicability is a tri-state evaluation per rule: `MATCH`, `NO_MATCH` or `INDETERMINATE_MISSING_CONTEXT`.

- `specimen=ANY` is `MATCH` even when caller specimen is absent. A concrete specimen value requires caller specimen evidence.
- `fasting_requirement=ANY` and `NOT_REQUIRED` are `MATCH` even when fasting evidence is absent. `NOT_REQUIRED` records reviewed source semantics that fasting is not a precondition; it is not evidence that the caller is non-fasting. `REQUIRED` requires `fasting_status=YES`.
- `sex=A` is `MATCH` even when caller sex is absent. `M` or `F` requires matching caller sex.
- Unbounded age fields do not require age. A bounded age rule requires age before that rule can be selected.
- Missing context returns `MISSING_CONTEXT` only when the indeterminate rule remains otherwise viable and the missing value could change the selected RI rule, applicable clinical system or matched band. An unrestricted rule does not by itself create a missing-context failure.
- A known context value that does not satisfy a rule is `NO_MATCH`, not `MISSING_CONTEXT`.

Selection must fail closed if an indeterminate, more-specific active rule could change the result. Runtime must not select a generic-looking fallback merely because required context was omitted.

### D.5 Canonical analyte and fasting resolution

The alias/canonicalization registry remains a separate artifact from the flat RI/CDL rule rows, but its behavior is part of this contract boundary:

1. Explicit reviewed aliases that contain fasting semantics may resolve directly to `Fasting plasma glucose`, including `Fasting Plasma Glucose`, `Fasting Blood Glucose`, `Glucose máu lúc đói` and `Đường huyết lúc đói`.
2. Generic names such as `Glucose` and `Đường huyết` do not contain fasting evidence and must not be silently resolved to FPG merely because FPG is the only available V1 rule.
3. Generic glucose plus `fasting_status=UNKNOWN` fails closed as `UNKNOWN / MISSING_CONTEXT` when V1 classification requires an FPG context.
4. Generic glucose plus `fasting_status=YES` may resolve to FPG only through an explicit, reviewed and identifiable canonicalization policy. The result must expose the applied policy ID.
5. If fasting evidence exists but no reviewed policy authorizes the generic-to-FPG mapping, the resolver fails closed; loader/runtime must not invent the mapping.
6. Canonical analyte resolution occurs before unit conversion and RI/CDL selection, but it may use only caller-supplied context explicitly authorized by the reviewed policy.

Normative invariant: **Generic analyte naming must not create clinical context.** In particular, `Glucose` must not create `fasting=true`.

### D.6 Fields intentionally outside this rule contract

- Critical/panic thresholds and critical provenance
- Input analyte aliases/canonicalization map contents and analyte-specific mappings; their runtime behavior must still satisfy Section D.5
- Unit conversion factors and conversion rounding definitions
- Educational descriptions, high/low notes and RAG content
- UI label/color/badge precedence
- Patient-specific diagnosis, target or treatment decisions

Unit conversions belong in the unit registry. The rule stores only `unit_canonical`; the result stores the applied conversion ID.

## E. Proposed Result Schema

### E.1 Final result shape

The original singular `clinical_band` proposal is insufficient because multiple band systems can apply. The final contract is:

```json
{
  "contract_version": "1.0",
  "analyte_canonical": "HbA1c",
  "analyte_resolution": {
    "status": "RESOLVED",
    "policy_id": "CANON-HBA1C-DIRECT-V1",
    "context_used": [],
    "reason_code": null
  },

  "input_value": "5.7",
  "input_unit": "%",
  "canonical_value": "5.7",
  "canonical_unit": "%",
  "conversion_id": null,

  "population_context": {
    "specimen": "WHOLE_BLOOD_EDTA",
    "fasting_status": "UNKNOWN",
    "population_tags": []
  },
  "sex": "F",
  "age": "42",

  "reference_classification": {
    "reference_status": "WITHIN_REFERENCE",
    "resolution_code": "MATCHED",
    "matched_reference_rule_id": "EXPV2-HBA1C-001",
    "candidate_rule_ids": ["EXPV2-HBA1C-001"],
    "evaluated_value": "5.7",
    "precision_applied": null,
    "rounding_policy_applied": "NONE",
    "interval": {
      "lower": "4.0",
      "lower_inclusive": true,
      "upper": "5.7",
      "upper_inclusive": true
    }
  },

  "clinical_classifications": [
    {
      "band_system_id": "HBA1C_DIAGNOSTIC_V1",
      "band_system_kind": "DIAGNOSTIC",
      "match_status": "MATCHED",
      "clinical_band": "prediabetes",
      "band_order": 2,
      "matched_clinical_rule_id": "EXPV2-HBA1C-002",
      "candidate_rule_ids": ["EXPV2-HBA1C-002"],
      "evaluated_value": "5.7",
      "precision_applied": null,
      "rounding_policy_applied": "NONE",
      "reason_code": null
    }
  ],

  "warnings": []
}
```

The example is structural only. It preserves current numbers for illustration and does not approve the shown edge operators; those require boundary review. Its simultaneous `WITHIN_REFERENCE` and `prediabetes` outputs are intentional: RI interval membership does not override or reinterpret the independent CDL classification.

### E.2 Result field semantics

| Field | Type | Required? | Semantics |
| ----- | ---- | --------- | --------- |
| `contract_version` | string | yes | Result schema version |
| `analyte_canonical` | string or null | yes | Null only when canonicalization fails |
| `analyte_resolution` | object | yes | Canonicalization status, reviewed policy ID, caller context used and failure reason; proves that naming did not silently create context |
| `input_value` | decimal string | yes | Parsed input lexical value, unchanged |
| `input_unit` | string | yes | Unit received from caller |
| `canonical_value` | decimal string or null | yes | High-precision converted value before system-specific quantization |
| `canonical_unit` | string or null | yes | Unit used by applicable rules |
| `conversion_id` | string or null | yes | Trace to unit-registry conversion; null means identity |
| `population_context` | object | yes | Specimen, fasting state and reviewed population tags supplied by caller |
| `sex` | enum or null | yes | Normalized caller context; null is allowed when omitted and no viable active rule requires sex |
| `age` | decimal string or null | yes | Completed years used by selector |
| `reference_classification` | object | yes | RI result, including NOT_APPLICABLE/UNKNOWN |
| `clinical_classifications` | array | yes | One result per applicable/declared band system; empty when none exists |
| `warnings` | array[object] | yes | Structured warning code, severity, message and related rule IDs |

`analyte_resolution.status` is `RESOLVED` or `UNKNOWN`. An unresolved result uses one of `MISSING_CONTEXT`, `ANALYTE_NOT_SUPPORTED` or `CANONICALIZATION_POLICY_UNAVAILABLE`. The last code applies when caller evidence exists but no reviewed policy authorizes the requested context-dependent mapping.

### E.3 Reference result enums

`reference_status`:

```text
BELOW_REFERENCE | WITHIN_REFERENCE | ABOVE_REFERENCE | UNKNOWN | NOT_APPLICABLE
```

`resolution_code`:

```text
MATCHED
NO_RI_DEFINED
ANALYTE_NOT_SUPPORTED
CANONICALIZATION_POLICY_UNAVAILABLE
INVALID_VALUE
MISSING_CONTEXT
OUTSIDE_SUPPORTED_POPULATION
NO_APPLICABLE_RULE
UNSUPPORTED_UNIT
CONVERSION_UNAVAILABLE
AMBIGUOUS_RULES
INVALID_RULESET
PRECISION_POLICY_UNRESOLVED
```

- `NOT_APPLICABLE + NO_RI_DEFINED` means no RI is intentionally defined, as for a reviewed CDL-only analyte.
- Every error/inability maps to `UNKNOWN` with a non-`MATCHED` resolution code.
- `matched_reference_rule_id` is non-null only for MATCHED.
- `candidate_rule_ids` exposes competing IDs for AMBIGUOUS_RULES.
- `WITHIN_REFERENCE` means only that the evaluated value matches the selected RI interval. It does not mean clinically normal and must not override a CDL classification.
- `MISSING_CONTEXT` means a caller value required by an otherwise viable active rule or reviewed canonicalization policy is unknown.
- `OUTSIDE_SUPPORTED_POPULATION` means the caller context is known, but no reviewed rule supports that age/population. In current V1 data, a known age outside 18–60 produces this code when no other reviewed rule applies.

### E.4 Clinical system result enums

`match_status`:

```text
MATCHED | NO_MATCH | UNKNOWN | AMBIGUOUS | NOT_APPLICABLE
```

`reason_code` is null for a successful `MATCHED` result and otherwise uses a structured code appropriate to the system outcome, including:

```text
MISSING_CONTEXT
OUTSIDE_SUPPORTED_POPULATION
CONVERSION_UNAVAILABLE
INVALID_RULESET
PRECISION_POLICY_UNRESOLVED
DATA_GAP
OVERLAPPING_BANDS
```

- `MATCHED`: exactly one band in the system matched.
- `NO_MATCH`: zero bands matched and the reviewed system is explicitly `PARTIAL`.
- `UNKNOWN`: classification should have been possible but context/unit/policy/ruleset is unusable.
- `AMBIGUOUS`: more than one band in the same system matched. No band is selected.
- `NOT_APPLICABLE`: the band system exists but its reviewed population/context does not apply.

When a clinical system cannot classify because age is missing, use `UNKNOWN / MISSING_CONTEXT`. When age is known but outside every reviewed rule for that system, use `UNKNOWN / OUTSIDE_SUPPORTED_POPULATION`, not `NOT_APPLICABLE`. `NOT_APPLICABLE` remains reserved for a system explicitly defined as inapplicable to the caller's reviewed non-age population/context.

### E.5 Traceability and warnings

Warnings are objects, not free strings:

```json
{
  "code": "AMBIGUOUS_CDL_BANDS",
  "severity": "ERROR",
  "message": "More than one band matched within HBA1C_DIAGNOSTIC_V1.",
  "rule_ids": ["RULE-A", "RULE-B"]
}
```

Rule IDs should be persisted with history snapshots. They permit replay against the exact contract version and prevent a later data rebuild from changing the meaning of an old report silently.

### E.6 Legacy `status`

The domain contract does not define one primary badge. RI, CDL and Critical are independent. A temporary API adapter may retain current `status` for backward compatibility, but it is a legacy presentation/transport field and must not become the source of truth for the new contract. UI badge precedence is a presentation decision outside this contract.

## F. RI Selection Algorithm

```text
function classify_ri(input, context, active_rules, unit_registry):
    analyte_resolution = resolve_canonical_analyte(
        input.name, caller_supplied_context, reviewed_canonicalization_policies
    )
    if analyte_resolution requires context:
        return reference_status=UNKNOWN,
               resolution_code=MISSING_CONTEXT

    if analyte_resolution is not resolved:
        return reference_status=UNKNOWN,
               resolution_code=analyte_resolution.reason_code

    canonical_analyte = analyte_resolution.analyte

    raw_value = parse_exact_decimal(input.value)
    if raw_value is invalid:
        return UNKNOWN / INVALID_VALUE

    ri_rules_for_analyte = active rules where
        analyte_canonical == canonical_analyte
        and reference_type == RI

    if ri_rules_for_analyte is empty:
        return NOT_APPLICABLE / NO_RI_DEFINED

    target_units = distinct unit_canonical in ri_rules_for_analyte
    if no deterministic conversion exists from input.unit to a target unit:
        return UNKNOWN / UNSUPPORTED_UNIT or CONVERSION_UNAVAILABLE

    canonical_value, canonical_unit, conversion_id =
        unit_registry.convert_exact(raw_value, input.unit, target_unit)

    evaluate applicability of each canonical-unit rule as:
        MATCH
        NO_MATCH
        INDETERMINATE_MISSING_CONTEXT

    Applicability rules include:
        specimen=ANY does not require specimen
        fasting_requirement=ANY does not require fasting evidence
        sex=A does not require sex
        concrete/bounded dimensions require matching caller context
        age_min <= age <= age_max, respecting null as unbounded

    candidates = rules with MATCH
    indeterminate = rules with INDETERMINATE_MISSING_CONTEXT

    if indeterminate rules could change the selected result:
        return UNKNOWN / MISSING_CONTEXT

    if candidates is empty and known age/population is outside every
       reviewed rule for the analyte/unit:
        return UNKNOWN / OUTSIDE_SUPPORTED_POPULATION

    if candidates is empty:
        return UNKNOWN / NO_APPLICABLE_RULE

    Apply RI specificity only as an explicit fallback rule:
        exact sex outranks A for the same other applicability dimensions
        exact specimen outranks explicit ANY
        exact fasting scope outranks ANY
        narrower age interval outranks broader interval only when fully nested

    best = candidates with maximal specificity tuple

    if best count > 1:
        return UNKNOWN / AMBIGUOUS_RULES with candidate rule IDs

    rule = the single best candidate
    evaluation_value = apply_verified_precision_policy(
        canonical_value, rule-set policy
    )
    if policy unresolved:
        return UNKNOWN / PRECISION_POLICY_UNRESOLVED

    if evaluation_value is below rule lower edge:
        status = BELOW_REFERENCE
    else if evaluation_value is above rule upper edge:
        status = ABOVE_REFERENCE
    else:
        status = WITHIN_REFERENCE

    return status / MATCHED with rule ID, interval,
           canonical measurement and applied precision metadata
```

No record-order tie-break exists. Specificity is deterministic, documented and testable. Equal candidates remain ambiguous. RI output is independent of any CDL result. `WITHIN_REFERENCE` must not suppress, relabel or otherwise override a clinical band returned by CDL.

## G. CDL Selection Algorithm

CDL selection is value-aware and grouped by `band_system_id`.

```text
function classify_cdl(input, context, active_rules, unit_registry):
    resolve canonical analyte and exact Decimal as in RI, using only
        caller-supplied context and explicit reviewed canonicalization policy

    if canonical resolution requires missing context:
        fail closed as UNKNOWN / MISSING_CONTEXT

    Generic analyte naming must not create context:
        "Glucose" with fasting unknown is not Fasting plasma glucose

    cdl_rules = active rules where
        analyte_canonical == canonical_analyte
        and reference_type == CDL

    group cdl_rules by band_system_id
    results = []

    for each band_system_id in stable lexical order:
        system_rules = that group

        validate rule-set metadata is internally identical:
            canonical unit
            band_system_kind
            coverage mode
            precision mode/precision/rounding policy

        if invalid:
            append UNKNOWN / INVALID_RULESET
            continue

        convert input exactly to system canonical unit
        if conversion unavailable:
            append UNKNOWN / CONVERSION_UNAVAILABLE
            continue

        evaluate each band's applicability as MATCH, NO_MATCH or
            INDETERMINATE_MISSING_CONTEXT using its individual
            specimen, fasting, population, age and sex scope

        applicable_bands = bands with MATCH
        indeterminate_bands = bands with INDETERMINATE_MISSING_CONTEXT

        Important:
            Do not discard A/all-sex bands merely because sex-specific
            bands also apply. A system may legitimately have an all-sex
            high band and sex-specific low/average bands. Dataset
            validation must prove mutual exclusivity for each context.

        if indeterminate bands could change applicability or the match:
            append UNKNOWN / MISSING_CONTEXT
            continue

        if age/population is known and no reviewed rule in the system
           supports it because it is outside the supported population:
            append UNKNOWN / OUTSIDE_SUPPORTED_POPULATION
            continue

        if the system is explicitly inapplicable for a reviewed
           non-age population/context:
            append NOT_APPLICABLE
            continue

        evaluation_value = apply the system's verified precision policy
        matches = all applicable_bands where boundary_matches(value, band)

        if matches count == 1:
            append MATCHED with band label/order/rule ID

        else if matches count == 0:
            if coverage == PARTIAL:
                append NO_MATCH
            else:
                append UNKNOWN / DATA_GAP and an ERROR warning

        else:
            append AMBIGUOUS / OVERLAPPING_BANDS,
                   include every matching rule ID,
                   do not use band_order or priority to choose

    return results
```

### G.1 Band-system requirement

`band_system_id` is required for CDL because an analyte can have multiple legitimate systems. It prevents all CDL rules for one analyte from being treated as one mutually exclusive list. Complexity is limited to grouping and returning an array. Backward compatibility is manageable: existing CDL records can be assigned proposed IDs during reviewed migration without changing their numeric values.

### G.2 Coverage mode

- `CONTINUOUS`: every valid evaluation value in the declared applicability domain must match exactly one band. Gaps and overlaps fail dataset activation.
- `PARTIAL`: zero matches is an expected `NO_MATCH`; overlap still fails.

Coverage must be explicit per band system. It should not be globally assumed for every clinical system.

### G.3 Missing context and supported population

- An unrestricted applicability value (`ANY` or `A`) can match without caller evidence for that dimension.
- A missing value required by a viable active band produces `UNKNOWN / MISSING_CONTEXT`; runtime does not choose a generic band if the missing value could change the result.
- A known age outside all reviewed rules produces `UNKNOWN / OUTSIDE_SUPPORTED_POPULATION`. For current V1 scope, age 61 must not be classified using an 18–60 rule.
- `NOT_APPLICABLE` is not a substitute for either failure code. It describes an explicitly reviewed system that does not apply for a known non-age population/context.

## H. Boundary Evaluation Algorithm

### H.1 Runtime edge evaluation

```text
function matches(rule, value):
    matches_lower =
        rule.range_lower is null
        OR value > rule.range_lower
        OR (
            value == rule.range_lower
            AND rule.range_lower_inclusive == true
        )

    matches_upper =
        rule.range_upper is null
        OR value < rule.range_upper
        OR (
            value == rule.range_upper
            AND rule.range_upper_inclusive == true
        )

    return matches_lower AND matches_upper
```

Runtime never infers an operator from a number, source text, band order or neighboring rule.

### H.2 RI reference-position evaluation

```text
if matches(ri_rule, value):
    WITHIN_REFERENCE
else if lower exists and (
    value < lower OR (value == lower AND lower_inclusive == false)
):
    BELOW_REFERENCE
else if upper exists and (
    value > upper OR (value == upper AND upper_inclusive == false)
):
    ABOVE_REFERENCE
else:
    UNKNOWN / INVALID_RULESET
```

This output reports position relative to the selected RI only. `WITHIN_REFERENCE` is not a clinical-normality assertion and cannot override any CDL classification.

### H.3 Dataset overlap/gap validation

For every active `band_system_id` and every relevant applicability context:

1. Sort applicable bands by lower edge, using null as negative infinity.
2. Reject duplicate `band_order` in equivalent context.
3. Compare adjacent A and B:
   - `A.upper > B.lower` → overlap.
   - `A.upper == B.lower` and both edges inclusive → overlap at the point.
   - `A.upper == B.lower` and both edges exclusive → gap at the point.
   - `A.upper == B.lower` and exactly one edge inclusive → contiguous.
   - `A.upper < B.lower` → gap in RAW domain.
4. For QUANTIZE domain, validate over the representable lattice with quantum `10^-precision`; an apparent numeric interval is not a gap only when it contains no representable evaluation value under the approved rounding policy.
5. If coverage is CONTINUOUS, require negative- and positive-open ends or an explicitly defined bounded domain; otherwise fail coverage validation.
6. Validation is within one band system. RI/CDL overlap and overlap across different band systems are not errors.

Any active overlap violates the contract. Runtime handling remains fail-closed because deployment or cache corruption can bypass build-time validation.

## I. Precision & Unit Ordering

### I.1 Required ordering

```text
raw input name/value/unit/context
→ canonical analyte
→ exact Decimal parse
→ canonical unit resolution
→ exact/high-precision unit conversion
→ preserve canonical_value
→ apply verified precision policy per RI set or band system
→ boundary matching
→ return evaluated_value + conversion/precision trace
```

Conversion occurs before evaluation rounding because precision is defined in the canonical unit. Rounding an input-unit value first can move the converted value across a boundary and makes results depend on the submitted unit.

### I.2 Where precision belongs

Precision belongs to a **classification rule set in a canonical unit**:

```text
(analyte, reference_type, band_system_id-or-RI-set,
 applicability context, canonical_unit)
```

It is not globally analyte-level because different sources/systems may publish different resolution. It is not independently rule-level because adjacent bands in one system must share one evaluation domain. The flat V1 schema repeats it per row only to avoid a new rule-set file; validation enforces consistency.

### I.3 Input rounding policy

- Default is **no rounding** (`RAW`, `NONE`).
- Input may be quantized only when retained source/review evidence defines the precision and algorithm.
- Do not choose ROUND_HALF_UP, truncate or any other algorithm by convention or medical memory.
- An opaque `SOURCE_SPECIFIC` runtime value is forbidden; the actual supported algorithm must be encoded.
- If a source displays one decimal and input has three decimals:
  - with reviewed QUANTIZE policy, convert then quantize using that policy;
  - with RAW policy and mathematically disjoint/complete operators, classify raw;
  - if classification depends on an unstated precision assumption, the rules remain non-active and result is UNKNOWN.
- If evidence is insufficient:

```text
MEDICAL_DATA_DECISION_REQUIRED
```

Lack of precision evidence is not automatically fatal when reviewed inclusive/exclusive operators make the raw Decimal domain deterministic. It is fatal when values such as 6.45, 2.585 or 3.355 would otherwise fall into an unexplained gap or overlap.

### I.4 Conversion rounding

Conversion definitions and any conversion rounding belong to the unit registry, with a `conversion_id`. The reference rule does not own a conversion factor. The canonical raw value should be retained at sufficient precision; classification quantization, if any, is a separate documented step.

## J. Migration Matrix

No thresholds or boundaries are changed here. Migration status definitions:

- **AUTO:** fields can be copied/transformed losslessly into a non-active contract record; AUTO does not grant `ACTIVE` medical approval.
- **REVIEW:** structured migration is possible, but operators, source literal, precision, band system or context needs human review before activation.
- **BLOCKED:** current evidence/conflict is insufficient even for a safe activation proposal.

| Analyte | Current rules | Proposed representation | Migration status | Reason |
| ------- | ------------- | ----------------------- | ---------------- | ------ |
| WBC | RRV2-0002; one RI | RI; age 18–60; A; whole blood EDTA; 10^9/L | AUTO | Canonical fields and single interval copy losslessly. New record remains non-active until source literal/operator confirmation is attached. |
| RBC | RRV2-0003/0004; sex-specific RI | Two RI rules, M/F, same unit/specimen | AUTO | Age/sex/unit/bounds map directly; no multi-band logic. Source/operator activation review still required. |
| HGB | RRV2-0005/0006; sex-specific RI | Two RI rules, M/F, same unit/specimen | AUTO | Same structural case as RBC; critical registry is outside this migration. |
| Fasting plasma glucose | RRV2-0040 RI + 0060/0061 CDL | One RI plus one reviewed diagnostic `band_system_id`; reviewed explicit-name and context-dependent canonicalization policies | REVIEW | RI/CDL numeric overlap is allowed in parallel, but CDL transition operators, precision, fasting semantics and system identity require review. Generic `Glucose` must not map to FPG without fasting evidence and an approved policy. |
| HbA1c | EXPV2-HBA1C-001..003; RI + CDL | One RI plus `HBA1C_DIAGNOSTIC_*` system | REVIEW | Explicit 5.7 overlap and 6.4/6.5 precision-dependent transition; specimen missing. MEDICAL_DATA_DECISION_REQUIRED. |
| Total cholesterol | RRV2-0065..0067; CDL-only | CDL-only clinical system; RI result NOT_APPLICABLE | BLOCKED | 5.18 overlap, 6.18/6.19 precision dependency, `fasting_required=CONDITIONAL`, and CSV mg/dL vs rule mmol/L conflict. |
| LDL-C | EXPV2-LDLC-001..005; RI + four CDL bands | RI plus one risk-category band system | REVIEW | Adjacent decimal boundaries depend on explicit RAW operators or reviewed quantization; specimen missing. Critical 4.91 is not part of this contract. |
| HDL-C | EXPV2-HDLC-001..005; A/M/F RI+CDL | One sex-aware band system plus parallel RI | REVIEW | Exact sex-specific overlaps and explicit 1.54 gap after two-decimal conversion; all-sex high band must coexist with sex-specific bands; specimen missing. |
| Triglyceride | RRV2-0068..0071; CDL-only | CDL-only clinical system; RI result NOT_APPLICABLE | BLOCKED | Explicit 2.25 and 5.64 gaps, precision dependency, plural/key mismatch and CSV mg/dL vs rule mmol/L conflict. |
| Potassium | EXPV2-POTASSIUM-001..007; RI + six CDL bands | RI plus one severity band system | REVIEW | Exact overlaps at 2.5, 3.0 and 7.0 plus precision-dependent transitions; specimen missing. Clinical `severe` must not imply critical. |
| eGFR | no active rule | Future direct-value RI and/or `EGFR_G_STAGE_*` CDL system | BLOCKED | Quarantine reason/source/rules absent. No computation layer is proposed. |
| Uric acid | no active rule | Future reviewed RI rules | BLOCKED | Quarantine evidence and range rules absent; unit-name mapping unresolved. |

### J.1 Migration groups

```text
A. Can migrate automatically as non-active structural records:
   WBC, RBC, HGB and other single/sex-specific RI records with complete fields

B. Needs boundary/contract review:
   Fasting plasma glucose, HbA1c, LDL-C, HDL-C, Potassium

C. Needs medical/source/unit review:
   all multi-band activations; especially precision/operator decisions

D. Cannot migrate safely to ACTIVE:
   Total cholesterol, Triglyceride, eGFR, Uric acid until named blockers resolve
```

## K. Runtime Impact

No change below is implemented by this task.

| Area | Impact class | Future implementation impact |
| ---- | ------------ | ---------------------------- |
| `data/reference/reference_ranges.json` | MIGRATION_REQUIRED; BREAKING for old loader if replaced in place | Add V1 fields or introduce a side-by-side V1 file; validate active rules before load. Side-by-side is recommended for rollback. |
| `data/reference/reference_checker_v2_config.json` | MIGRATION_REQUIRED | `allowed_reference_types=[RI]` can no longer govern both algorithms. Keep `approved_analytes` unchanged until separate approval; add contract-version/rule-set gates only after approval. |
| `src/scripts/build_reference_config.py` | MIGRATION_REQUIRED | Emit explicit bounds, statuses, band-system metadata, validation results and provenance; never infer medical operators silently. |
| `reference_build_report.json` | NON_BREAKING additive | Add contract version, active/incomplete counts, band-system validation, gap/overlap results and source/precision completeness. |
| `src/services/reference_repository.py` | BREAKING internal API | Replace single `select_rule()` behavior with canonical measurement preparation, RI selection and CDL-system evaluation; return structured result. |
| Canonical analyte resolver/alias registry | MIGRATION_REQUIRED | Distinguish explicit fasting aliases from generic glucose labels. Context-dependent generic-to-FPG mapping requires fasting evidence and a reviewed policy ID; naming alone cannot create fasting context. |
| `src/agents/nodes/reference_range_checker_node.py` | MIGRATION_REQUIRED | Map structured RI/CDL results into agent state; stop compressing clinical band into generic status. |
| `src/agents/state.py` | MIGRATION_REQUIRED | Add `reference_classification`, `clinical_classifications`, canonical measurement and rule IDs. Keep legacy status only during adapter period. |
| `src/agents/nodes/critical_detector_node.py` | NON_BREAKING to this contract; separate safety work | Remains a distinct subsystem. A later implementation should consume canonical measurement but must not read CDL labels as critical. No threshold changes. |
| `src/models/schemas.py` API response | NON_BREAKING if additive; BREAKING if legacy fields removed | Add optional V1 objects first. Retain `status`, `reference_low/high`, `is_critical` for a documented transition. |
| `frontend/src/types/analysis.ts` | NON_BREAKING additive | Add optional typed reference/clinical objects. Existing screens can continue using legacy fields until presentation design is approved. |
| Patient/doctor result UI | MIGRATION_REQUIRED | Display RI and clinical band separately. Primary badge precedence is presentation policy, not contract policy. |
| `src/models/db.py` history snapshots | MIGRATION_REQUIRED | Persist contract version, canonical value/unit, RI status/rule ID and clinical system results/rule IDs. Existing `status` cannot faithfully replay parallel outputs. |
| `src/services/history_repository.py` | MIGRATION_REQUIRED | Save/restore new snapshot fields; do not reclassify old reports against new rules. |
| `frontend/src/types/history.ts` / History UI | NON_BREAKING additive, then MIGRATION_REQUIRED for display | Read persisted parallel classifications when present; tolerate legacy reports. |
| Tests | MIGRATION_REQUIRED | Add contract validators, exact Decimal edges, unit ordering, RI/CDL parallel results, multiple systems, snapshot replay and compatibility tests. |
| Existing history rows | NON_BREAKING read compatibility | Mark as legacy contract version; do not invent missing CDL/rule IDs retrospectively. |

### K.1 Recommended compatibility sequence

1. Add contract validator and side-by-side V1 data artifact, inactive by default.
2. Add result objects to internal state and API as optional fields; keep legacy fields.
3. Persist new snapshot fields for newly analyzed reports only.
4. Update frontend to consume parallel semantics.
5. After golden tests and human approval, activate reviewed rule sets analyte-by-analyte.
6. Deprecate legacy `status` only in a separately approved API version.

### K.2 Backward compatibility contract

Migration is additive for the transition period:

- Add `reference_classification`, `clinical_classifications`, canonical measurement and canonicalization trace fields.
- Temporarily retain legacy `status`, `reference_low`, `reference_high`, `is_abnormal`, `is_critical` and related response/history fields required by the current frontend.
- V1 structured objects are the domain source of truth. Legacy fields are a lossy compatibility projection and must not be read back to reconstruct RI/CDL semantics.
- A compatibility adapter may project `BELOW_REFERENCE` to legacy `low`, `WITHIN_REFERENCE` to legacy `normal`, and `ABOVE_REFERENCE` to legacy `high`. This projection does not change the V1 vocabulary and never incorporates a CDL label.
- Existing critical behavior may continue to affect the legacy presentation status during the transition, but the separate critical result remains authoritative for safety; neither critical nor CDL rewrites `reference_classification`.
- `reference_low` and `reference_high` may be copied from the matched RI interval only. They remain null when no RI is matched and must never be synthesized from CDL bands.
- Old history rows remain explicitly legacy. Do not retrospectively invent canonicalization policy IDs, rule IDs or clinical classifications.
- Removal of legacy fields requires a separately approved API version and frontend/history migration; it is not part of Contract V1 implementation authorization.

## L. Acceptance Criteria for Future Implementation

### AC-01 — RI basic

```text
Given one applicable ACTIVE RI with defined lower/upper edges
When the canonical evaluation value lies inside the interval
Then reference_status = WITHIN_REFERENCE
And resolution_code = MATCHED
And matched_reference_rule_id is returned.
```

### AC-02 — Inclusive lower

```text
Given lower=5.7 and range_lower_inclusive=true
When evaluation value=5.7
Then the lower condition matches.
```

### AC-03 — Exclusive upper

```text
Given upper=5.7 and range_upper_inclusive=false
When evaluation value=5.7
Then the rule does not match through the upper edge.
```

### AC-04 — Parallel RI + CDL

```text
Given an analyte has an applicable RI and one applicable CDL system
When one valid value matches the RI and one CDL band
Then the result contains both reference_status and clinical_band
And no resolver conflict is raised merely because RI and CDL overlap numerically.
And WITHIN_REFERENCE, when present, does not suppress or override the clinical_band.
```

### AC-05 — One CDL band

```text
Given a reviewed band_system_id
When classification runs for any valid value/context
Then at most one band in that system is MATCHED.
```

### AC-06 — Overlap detection

```text
Given two ACTIVE bands in the same system/context overlap
Then dataset validation FAILS before runtime activation
And identifies both rule IDs.
```

### AC-07 — Gap detection

```text
Given band_system_coverage=CONTINUOUS
When a representable valid value belongs to no band
Then dataset validation FAILS and identifies adjacent rule IDs/the gap.
```

### AC-08 — Open-ended bound

```text
Given range_lower=null and range_lower_inclusive=null
Then the lower side is unbounded
And is not interpreted as missing-data sentinel.
```

### AC-09 — RI-only analyte

```text
Given a WBC-style analyte has RI and no CDL system
When one applicable RI is selected
Then reference classification works
And clinical_classifications is empty.
```

### AC-10 — CDL-only analyte

```text
Given a reviewed analyte has CDL but no RI
When one clinical band matches
Then reference_status=NOT_APPLICABLE with NO_RI_DEFINED
And the clinical band is returned without fabricating an RI.
```

### AC-11 — Multiple band systems

```text
Given two applicable band_system_id values for one analyte
When each system has exactly one matching band
Then two clinical classification results are returned
And neither system overrides the other.
```

### AC-12 — Same-system runtime overlap fail-closed

```text
Given invalid deployed data causes two bands in one system to match
When runtime classification occurs
Then match_status=AMBIGUOUS
And all candidate rule IDs are returned
And band_order/record order does not select a winner.
```

### AC-13 — PARTIAL system no-match

```text
Given band_system_coverage=PARTIAL
When zero bands match a valid applicable value
Then match_status=NO_MATCH, not UNKNOWN.
```

### AC-14 — UNKNOWN, NOT_APPLICABLE and reason-code distinctions

```text
Given an RI exists but required specimen/context is missing
Then reference_status=UNKNOWN with MISSING_CONTEXT.

Given age is known but no reviewed rule supports that age/population
Then reference_status=UNKNOWN with OUTSIDE_SUPPORTED_POPULATION.

Given no RI is defined by contract for the analyte
Then reference_status=NOT_APPLICABLE with NO_RI_DEFINED.
```

### AC-15 — Unit ordering

```text
Given a supported non-canonical input unit
When classification runs
Then exact conversion occurs before evaluation quantization
And conversion_id, canonical_value and canonical_unit are returned.
```

### AC-16 — Unsupported unit

```text
Given no approved conversion exists from input unit to rule unit
When classification runs
Then result is UNKNOWN/UNSUPPORTED_UNIT or CONVERSION_UNAVAILABLE
And no numeric comparison occurs.
```

### AC-17 — Precision evidence

```text
Given precision_mode=QUANTIZE
Then precision, concrete rounding_policy and source/review evidence are present.

Given determinism depends on missing precision evidence
Then the rule set cannot become ACTIVE
And validation emits MEDICAL_DATA_DECISION_REQUIRED.
```

### AC-18 — No numeric sentinel

```text
Given an absent lower or upper bound
Then it is represented by null plus null inclusive flag
And validators reject a configured sentinel convention such as -1.
```

### AC-19 — Critical separation

```text
Given a clinical band label is high, very_high, severe or stage-like
When reference classification completes
Then it does not set is_critical or emit a critical alert.
```

### AC-20 — Snapshot traceability

```text
Given a new report is persisted
Then history stores contract version, canonical measurement,
matched RI rule ID and every matched clinical system/rule ID
And replay does not depend on current mutable rules.
```

### AC-21 — Equal RI candidates

```text
Given more than one equally specific applicable RI remains
When selection runs
Then reference_status=UNKNOWN with AMBIGUOUS_RULES
And no first-record or generic priority tie-break is used.
```

### AC-22 — Inactive rules

```text
Given a rule_status other than ACTIVE
When runtime loads the contract
Then the rule cannot classify a value.
```

### AC-23 — Context is required only when declared

```text
Given an otherwise applicable ACTIVE rule has specimen=ANY,
fasting_requirement=ANY and sex=A
And caller specimen, fasting evidence and sex are absent
When applicability is evaluated
Then those unrestricted dimensions match
And the result does not fail merely because those caller fields are absent.

Given an otherwise viable ACTIVE rule has fasting_requirement=REQUIRED
And fasting evidence is absent
When applicability is evaluated
Then classification fails closed as UNKNOWN / MISSING_CONTEXT.
```

### AC-24 — Outside supported age scope

```text
Given age=61
And the only otherwise applicable reviewed rule supports ages 18–60
When RI or CDL selection runs
Then that rule is not used
And the result is UNKNOWN / OUTSIDE_SUPPORTED_POPULATION.

Given age is unknown
And a bounded-age rule is otherwise viable and requires age
When selection runs
Then the result is UNKNOWN / MISSING_CONTEXT, not OUTSIDE_SUPPORTED_POPULATION.
```

### AC-25 — Generic glucose must not imply fasting

```text
Given input name="Glucose"
And fasting context=UNKNOWN
And V1 only supports Fasting plasma glucose classification
When canonical analyte resolution runs
Then it does not silently map the input to Fasting plasma glucose
And classification fails closed as UNKNOWN / MISSING_CONTEXT or an equivalent
structured failure carrying MISSING_CONTEXT.

Given input name="Glucose"
And fasting context=YES
When canonical analyte resolution runs
Then mapping to Fasting plasma glucose is allowed only through an explicit,
reviewed canonicalization policy
And the applied policy ID is returned.
```

### AC-26 — Explicit fasting aliases

```text
Given input name is an approved explicit fasting alias such as
"Fasting Plasma Glucose" or "Glucose máu lúc đói"
When canonical analyte resolution runs
Then it may resolve directly to Fasting plasma glucose through the reviewed alias policy
And no generic-name inference is used.
```

### AC-27 — ACTIVE rule completeness

```text
Given a rule lacks an explicit edge operator, source identity/provenance,
literal source text, executable applicability context, canonical unit,
or a precision policy required for deterministic boundaries
When contract validation runs
Then the rule cannot become ACTIVE
And loader/runtime does not infer the missing medical semantics.
```

### AC-28 — Additive legacy compatibility

```text
Given a V1 result is returned during the transition period
Then structured RI and CDL objects are present as the domain source of truth
And required legacy fields remain available as a derived compatibility projection
And no legacy field overrides or reconstructs the structured V1 result.
```

## Decisions Needed From Human

No unresolved architecture decision remains in this proposal. Human decisions D01–D09 are approved and incorporated:

| Decision | Approved outcome |
| -------- | ---------------- |
| D01 | RI and CDL are parallel outputs; CDL is grouped by `band_system_id`; Critical remains separate. |
| D02 | Default precision is `RAW` with no rounding; unresolved precision-dependent boundaries cannot become active. |
| D03 | Every clinical band system declares `CONTINUOUS` or `PARTIAL`; overlaps are forbidden in both. |
| D04 | Missing context fails closed only when a potentially applicable active rule requires it; `ANY`/`A` does not create a requirement. |
| D05 | V1 migration is additive and temporarily retains legacy API/history fields without treating them as domain truth. |
| D06 | Only rules with explicit executable semantics, provenance, literal source text, canonical unit and resolved precision behavior may become `ACTIVE`. |
| D07 | Current V1 supported age scope is explicitly 18–60 inclusive; known unsupported ages return `OUTSIDE_SUPPORTED_POPULATION`. |
| D08 | RI vocabulary is `BELOW_REFERENCE`, `WITHIN_REFERENCE`, `ABOVE_REFERENCE`, `UNKNOWN`, `NOT_APPLICABLE`. |
| D09 | Generic glucose naming never implies fasting; generic-to-FPG resolution requires fasting evidence and a reviewed policy. |

Exact analyte-specific operators, boundaries, critical thresholds, conversion constants and clinical bands remain later **Medical Data Review** work. They are not unresolved architecture decisions and do not reopen D01–D09.

## Final Verdict

The amended proposal is internally consistent with approved Human decisions D01–D09. Individual analyte operators, source literals, precision policies and blocked unit/quarantine cases still require medical/data review before their records can become `ACTIVE`; those data-review items do not block approval of the architecture or this document update.

```text
REFERENCE_DATA_CONTRACT_V1_DESIGN =
APPROVED_BY_HUMAN_PENDING_DOCUMENT_UPDATE
```

```text
REFERENCE_DATA_CONTRACT_V1_DOCUMENT =
READY_FOR_FINAL_APPROVAL
```

No implementation, data migration, runtime change or approval-list change is authorized by this document update.

## CHANGE SUMMARY

- **D07:** Replaced unrestricted “Adult” semantics with the explicit inclusive V1 age scope 18–60; added `OUTSIDE_SUPPORTED_POPULATION`, its distinction from `MISSING_CONTEXT`, selection behavior and acceptance coverage for age 61.
- **D08:** Replaced the V1 RI vocabulary throughout domain/result schemas, algorithms, examples and acceptance criteria with `BELOW_REFERENCE`, `WITHIN_REFERENCE` and `ABOVE_REFERENCE`; added the invariant that `WITHIN_REFERENCE` is not clinical normality and cannot override CDL.
- **D09:** Added explicit fasting-name versus generic-glucose canonicalization semantics, policy traceability, fail-closed behavior and acceptance tests proving that `Glucose` does not imply fasting.
- **D04 clarification:** Made context requirements active-rule-specific; defined `ANY`/`A` as non-requiring scopes, added tri-state applicability semantics and acceptance tests for unrestricted versus required context.
