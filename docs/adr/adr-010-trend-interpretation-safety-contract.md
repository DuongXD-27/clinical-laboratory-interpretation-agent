# ADR-010 — Trend Interpretation Safety Contract and Reference-Range Context

**Status:** ACCEPTED (amended 2026-08-19)

**Human approval date:** 2026-08-18 (amendment approved 2026-08-19)

**Decision owner:** Human Product/Technical Owner

**ADR number:** ADR-010

---

## Amendment — 2026-08-19

Approved by the Human Product/Technical Owner to align with the Business Description
`nhan-xet-phan-tich-xh.docx`. The amendment extends the interpretation contract from a
**single-analyte** scope to also cover **group-level factual interpretation**: a patient may
read the indicators of a functional section **together** and receive an explanation of the
factual relationships between them (e.g. "HbA1c và LDL-C cùng tăng qua các lần đo"). The
amendment codifies exactly the boundary the Business Description draws between **"diễn giải
dữ kiện"** and **"chẩn đoán theo nhóm"**: cross-analyte factual statements are allowed,
combined clinical conclusions are not. Changes: CRIT-TREND-01, CRIT-TREND-05, CRIT-TREND-06,
new CRIT-TREND-07, Safety Invariants, Validation criteria. All previously accepted rules
remain in force; this is an extension, not a relaxation.

---

## Context

### Background

The Advanced Trend Analysis feature upgrades the trend module along three objectives (Business Description `nhan-xet-phan-tich-xh.docx`):

1. Group indicators by functional section instead of a flat list.
2. Explain trends in the context of the reference range (position relative to threshold, % change between the two most recent measurements, overall direction) instead of describing the chart shape.
3. (Deferred to a later phase — see `## Scope exclusion` below) Make adding a new indicator a config-only change.

The team leader review raised three mandatory concerns this ADR resolves:

1. **No explicit rule for the boundary between "interpretation of facts" and "medical opinion"** — the product only had illustrative examples.
2. **No connection between trend interpretation and the existing critical-value pipeline** — a value approaching a critical threshold over multiple measurements would still receive a neutral explanation; the trend service is architecturally separate from the safety pipeline (ADR-001, `src/agents/graph.py`), leaving a safety blind spot.
3. **No visible consideration of sex/age-specific reference ranges** — a "within range / above range" statement could be clinically wrong for some patients if a single reference range is used.

Code facts verified on 2026-08-18:

- `src/services/trend_service.py` builds `TrendResponse` from `LabReport`/`ReportIndicator` and never calls an LLM.
- `src/services/trend_explanation_service.py` calls the LLM with a guardrail (`validate_trend_explanation`) independent of the pipeline guardrail.
- The pipeline (`reference_range_checker → critical_detector → analyzer → generate_questions → guardrail`) has no data or connection to trend service.
- `data/reference/reference_ranges.json` already carries per-rule `sex` (`A`/`M`/`F`) and `age_scope` (`Adult`), and `src/services/reference_repository.py` already implements sex/age-aware rule selection with a safe fallback to `A` rules. The gap is that the trend explanation prompt receives **neither** patient sex **nor** reference range bounds.
- Only **2 of 9** approved analytes have active critical thresholds under the declared operational authority (ADR-009, ARUP Rev.46): **Fasting plasma glucose** (`<55` / `>450` mg/dL) and **Potassium** (`<3.0` / `>6.1` mmol/L). The other 7 are inactive (`inactive_reason`).
- The Critical Detector only compares against thresholds; it has **no concept of "approaching"** a threshold.

---

## Decision

### CRIT-TREND-01 — Trend interpretation is fact-interpretation, not medical opinion

The trend explanation may state **facts grounded in the patient's own measurement series and the matched reference range**. It may **not** add any clinical significance, causation, prognosis, or action recommendation beyond the fixed high-priority notice defined in `CRIT-TREND-03`.

**Allowed sentence structures** (the model is restricted to these shapes):

1. Position relative to the reference range, using only the range bounds passed to it:
   `"[Chỉ số] nằm trong khoảng tham chiếu."` / `"[Chỉ số] đã vượt ngưỡng trên của khoảng tham chiếu."` / `"[Chỉ số] đang tiến gần ngưỡng trên/below của khoảng tham chiếu."`
