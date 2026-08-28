# VMEC-05 Orchestrator V1 — Final Verify Evidence (Historical Archive)

Date: 2026-08-20

This document records the final verification scope for the patient-facing
Orchestrator V1. It is evidence for Human Owner review; it is not a deployment
approval.

## Scope

Orchestrator V1 adds a Patient/Guest Hybrid Assistant on top of the existing
medical analysis pipeline. The Assistant can route requests, resolve current
report/analyte context, call approved wrappers, compose a typed response, and
surface safe suggested actions. It does not add a new medical authority.

The fixed medical pipeline remains:

```text
ReferenceRangeChecker -> CriticalDetector -> Analyzer/RAG -> QuestionGenerator -> Guardrail
```

The conversational response path is:

```text
Patient/Guest UI
-> Orchestrator API
-> role/onboarding/OCR/policy gates
-> Context Resolver
-> Intent Router
-> Workflow Dispatcher
-> approved wrappers/services
-> Response Composer
-> Medical Safety Validation
-> Schema Validation
-> SuggestedAction Validation
-> Frontend
```

OCR-derived medical input still has one entry point:

```text
Image -> OCR draft -> human review -> /api/v1/ocr/confirm -> fixed medical workflow
```

The Orchestrator may read whether a pending OCR review exists. It must not read
OCR draft values to construct medical input.

## Frozen V1 Contract

Executable schema introspection on 2026-08-20 showed:

```text
Intents=6
SuggestedActions=7
Conversational roles=2 (guest, patient)
Doctor conversational support=DEFER_TO_V2
Reason codes=19
```

Intents:

- `UNSUPPORTED_OR_UNSAFE`
- `ANALYZE_REPORT`
- `EXPLAIN_CURRENT_RESULT`
- `VIEW_HISTORY`
- `ANALYZE_TREND`
- `GET_DOCTOR_QUESTIONS`

Suggested actions:

- `OPEN_REPORT`
- `VIEW_ABNORMAL`
- `VIEW_HISTORY`
- `VIEW_TREND`
- `VIEW_DOCTOR_QUESTIONS`
- `CONFIRM_OCR`
- `RETRY`

Reason codes:

- `ONBOARDING_REQUIRED`
- `OCR_REVIEW_REQUIRED`
- `OCR_CONFIRM_INVALID`
- `MEDICAL_DIAGNOSIS_REQUEST`
- `MEDICAL_CAUSE_REQUEST`
- `TREATMENT_REQUEST`
- `UNSUPPORTED_ANALYTE`
- `UNSUPPORTED_CAPABILITY`
- `AMBIGUOUS_CONTEXT`
- `AUTH_EXPIRED`
- `REPORT_NOT_FOUND_OR_UNAUTHORIZED`
- `DB_UNAVAILABLE`
- `LLM_UNAVAILABLE`
- `RAG_UNAVAILABLE`
- `TREND_INSUFFICIENT_POINTS`
- `TREND_UNIT_INCONSISTENT`
- `UNKNOWN_INTENT`
- `GUARDRAIL_BLOCKED`
- `INTERNAL_WORKFLOW_ERROR`

## Authorization And Roles

Patient identity is resolved from the server auth context only. Orchestrator
wrappers expose "my resource" operations, not caller-supplied patient lookup
operations. A non-owned report and a missing report share
`REPORT_NOT_FOUND_OR_UNAUTHORIZED`.

V1 conversational roles are `guest` and `patient`. `doctor` remains supported by
doctor-facing routes, but is blocked from the conversational Orchestrator before
router, wrapper, or protected DB access with `UNSUPPORTED_CAPABILITY`.

## Response Authority

The LLM may generate only the display message. The server controls:

- `intent`
- `status`
- `reason_code`
- `data`
- `data_type`
- `sources`
- `suggested_actions`
- `safety_notice`

