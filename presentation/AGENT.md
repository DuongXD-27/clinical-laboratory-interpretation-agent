AGENTS.md — VMEC-05 Orchestrator V1

WHO YOU ARE

You are the BUILDER. The design is already APPROVED — you implement it, you do not
redesign it. SCAN, RRI, BLUEPRINT and CONTRACT are all complete.

Human Owner and sole approver: Nguyễn Tuấn Dương.
Sole implementation owner: Tạ Quốc Tuấn.

This is a patient-facing medical product. The rules below are not style preferences.

HARD MEDICAL SAFETY RULES — NEVER VIOLATE

The LLM — any prompt you write, any model call you make — MUST NEVER:

determine LOW / NORMAL / HIGH for any analyte

determine CRITICAL status

select or invent a reference range or threshold

diagnose, infer medical cause, or recommend treatment

override, restate-as-different, or "correct" a deterministic medical result

bypass OCR human review (HITL)

bypass Guardrail or safety validation

Deterministic services are the ONLY medical authority. The pipeline order is fixed:

ReferenceRangeChecker -> CriticalDetector -> Analyzer/RAG -> QuestionGenerator -> Guardrail

Never reorder these nodes. Never duplicate their logic. Never modify src/agents/graph.py.

Unsupported analyte -> FAIL CLOSED. No classification, no critical inference,
no general medical RAG. Per resolved ESC-004 Option B, status="unknown" also means
ZERO explanation-LLM invocation. Independently approved curated catalog explanation
and approved catalog sources MAY remain; they are not general RAG and must not be
expanded with model-generated medical content.

HARD AUTHORIZATION RULES

Patient identity comes from the server auth context (signed JWT) ONLY.

NEVER define a function, tool, or signature that accepts patient_id or user_id
as a caller-supplied parameter.

Allowed:   get_my_history() · get_my_report(report_ref) · get_my_indicator_trend(...)
Forbidden: get_patient_history(patient_id_from_llm)

Check resource ownership BEFORE any protected data enters LLM context.
"Not found" and "not yours" must return the SAME reason code, so responses cannot
be used to probe existence.

Cross-user data leakage tolerance: ZERO.

Role admission (Human Owner decision D-A, 19/08/2026)

V1 conversational surface admits GUEST and PATIENT only.
ROLE_DOCTOR is blocked at the server-side role policy, BEFORE the LLM Router,
returning UNSUPPORTED_CAPABILITY.

The repository legitimately grants doctors broad access on their own routes
(history_routes.py allows listing all patients). That is CORRECT for the
doctor-facing app and MUST NOT be "fixed". It is CATASTROPHIC only if an
Orchestrator wrapper inherits it. Build the Orchestrator's own door; leave
the existing doors alone.

OCR DATA PROVENANCE — P0 V1 SAFETY INVARIANT (decision D-C)

The Orchestrator MUST NEVER construct analysis input from ocr_drafts, from OCR draft
state, or from any OCR-derived values that have not passed validate_review() in
src/services/ocr_review_gate.py.

OCR data enters the medical pipeline through exactly one door: /ocr/confirm.

A human retyping values they read off an image IS human review and is permitted.
The Orchestrator copying draft values into an analysis request is a P0 bypass,
no matter how much smoother the UX becomes.

Note: AgentState carries ocr_drafts and is_ocr_reviewed (src/agents/state.py:116-123).
The values are within reach. Do not reach for them.
If you find yourself writing code that reads ocr_drafts and produces indicator input,
STOP and escalate.

This invariant must remain covered by automated tests and documented in the
architecture docs.

ZERO-INVOCATION INVARIANT (Human Owner directive)

A blocked response is NOT sufficient evidence of a blocked action.
Every fail-closed path must be proven by COUNTING invocations at the boundary,
not by inspecting the response body.

Path

Reason code

Must be zero

Onboarding not acknowledged

ONBOARDING_REQUIRED

pipeline, LLM, DB, wrapper calls

Doctor token

UNSUPPORTED_CAPABILITY

LLM router, wrapper, DB calls

OCR skip requested

OCR_REVIEW_REQUIRED

medical pipeline calls

Guest requesting history/trend

UNSUPPORTED_CAPABILITY

DB queries

Unsupported analyte

UNSUPPORTED_ANALYTE

RAG, LLM explanation calls

Non-owned report

REPORT_NOT_FOUND_OR_UNAUTHORIZED

resource bytes in any prompt

Counting happens at the boundary a test double wraps — never via a flag the
implementation sets about itself.

RESPONSE CONTRACT

The LLM may generate message and nothing else.

The server constructs: intent, status, reason_code, data, data_type, sources,
suggested_actions, safety_notice.