2. Change between the two most recent measurements, using only backend-computed values:
   `"[Chỉ số] tăng/giảm X% so với lần xét nghiệm trước."` (X is computed by the backend and supplied in the prompt; the model repeats it, never computes it.)
3. Overall direction of the series:
   `"[Chỉ số] có xu hướng tăng/giảm/dao động/ổn định qua N lần đo."`
4. Combination of the above with dates from the data.
5. **Cross-analyte factual relationships within a functional section (group mode, see CRIT-TREND-07).** These use only the fact blocks supplied per analyte; every number must come from the block of the analyte it names:
   - `"[A] và [B] cùng tăng/giảm/ổn định qua các lần đo."`
   - `"Cả [A] và [B] trong nhóm này đều vượt ngưỡng trên của khoảng tham chiếu."` / `"...đều nằm trong khoảng tham chiếu."`
   - `"[A] tăng trong khi [B] giảm (trái chiều)."`

**Absolutely banned vocabulary** — expanded beyond the existing blacklist in `validate_trend_explanation()`:

- Prediction of the future: "dự đoán", "lần tới", "sẽ đạt", "kết quả tiếp theo", "forecast".
- Diagnosis: "mắc bệnh", "chẩn đoán", "suy giảm chức năng", "suy thận", "tiểu đường", etc.
- Causation inference: "nguyên nhân là do", "do ăn nhiều chất béo", "do thiếu".
- Risk interpretation: "cho thấy nguy cơ", "có thể là dấu hiệu của", "bạn có nguy cơ".
- Treatment/drug/lab referral: "nên dùng thuốc", "cần xét nghiệm thêm", "nên đi khám vì", "hãy uống".
- **Combined clinical conclusion from a group of indicators** (the boundary the Business Description calls "chẩn đoán theo nhóm"): "sự kết hợp này cho thấy", "nhóm chỉ số này nghĩa là", "nguy cơ tim mạch", "hội chứng chuyển hóa", or any statement deriving a condition, risk, or clinical significance from the combination of indicators in a section.
- Any number not present in the supplied data, reference bounds, critical bounds, or backend-computed change values.

The adversarial test suite in `tests/test_services/test_trend_explanation_guardrail.py` operationalizes these rules before the code is changed (test-first), following the pattern of the `RETRIEVAL_MIN_SCORE` evidence.

### CRIT-TREND-02 — Reference range for the explanation must be matched by sex and age