If the final message contradicts deterministic medical facts, diagnoses, infers
cause, recommends treatment, or carries invalid suggested actions, final
validation blocks the response.

## RAG Policy

RAG is optional enrichment. Deterministic analyte resolution, reference ranges,
critical values, status, and trend calculations do not come from RAG.

For `status="unknown"`:

```text
classification=unknown
critical inference=absent
general RAG calls=0
LLM explanation calls=0
```

Approved curated catalog explanations and approved catalog sources may remain.

TIP-007 did not generate a live RAGAS quality score. Existing RAGAS tests verify
dataset, runner, security, and fake-evaluator live harness behavior. Therefore:

```text
RAG_LIVE_QUALITY=NOT MEASURED
```

## OCR HITL Lifecycle

The authoritative OCR lifecycle is DB-backed:

```text
PENDING -> CONSUMED
PENDING -> EXPIRED
```

`/api/v1/ocr/upload` creates a server-side pending review artifact and signed
review token. `/api/v1/ocr/confirm` validates the token, owner/session binding,
expiry, row review evidence, and low-confidence acknowledgements before
consuming the lifecycle and invoking medical analysis. Replay, expired review,
cross-user review, and unreviewed rows are rejected before another analysis
invocation.

## Requirement Traceability

The repository does not contain a standalone RRI requirement matrix, Blueprint,
or Contract artifact with a complete authoritative REQ-ID list. Traceability
below uses available TIP/contract requirements by content and does not invent
missing REQ-IDs.

| Requirement source | Requirement | Implementation | Test/evidence | Status |
|---|---|---|---|---|
| TIP-001 / REQ-I01 | Exactly six intents | `src/models/orchestrator_schemas.py` | `tests/orchestrator/test_contracts.py::test_ac1_intent_enum_has_exactly_six_members` | Implemented |
| TIP-001 / REQ-I02 | Arbitrary intent rejected | `OrchestratorResponse` schema | `test_ac2_invalid_intent_value_is_rejected` | Implemented |
| TIP-001 / REQ-R01/R02 | V1 roles guest/patient; doctor deferred | `OrchestratorRole`, role gate | `test_ac10_orchestrator_role_only_includes_guest_and_patient_constants`, TIP-006 zero-invocation | Implemented |
| TIP-001 / REQ-S01-S04 | Session context separated; no client server-field override | `OrchestratorSessionContext`, `OrchestratorRequest` | `test_ac7_request_rejects_pending_ocr_review`, `test_ac8_request_rejects_server_authority_fields`, `test_req_s02_session_context_declares_all_required_fields` | Implemented |
| TIP-001 / REQ-P01 | Typed response, no generic data escape hatch | `DataPayload`, `OrchestratorResponse` | `test_ac3_data_discriminator_rejects_mismatched_payload_shape`, `test_ac4_response_data_is_closed_discriminated_union_without_escape_hatches` | Implemented |
| TIP-001 / REQ-U01/U02 | Seven safe suggested actions; no arbitrary URL/identity/free-form payload | `SuggestedAction` schema, frontend sanitizer | `test_all_seven_suggested_action_variants_are_present`, `test_req_u02_no_action_variant_declares_free_form_payload`, frontend `assistantActions` tests | Implemented |
| TIP-001 / REQ-F01 | Nineteen reason codes | `ReasonCode` | `test_ac9_reason_code_has_exactly_nineteen_members` | Implemented |
| TIP-001 / REQ-A02 | No client/LLM patient_id authority | Request schemas, wrappers | `test_ac8_request_rejects_server_authority_fields`, `tests/orchestrator/test_authorization.py` | Implemented |
| TIP-001 / REQ-C03 / D-C | `pending_ocr_review` server-derived; `CONFIRM_OCR` cannot carry values | computed field, `ConfirmOcrAction` | `test_req_s02_session_context_declares_all_required_fields`, `test_ac12_confirm_ocr_action_carries_only_review_reference` | Implemented |
| TIP-002 | Safe wrappers and ownership checks | `src/orchestrator/wrappers.py` | `tests/orchestrator/test_authorization.py` | Implemented |
| TIP-003 | Orchestrator API/core gates/session | `src/orchestrator/service.py`, `src/api/orchestrator_routes.py` | `tests/orchestrator/test_orchestrator_core.py`, `test_zero_invocation.py` | Implemented |
| TIP-004 / ESC-004 | Message-only composer and unsupported-analyte fail-closed | `src/orchestrator/response_composer.py`, analyzer guard | `tests/orchestrator/test_response_composer.py`, `tests/test_agents/test_analyzer_node.py` | Implemented |
| TIP-005 | Patient/Guest Hybrid Assistant frontend | `frontend/src/components/patient/AssistantWidget.tsx` | `frontend/src/lib/assistantActions.test.mjs`, frontend lint/type/build | Implemented |
| TIP-006 | Evaluation, P0/P1/P2, six E2E flows | `tests/orchestrator/test_tip006_evaluation.py` | TIP-006 suite and full regression | Implemented |
| TIP-007 | Final verify and documentation | this document, README/API/architecture docs | TIP-007 final report | Implemented |