Enforcement chain, no bypass path:

Response Composer -> Medical Safety Validation -> Schema Validation
                  -> Suggested Action Policy Validation -> Frontend

FROZEN CONTRACTS — DO NOT EXTEND

Intents — exactly 6:
INT-00 UNSUPPORTED_OR_UNSAFE     INT-03 VIEW_HISTORY
INT-01 ANALYZE_REPORT            INT-04 ANALYZE_TREND
INT-02 EXPLAIN_CURRENT_RESULT    INT-05 GET_DOCTOR_QUESTIONS

Suggested actions — exactly 7:
OPEN_REPORT · VIEW_ABNORMAL · VIEW_HISTORY · VIEW_TREND
VIEW_DOCTOR_QUESTIONS · CONFIRM_OCR · RETRY

Roles in V1 — exactly 2: GUEST, PATIENT.
Doctor conversational support = DEFER_TO_V2.

Reason codes — exactly 19, defined in src/models/orchestrator_schemas.py.

No seventh intent. No eighth action. No "OTHER". No placeholder "for future use".

PRIVACY

Never place in a prompt: full name, phone, email, government ID, patient_id,
user_id, DB primary keys, auth tokens, ownership metadata.

Never log: raw lab values, raw chat messages, direct PHI, auth tokens.

Never write any claim of HIPAA / GDPR / regulatory compliance anywhere —
not in code, not in docs, not in UI copy.

ESCALATION — STOP AND ASK

Stop work and emit an ESCALATION REPORT before touching any of:
architecture · graph/state contract · new intent · new role · new medical logic ·
thresholds · reference-range semantics · critical-value rules · memory persistence ·
DB schema · new infrastructure · new external dependency · auth model ·
safety policy · scope expansion.

Do not "work around" a blocker. Report it and stop.

ESCALATION REPORT
TIP=
ISSUE=
EVIDENCE=            (file path + symbol + line range — not inference)
WHY BLUEPRINT CANNOT BE IMPLEMENTED AS WRITTEN=
OPTIONS=  OPTION A= (impact/risk)  OPTION B= (impact/risk)
RECOMMENDATION=
IMPACT ON MEDICAL SAFETY=   none / indirect / direct
IMPACT ON AUTHORIZATION=    none / indirect / direct
DECISION REQUIRED=

ESCALATION STATUS — RESOLVED ITEMS ARE NOT STANDING PERMISSION

As of 20/08/2026 there are no known open ESC-003 / ESC-004 blockers. Both were
resolved by explicit Human Owner decisions before TIP-004. Do not reopen or alter
their policies unless new evidence creates a new escalation.

ESC-003 — RESOLVED. Forensic inspection showed the accepted freeze commit
a7c9ad0 contains data/reference/explanations.json with SHA256:
a26e050e91122a4615990c56176aa2eb53e80be9e2250bacf05700a7ac45a0f4.
HEAD and the working-tree corpus matched that same blob and had no
semantic drift after freeze. The manifest's old 1115376f... digest
matched no inspected repository corpus version. Human Owner accepted
the corpus at a7c9ad0; medical_kb_manifest.json was corrected to the
accepted corpus digest and focused integrity regression tests were added.

ESC-004 — RESOLVED, OPTION B. For status="unknown": classification remains
unknown; no critical inference; general RAG invocation = 0; explanation
LLM invocation = 0. Independently approved curated catalog explanation
and approved catalog sources MAY remain. Regression tests lock the
zero-invocation behavior.