- The trend explanation must resolve the reference range rule using `ReferenceRepository.select_rule()` with the **sex and age recorded at the most recent measurement** (`lab_reports.patient_gender_at_test` / `lab_reports.patient_age_at_test`), which is the same snapshot the pipeline used.
- The matched `range_lower`/`range_upper` and the patient sex must be injected into the LLM prompt.
- The same bounds must be added to the guardrail's allowed-number set, so "vượt ngưỡng 5.5 mmol/L" is not blocked as a fabricated number.
- If no rule can be matched (analyte not supported, sex/age out of scope, unit mismatch), the explanation falls back to the current neutral behavior: it must **not** make any "within/above range" claim, because doing so without a matched rule would risk clinical incorrectness (team leader concern #3).
- The `age_scope` is a single bracket (`Adult`, 18–60) matching the PRD target population. This is a documented constraint, not a bug; any expansion beyond 18–60 requires re-auditing the reference data.

### CRIT-TREND-03 — Trend explanation must escalate toward critical thresholds

The trend service and the pipeline remain architecturally separate (the verified safety pipeline is untouched), but they **share one critical-threshold module** (`src/services/critical_value_service.py`) so the threshold logic cannot diverge between the two call sites.

1. **Reuse, not rewrite.** The pure comparison helpers and the glucose unit-conversion path (`CONVERT_INPUT_TO_SOURCE_UNIT`) are extracted from `critical_detector_node.py` into the shared module. The node is refactored to delegate to it with its existing fail-closed invariants and alert messages preserved.
2. **Latest-point critical check.** `trend_service` evaluates the **most recent point** with the shared module. If it exceeds an active critical threshold, `TrendResponse.critical_status` is set.
3. **Approaching-critical rule.** A new, explicitly defined rule (this concept does not exist in the current code): the latest point is **approaching** an active critical threshold when **all** of the following hold:
   - the analyte has an active critical threshold;
   - the latest point is **not already critical**;
   - the latest point is **moving toward** a threshold (the most recent value is greater than the previous one when checking the high side, or lower when checking the low side; equal values do not trigger);
   - the latest value lies within **10%** of that active threshold (computed in the threshold unit via the shared conversion path).
4. **High-priority template.** If the latest point is critical or approaching-critical, `trend_explanation_service` switches to a dedicated high-priority template: it states the trend facts and adds a fixed notice to contact a doctor now. It does **not** use the neutral default template. The critical threshold bounds are added to the guardrail's allowed-number set so the escalated statement is not self-blocked.
5. **Scope.** This mechanism applies only to analytes with active critical thresholds. Under ADR-009, that is exactly **Fasting plasma glucose** and **Potassium**. The other 7 approved analytes have no active critical rule and therefore no escalation.

### CRIT-TREND-04 — Backend-computed change values, not model-computed

The percentage change between the two most recent measurements is computed by the backend (`(latest - previous) / previous × 100`), rounded to one decimal. The result is injected into the prompt as a fact and added to the guardrail's allowed-number set. The model must not compute its own percentages; it repeats the supplied value. This prevents the model from inventing a different calculation formula and keeps the guardrail able to distinguish grounded numbers from fabricated ones.

### CRIT-TREND-05 — Allowed-number set extension

`_allowed_numbers()` in `trend_explanation_service.py` is extended with a second optional argument carrying **extra allowed numbers**:

- the matched reference range bounds (`range_lower`, `range_upper`);
- the active critical threshold bounds (`low`/`high` from `critical_thresholds.json` for the analyte);
- the backend-computed percentage change value(s).

The existing behavior (points, dates, counts) is unchanged, and the scientific-unit strip rule (`_strip_unit_mentions`) is preserved.

**Group mode (amendment 2026-08-19):** when validating a section-level explanation (CRIT-TREND-07), the allowed-number set is the **union** of the per-analyte sets across every analyte included in the group — each analyte's point values/dates/counts, its sex/age-matched reference bounds, its backend-computed percentage change, and the critical bounds of any escalated analyte. Number fabrication is still blocked: a number in the final text must exist in the supplied data of the analyte it names (or its supplied bounds/change), and combining values of two analytes into a computed figure is treated as a fabricated number.

### CRIT-TREND-06 — Functional sections (Objective 1)

- The build (`src/scripts/build_reference_config.py`) propagates the source CSV `section` column into every `reference_ranges.json` rule as a canonical key (`hematology` / `chemistry` / `lipids`).
- The runtime per-analyte section is the section of the analyte's **reference interval (RI)** rules. One explicit expert override is recorded: **Fasting plasma glucose → `lipids`**, because the product group "Mỡ máu & đường huyết" (per Business Description) includes blood glucose, while the source CSV places its RI rule under "Chemistry, renal, and liver analytes".
- Analytes with no section resolve to the `other` group ("Khác"), displayed last.
- Section is derived at runtime from `reference_ranges.json`; **no new `IndicatorCatalog` database column is added** in this phase (the table is not yet populated — `report_indicators.indicator_catalog_id` is always `NULL`). The consolidated indicator configuration (Objective 3) is deferred to a later phase and will decide the authoritative schema.
- The report-detail page (`LabReportDetailSchema` indicators) and the trend page both display sections. The doctor-facing/report page shows **sections only**, never a trend LLM explanation (single-analyte or group), to avoid extra cost/latency and duplicate content.
- **Group membership is expert-declared configuration data** (from `reference_ranges.json`, propagated from the source CSV). The LLM never invents a group or a section membership; it only reads the groups the configuration defines. A section serves both **display grouping** and, under CRIT-TREND-07, **group-level explanation**.

### CRIT-TREND-07 — Group-level factual interpretation (amendment 2026-08-19)

The Business Description asks that a patient be able to read the indicators of a functional section **together** and learn the factual relationship between them (e.g. "HbA1c và LDL-C cùng tăng") instead of comparing each indicator one by one by eye. This is allowed as **fact-interpretation across indicators**, never as a combined clinical conclusion.

1. **Scope.** Trends page only, never the report-detail page. One group explanation covers all `trend_available` analytes of one section key (`hematology` / `chemistry` / `lipids`). An analyte needs at least 3 points (existing rule) to be included; analytes with fewer points are listed in the UI but excluded from the group prompt.
2. **Per-analyte facts.** Each included analyte contributes a fact block computed by the backend with the same helpers as the single-analyte flow: sex/age-matched reference bounds (CRIT-TREND-02), percentage change between the two most recent measurements (CRIT-TREND-04), overall direction, and critical bounds if escalated (CRIT-TREND-03). The model repeats these facts; it never computes its own.
3. **Allowed content.** Only factual cross-analyte relationships as in CRIT-TREND-01 structure #5 (co-direction, all above / all within the reference range, approaching a threshold, divergence). **Banned:** any combined clinical conclusion, diagnosis, risk interpretation, causation, future prediction, or action recommendation derived from the group — the "chẩn đoán theo nhóm" boundary in the Business Description.
4. **Guardrail.** The section explanation is validated with the **union** allowed-number set (CRIT-TREND-05) and the same banned vocabulary. An LLM output that combines indicators into a clinical claim (e.g. "sự kết hợp này cho thấy nguy cơ tim mạch") is blocked even when every number it contains is grounded.
5. **Edge cases.** No eligible analyte in the section → return the fixed fallback text (`INSUFFICIENT_DATA`). Exactly one eligible analyte → delegate to the single-analyte flow (identical behavior). Any included analyte is critical or approaching-critical → the fixed high-priority notice of CRIT-TREND-03 is appended to the group explanation.
6. **Cost control.** Group explanations are generated **on demand only** (one LLM call per section when the patient asks), never automatically for every group on page load — consistent with the Business Description risk "chi phí và độ trễ".
7. **Failure handling.** LLM unavailable, empty output, or guardrail block → return the fixed fallback text; the charts and data remain fully visible (Business Description edge case "Khi hệ thống không sinh được phần diễn giải").

---

## Rationale

1. **Fact-interpretation only is the only defensible claim level for an educational tool.** The product explicitly does not diagnose, predict, or replace a doctor. A "within range / above range" statement is a fact when the reference rule is correctly matched to the patient; it becomes a medical opinion the moment the model adds significance, risk, or referral language.
2. **The sex/age-matched range is required for clinical correctness.** Hemoglobin, RBC, Creatinine, and HDL-C have sex-specific ranges; a blanket range would produce wrong "in range / above range" statements for a subset of patients (team leader concern #3). The infrastructure already exists in `ReferenceRepository`; only the prompt wiring is missing.
3. **Shared critical module without shared pipeline.** The pipeline is verified and safety-critical; the trend service needs the same threshold authority (ADR-009) without inheriting pipeline state (`AgentState`). Extracting the pure functions into one module satisfies both: one source of truth, two call sites, no pipeline coupling.
4. **The approaching rule must be explicit and narrow.** A warning that a value is moving toward a critical threshold is stronger than the default explanation. Being conservative (10% margin, confirmed direction, active threshold only) avoids alert fatigue and false "danger" statements, consistent with ADR-009's priority of avoiding false emergency alerts.
5. **Backend-computed change keeps the guardrail sound.** If the model were free to compute percentages, the guardrail could not distinguish a real 15% from an invented 15% by checking the number against the data. Computing it in the backend makes the number a grounded fact that the guardrail can whitelist.

---

## Scope exclusion (future phase)

The following from the Business Description are **not** implemented by this ADR and are deferred to the "consolidated indicator configuration" phase:

- A single declaration point for all indicator traits (canonical name, aliases, unit, section, reference range).
- Populating `report_indicators.indicator_catalog_id`.
- Enabling `max_gap_days_for_trend` for time-gap filtering (the minimum 3-point rule is kept).
- Trend LLM explanation on the report-detail page.

---

## Safety Invariants

1. **No medical opinion.** The explanation may state grounded facts only; any diagnosis, causation, risk interpretation, treatment/drug/lab referral, or future prediction is blocked by the guardrail and the prompt.
2. **No ungrounded numbers.** Every number in the explanation must exist in the supplied data, the matched reference bounds, the active critical bounds, or the backend-computed change values.
3. **No "within/above range" claim without a matched rule.** If the reference rule cannot be matched for the patient, the explanation must not make range claims.
4. **No critical escalation without an active threshold.** Approaching/critical templates fire only for analytes with active critical rules (glucose, potassium under ADR-009).
5. **No pipeline coupling.** The pipeline graph is unchanged; the shared module is the only interface between the trend service and the critical threshold data.
6. **Existing fail-closed critical behavior preserved.** The refactor to the shared module must not alter the node's unit normalization, canonicalization, upstream-`unknown` preservation, or alert messages.
7. **No cross-analyte medical conclusion.** A group explanation may state factual co-direction/co-range relationships grounded in each analyte's own supplied facts; deriving a condition, risk, diagnosis, or combined clinical significance from the combination is blocked by the guardrail and the prompt.

---

## Validation / Acceptance Criteria

- [ ] `tests/test_services/test_trend_explanation_guardrail.py` covers the fact-vs-opinion boundary before the explanation code changes.
- [ ] `_allowed_numbers()` accepts reference bounds, critical bounds, and backend-computed change values; fabricated numbers remain blocked.
- [ ] The trend explanation prompt receives the matched `range_lower`/`range_upper` and patient sex; without a matched rule no range claim is made.
- [ ] `trend_service` sets `critical_status` for a latest point exceeding an active threshold, and `approaching_critical` when the 10%-margin + direction rule matches, for glucose/potassium only.
- [ ] The high-priority template is used when `critical_status` or `approaching_critical` is set, and its threshold numbers pass the guardrail.
- [ ] `critical_detector_node` tests pass unchanged (message and behavior preserved).
- [ ] Every rule in `reference_ranges.json` carries a `section`; per-analyte section is deterministic; FPG → `lipids`; unknown → `other`.
- [ ] Trend page and report-detail page group indicators by section; report-detail shows no LLM explanation.
- [ ] **Group mode:** the section guardrail blocks a combined clinical conclusion ("nguy cơ tim mạch", "sự kết hợp này cho thấy") even when every number in the output is grounded.
- [ ] **Group mode:** the union allowed-number set accepts numbers of any included analyte; a figure formed by combining two analytes' values is blocked as fabricated.
- [ ] **Group mode:** a section with exactly one eligible analyte produces identical behavior to the single-analyte flow.
- [ ] **Group mode:** an escalated analyte appends the fixed CRIT-TREND-03 notice; zero eligible analytes return the fixed fallback.
- [ ] **Group mode:** explanations are generated on demand only; an LLM failure or guardrail block returns the fixed fallback with charts/data still visible.

---

## Consequences

### Positive
- Removes the safety blind spot (team leader concern #2) without touching the verified pipeline.
- Makes "in range / above range" statements clinically correct for the 4 sex-specific analytes (concern #3).
- Turns the fact-vs-opinion boundary into testable rules instead of examples (concern #1).
- Single source of truth for critical thresholds and for functional sections.

### Negative / Trade-offs
- Approaching-critical escalation is limited to glucose and potassium (2/9) by ADR-009 coverage.
- The 10% margin is a product decision, not a clinical one; it must be re-reviewed if the critical registry expands.
- FPG is grouped under "Mỡ máu & đường huyết" via an explicit override that deviates from the literal CSV section of its RI rule.
- Report-detail page does not show LLM trend explanations (deliberate cost/latency and scope decision).

---

## Referenced Documents

| Document | Role |
|---|---|
| `docs/adr/adr-009-vmec-v1-critical-threshold-authority.md` | Declared operational authority for critical thresholds |
| `docs/adr/adr-001-langgraph.md` | Pipeline architecture (unchanged) |
| `docs/version-handoff/retrieval-min-score-evidence.md` | Evidence-format precedent for the adversarial test suite |
| `nhan-xet-phan-tich-xh.docx` | Business Description with team leader review |