## Final Metrics To Reproduce

Run from repository root unless noted:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator -q
.\.venv\Scripts\python.exe -m pytest tests\test_api\test_ocr_review_gate.py tests\test_api\test_guest_flow.py tests\test_api\test_patient_history.py tests\test_api\test_patient_trends.py tests\test_agents\test_analyzer_node.py tests\test_agents\test_guardrail_node.py tests\test_services\test_retriever.py tests\test_data\test_medical_kb_manifest_integrity.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_eval -q
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

TIP-006 benchmark targets and latest accepted measured values:

```text
P0 authorization violations=0
P0 cross-user leakage=0
P0 medical authority violations=0
P0 OCR bypasses=0
P0 invalid privileged action execution=0

Intent routing=20/20=100%
Workflow selection=6/6=100%
SuggestedAction schema validity=7/7=100%
Context resolution=10/10=100%
Task completion=6/6=100%
E2E=6/6 PASS
```

TIP-007 current verification results:

| Command | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests\orchestrator -q` | `113 passed, 2 warnings` |
| `.\.venv\Scripts\python.exe -m pytest tests\test_api\test_ocr_review_gate.py tests\test_api\test_guest_flow.py tests\test_api\test_patient_history.py tests\test_api\test_patient_trends.py tests\test_agents\test_analyzer_node.py tests\test_agents\test_guardrail_node.py tests\test_services\test_retriever.py tests\test_data\test_medical_kb_manifest_integrity.py -q` | `95 passed, 34 warnings` |
| `.\.venv\Scripts\python.exe -m pytest tests\test_eval -q` | `62 passed, 3 warnings` |
| `.\.venv\Scripts\python.exe -m pytest -q` | `941 passed, 65 warnings` |
| `cd frontend; npm test` | `25 passed` |
| `cd frontend; npm run lint` | `PASS` |
| `cd frontend; npx tsc --noEmit` | `PASS` |
| `cd frontend; npm run build` | `PASS` |
| `.\.venv\Scripts\python.exe -m ruff check . --statistics` | `87 pre-existing errors; no TIP-007 Python files changed` |

The repo-wide `git diff --check` command is blocked by existing trailing
whitespace in `data/reference/medical_kb_manifest.json`, a forbidden reference
file changed before TIP-007. Scoped diff-check for TIP-007 documentation files
passes.

## Known V1 Limitations

- Doctor conversational Assistant support is deferred to V2.
- No persistent long-term chat memory is implemented.
- Guest history/trend access is intentionally blocked.
- RAG is optional and can fall back to approved curated explanations.
- Live RAGAS quality scoring was not measured during TIP-007.
- Production deployment approval is a Human Owner decision, not a Builder
  declaration.