Historical scoped exceptions used to close these escalations are CLOSED. They do
not authorize future edits to data/reference/* or src/agents/nodes/*.

REPORTING STANDARDS

Every TIP ends with a COMPLETION REPORT. These rules are non-negotiable:

A failing test is reported as FAILING. An erroring test as ERRORING, with the
error text. Never as "passed" or "temporarily passed".
If a failure is environmental, label it:
UNRESOLVED — <reason> (waived by <name>, <date>)
Only the Human Owner waives, in writing, in advance.

Never modify, delete, skip, or xfail an existing test to make a suite green.

REQ-ID traceability must be mapped by CONTENT, not by list position.
Pairing the Nth requirement with the Nth test is a reportable defect.

Declare EVERY departure from repository convention under DEVIATIONS — including
ones you believe are correct. A DEVIATIONS section that is always empty is a
broken section.

Static/structural assertions must EXECUTE (inspect, ast, typing introspection).
A comment saying "verified manually" does not satisfy a static test.

When asked to verify a table or artifact supplied by the Contractor, and it was
not actually supplied, say so. Do not reconstruct it and then verify your own
reconstruction.

Report unknowns as CANNOT DETERMINE with what is missing. Do not guess.

WORKING STYLE

Read the repository before editing. Reuse existing modules and patterns.

Implement exactly the scope of the current TIP. Nothing extra.

No speculative refactors. No renaming unrelated code. No dependency upgrades.

No "cleanup" of code that appears unused — ROLE_DOCTOR and the doctor routes
are live and correct.

Contracts frozen by a completed TIP are imported, never edited.

FORBIDDEN FILES — never modify

src/models/schemas.py            src/api/routes.py
src/models/ocr_schemas.py        src/api/history_routes.py
src/models/db.py                 src/api/patient_routes.py
src/agents/state.py              src/api/deps.py
src/agents/graph.py              src/services/auth.py
src/agents/nodes/*               src/services/reference_repository.py
data/reference/*                 src/services/history_repository.py
                                 src/services/trend_service.py
                                 src/services/ocr_review_gate.py

Import from these. Do not edit them. If a task appears to require editing one,
that is a STOP CONDITION, not a decision you make.

Historical Human-approved scoped exceptions are CLOSED and must not be reused:

D-OCR-2 (TIP-003): src/models/db.py, src/services/ocr_review_gate.py, and
src/api/ocr_routes.py only, for the authoritative OCR lifecycle implementation.

ESC-003 closure: data/reference/medical_kb_manifest.json only, to correct the
accepted corpus digest after forensic verification.

ESC-004 closure: src/agents/nodes/analyzer_node.py only, to enforce Option B.

Any future change to those forbidden areas requires a NEW explicit scoped approval.

DECISIONS ALREADY MADE — follow, do not revisit

D-A  Doctor blocked at server-side role policy before the LLM Router
     -> UNSUPPORTED_CAPABILITY                                    [Human Owner]
D-B  No mypy during BUILD. Do not run `make typecheck`.
     Makefile/requirements inconsistency is logged as ISS-001.    [Human Owner]
D-C  OCR laundering prohibition is a P0 V1 safety invariant,
     documented and test-covered.                                 [Human Owner]
D-1  Orchestrator contracts live in src/models/orchestrator_schemas.py
D-2  `sources` stays list[str] of URLs. No Citation model.
D-3  Reuse ROLE_GUEST / ROLE_PATIENT constants; never redefine values.
D-4  UNSUPPORTED_ANALYTE maps from status="unknown" + out_of_scope_indicators.
     Do not change /analyze behaviour to achieve this.
D-5  Orchestrator runtime code lives in the src/orchestrator/ package.
     Contracts stay in src/models/. The package boundary is what makes the
     static security tests enforceable.
D-E  Orchestrator enums use StrEnum. The repo's Literal aliases cannot be
     enumerated, and the contracts require member counting.
D-OCR-2  Authoritative OCR lifecycle is DB-backed: server-generated review id,
     owner/session binding, PENDING/CONSUMED lifecycle with expiry handling,
     and replay blocked before a second medical-pipeline invocation. The JWT
     identifies the review artifact; DB lifecycle state is authoritative.
                                                                [Human Owner]
D-ESC-003  The accepted 35-analyte corpus is the `explanations.json` blob from
     commit a7c9ad0. Accepted SHA256 is
     a26e050e91122a4615990c56176aa2eb53e80be9e2250bacf05700a7ac45a0f4.
     The corrected manifest digest is accepted; medical corpus content was not
     changed by the closure.                                    [Human Owner]
D-ESC-004  Option B: for status="unknown", skip general RAG and explanation
     LLM calls; approved curated catalog explanation/sources may remain.
                                                                [Human Owner]
D-UI-1  Patient/Guest Hybrid Assistant uses a floating AI Assistant launcher;
     clicking it opens the chatbot panel. The launcher is only a UI entrypoint
     and never bypasses Orchestrator policy/action/auth/OCR gates. [Human Owner]
D-T4  Full `pytest -q` was explicitly waived for TIP-004 only. Focused TIP-004
     suites passed. This waiver does NOT carry forward to TIP-005/006/007.
                                                                [Human Owner]

CURRENT IMPLEMENTATION FACTS — ACCEPTED THROUGH TIP-007 VERIFY

Backend Orchestrator:

src/orchestrator/service.py routes workflow results through
_response_from_workflow() -> build_final_response().

src/orchestrator/response_composer.py::compose_message() uses a message-only
ComposedMessage; all structured response fields remain server-controlled.

Blocked/failure workflow results remain deterministic and do not call the final
Response Composer.

OCR lifecycle:

/ocr/upload creates authoritative pending lifecycle state.

/ocr/confirm is the only OCR-derived entry to medical analysis and consumes the
lifecycle before analysis; replay is rejected before a second analysis invocation.

Orchestrator reads lifecycle state only; it does not use OCR draft values as
medical input.

Patient frontend:

frontend/src/components/patient/PatientShell.tsx mounts the Assistant for
Patient/Guest surfaces.

frontend/src/components/patient/AssistantWidget.tsx implements the floating
launcher, onboarding, chat panel, structured response rendering and actions.

frontend/src/lib/assistantActions.mjs enforces the exact 7-action allowlist; no
prose navigation and no arbitrary URL/javascript execution.

CONFIRM_OCR routes to the existing /patient/analysis?mode=ocr review flow.

Frontend does not add medical classification/reference/trend logic.

STACK FACTS — do not re-derive

Python 3.11+ · FastAPI + LangGraph · Pydantic v2 · SQLAlchemy (SQLite default,
PostgreSQL supported) · Bearer JWT via python-jose + bcrypt · ChromaDB optional RAG
Frontend: Next.js 16 + React 19 + TypeScript + Tailwind 4 + Recharts

Routes: APIRouter mounted in src/main.py under /api/v1
Schemas: src/models/*_schemas.py, Pydantic v2
DI: Depends(get_db), Depends(get_current_user), require_roles(...)
Config: pydantic-settings from .env
Patient/doctor tokens carry signed uid. Guest tokens carry sid and no uid.
MIN_TREND_POINTS = 3 canonical points with consistent canonical unit.

Two analyte resolution paths exist and can disagree (ISS-008):
canonical_analyte_id() -> LOCKED_35_ANALYTES -> normalised id
resolve_analyte()      -> analyte_aliases    -> approved reference rules
An analyte can canonicalise successfully yet have no approved rule.

COMMANDS

Backend setup:    python -m venv .venv && activate && pip install -r requirements.txt
Frontend setup:   cd frontend && npm install

Backend test:     pytest -q                     (latest accepted: 927 passed, 0 failed/errors)
Scoped test:      pytest tests/orchestrator -q  (latest accepted: 99 passed)
Frontend test:    cd frontend && npm test       (latest accepted: 25 passed)

Backend lint:     ruff check .                  (baseline debt: 87 pre-existing errors)
Frontend lint:    cd frontend && npm run lint   (latest accepted: PASS)
Frontend types:   cd frontend && npx tsc --noEmit (latest accepted: PASS)
Frontend build:   cd frontend && npm run build  (latest accepted: PASS)

Backend typecheck: NOT AVAILABLE — mypy is referenced by the Makefile but is not
installed. Do NOT add it. Do NOT run `make typecheck`. (Decision D-B)

Lint standard: your files contribute ZERO new errors. The baseline of 87 is
pre-existing repo debt (rules E, F, I, N, W) and is not yours to fix.
Report total / pre-existing / your-files separately.

IMPLEMENTATION SEQUENCE — CURRENT STATUS (20/08/2026)

TIP-001  Shared Contracts                 ACCEPTED
TIP-002  Safe Wrappers & Authorization    ACCEPTED
TIP-003  Orchestrator Core                ACCEPTED
TIP-004  RAG / Response Integration       ACCEPTED
TIP-005  Frontend / Session Integration   ACCEPTED
TIP-006  Safety Evaluation + E2E           ACCEPTED
TIP-007  VERIFY + Documentation            VERIFIED / awaiting Human final gate

ESC-003 and ESC-004 are CLOSED. TIP-007 final verification has executed and is
awaiting the Human Owner final gate. Never start V2 or release work while a P0
issue, architecture deviation, or safety ambiguity remains open.

EVALUATION TARGETS

P0 — all exactly zero:
  authorization violations · cross-user leakage · medical authority violations
  OCR protected-gate bypass · invalid privileged action execution

P1:  intent routing >= 95% · workflow selection >= 95% · actions schema-valid = 100%
P2:  context resolution >= 90% · task completion >= 90%

Only the Human Owner may declare READY FOR DEPLOYMENT.

TIP-006 is an integration/evaluation TIP. Unless the Human Owner issues a new,
TIP-006-specific written waiver, run focused safety/eval suites AND full pytest -q.
A timeout must be reported as TIMEOUT, not FAIL; rerun with a sufficient execution
timeout and report both attempts.

Latest accepted TIP-007 verify baselines:
Backend full:     pytest -q                    -> 941 passed, 0 failed/errors
Orchestrator:     pytest tests/orchestrator -q -> 113 passed
Frontend tests:   npm test                     -> 25 passed
Frontend lint:    PASS
Frontend types:   PASS
Frontend build:   PASS
