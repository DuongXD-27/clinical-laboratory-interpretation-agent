# VMEC-05 — TIP-DATA-004 FRONTEND + MOCK CATALOG ALIGNMENT

## ROLE

Bạn là BUILDER.

Dependencies đã hoàn thành:

- TIP-DATA-001 — consistency guardrails
- TIP-DATA-002 — canonical analyte catalog
- TIP-DATA-003 — backend/runtime catalog alignment

Canonical catalog hiện tại:

data/reference/analyte_catalog.json

Backend authority:

analyte identity / alias / runtime status / canonical unit / canonical group
→ analyte_catalog.json

Medical numeric authority vẫn tách riêng:

reference ranges / critical thresholds / conversions
→ existing deterministic medical artifacts

## OBJECTIVE

Align frontend manual-entry metadata và mock analyte identity với canonical catalog nhưng:

- không thay medical numeric semantics;
- không mở rộng runtime support;
- không sửa backend architecture;
- không sửa orchestrator;
- không sửa RAG;
- không biến mock-only analyte thành supported;
- không tự thêm conversion factor.

Mục tiêu cuối:

canonical catalog
      │
      ├── backend identity/status
      ├── frontend analyte identity/group metadata
      └── mock identity validation

trong khi runtime capability vẫn giữ nguyên.

---

# 1. LOCKED POLICIES

APPROVED exact set vẫn là:

- WBC
- RBC
- HGB
- Fasting plasma glucose
- HbA1c
- LDL-C
- HDL-C
- Creatinine
- Potassium

Uric acid:
HOLD

eGFR:
UNSUPPORTED

Không thay các decision này.

BASO và MPV hiện chưa có human decision.

Không tự thêm BASO/MPV vào canonical catalog hoặc runtime.

Nếu mock có BASO/MPV:
report chúng là unresolved/mock-only debt.

---

# 2. ABSOLUTE BOUNDARIES

DO NOT TOUCH:

src/orchestrator/**
RAG/retrieval/**
critical thresholds
reference numeric values
medical explanations
database
auth/history/trend
deployment

Không sửa các known response-quality failures.

Không đổi runtime approved set.

---

# 3. PRE-FLIGHT

Run:

git status --short --untracked-files=all
git diff --name-only
git diff --stat
git log --oneline -10

Working tree phải không chứa thay đổi của TIP khác trong các file DATA-004 cần sửa.

Nếu có:
report CONFLICT_RISK và không overwrite.

---

# 4. FOCUSED SCAN

Read:

data/reference/analyte_catalog.json
src/services/analyte_catalog.py

frontend/src/lib/manualEntry.mjs

data/mock/templates/**
data/mock/generated/** nếu thực sự còn được runtime/test sử dụng

tests liên quan frontend/manual/mock/catalog

Search:

rg "manualEntry" frontend tests
rg "Triglycerides|RDW|AST \(GOT\)|ALT \(GPT\)|Sodium \(Na\)|Chloride \(Cl-\)|Uric Acid|eGFR|BASO|MPV" data frontend tests

Trước khi sửa, tạo inventory:

mock/display name
→ canonical candidate
→ catalog status
→ unit
→ group
→ classification

Classification:

CANONICAL
KNOWN_ALIAS
HOLD
UNSUPPORTED
UNRESOLVED

Không đoán.

---

# 5. FRONTEND MANUAL ENTRY

Mục tiêu:

frontend không duy trì một analyte identity taxonomy độc lập trái với canonical catalog.

Tuy nhiên:

KHÔNG bắt buộc frontend phải đọc JSON trực tiếp ở runtime nếu architecture hiện tại không phù hợp.

Có thể:

A. derive/generate frontend metadata từ canonical catalog;
B. tạo validated adapter/build artifact;
C. giữ manualEntry nhưng thêm strict sync tests nếu migration trực tiếp gây conflict lớn.

Chọn giải pháp nhỏ nhất, phù hợp stack hiện tại.

Không tạo source-of-truth thứ ba.

---

# 6. SIX-GROUP TAXONOMY

Canonical groups:

hematology
electrolytes
glucose
renal
liver
lipids

Frontend nên align semantic grouping với canonical taxonomy.

Display labels tiếng Việt có thể map:

hematology → Huyết học
electrolytes → Điện giải
glucose → Đường huyết
renal → Chức năng thận
liver → Chức năng gan
lipids → Mỡ máu

Không thay backend legacy three-group adapter trong TIP này.

Frontend display taxonomy và backend legacy grouping có thể khác representation nhưng phải cùng canonical source.

---

# 7. MOCK ALIAS ALIGNMENT

Các mock name như:

Triglycerides
RDW
AST (GOT)
ALT (GPT)
Sodium (Na)
Chloride (Cl-)
Uric Acid
eGFR

phải được phân loại.

Nếu tên đã là approved canonical alias:
map/validate về canonical.

Nếu HOLD:
giữ HOLD semantics.

Nếu UNSUPPORTED:
mock được phép chứa nếu fixture mục đích là demo/unsupported scenario, nhưng phải explicit.

Nếu unresolved:
không tự tạo alias.

Report.

Không silently sửa mock nhằm khiến runtime support nó.

---

# 8. MOCK SUPPORT STATUS

Nếu mock hiện dễ khiến người đọc hiểu mọi analyte đều runtime-supported:

thiết kế representation nhỏ nhất để phân biệt ít nhất:

SUPPORTED
NON_RUNTIME / DEMO_ONLY
UNRESOLVED

Nhưng chỉ implement metadata mới nếu scan chứng minh consumer/test có nơi hợp lý dùng nó.

Không redesign toàn mock schema nếu không cần.

Nếu schema change gây rộng:
report follow-up thay vì implement.

---

# 9. UNIT POLICY — CRITICAL

Không yêu cầu:

frontend unit == canonical unit

một cách máy móc.

Phân biệt:

canonical/reference unit
input/display unit
conversion-supported unit

Ví dụ cần audit:

HCT:
frontend %
reference L/L

lipids:
mock/frontend mg/dL
reference mmol/L

RDW:
%CV / %

Với mỗi mismatch:

1. tìm conversion hiện có;
2. xác minh runtime có thực sự support conversion;
3. nếu có → UI có thể giữ display/input unit và validate contract;
4. nếu không → KHÔNG tự thêm conversion.

Không thay conversion factor.

Không sửa medical number.

Nếu frontend hiện cho nhập một unit runtime không xử lý được:
report HIGH-RISK UNIT CONTRACT GAP.

Chỉ sửa nếu solution hoàn toàn deterministic và sử dụng existing conversion contract.

---

# 10. eGFR

eGFR có thể xuất hiện trong mock nhưng:

runtime_status = UNSUPPORTED

Do not:

- calculate eGFR;
- add RI;
- mark supported;
- expose như analyte supported trong manual entry nếu UI hiện mang nghĩa runtime-support.

Nếu cần giữ trong mock:
phải identifiable là unsupported/demo fixture.

---

# 11. URIC ACID

Uric acid:

runtime_status = HOLD

Không expose như fully supported analyte.

Không thêm range.

Không thêm conversion.

Nếu frontend hiện đang cho nhập như supported:
align presentation/support status với HOLD policy mà không phá unrelated UI.

---

# 12. BASO / MPV

Không có human support decision.

Do not add to catalog.

Do not approve.

Classify:

UNRESOLVED_MOCK_ANALYTE

Nếu mock bắt buộc giữ chúng:
guardrail phải cho thấy chúng có chủ đích tồn tại ngoài supported catalog.

Report decision required.

---

# 13. REQUIRED TESTS

UI-MOCK-001
Frontend supported analyte identity resolves to canonical catalog.

UI-MOCK-002
Frontend canonical group mapping matches six-group catalog.

UI-MOCK-003
No frontend analyte is accidentally treated as APPROVED unless catalog says APPROVED.

UI-MOCK-004
Uric acid remains non-approved/HOLD.

UI-MOCK-005
eGFR remains UNSUPPORTED.

UI-MOCK-006
Known mock aliases resolve deterministically where catalog alias exists.

UI-MOCK-007
Unresolved mock analytes are explicit and cannot silently become runtime-supported.

UI-MOCK-008
Unit input/display contract is valid for supported analytes.

UI-MOCK-009
No new conversion factor introduced.

UI-MOCK-010
TIP-DATA-001/002/003 guardrails remain green.

---

# 14. IMPORTANT TEST RULE

Do not create tests that simply whitelist every current mismatch forever.

Bad:

KNOWN_BAD = [38 names]
assert mock_name in catalog or mock_name in KNOWN_BAD

Better:

each exception must carry explicit status/reason:

mock name
canonical resolution if any
support status
reason

Temporary debt must remain visible.

---

# 15. EXPECTED DIFF

Prefer:

frontend/src/lib/manualEntry.mjs
small frontend catalog adapter/generated artifact if justified
mock files only where necessary
focused tests

Avoid modifying dozens of mock JSON files merely for formatting/name cleanup.

No format churn.

If 20+ mock files would need edits:
consider validation/adapter instead and report why.

---

# 16. VERIFY

Run relevant frontend/unit tests if available.

Run:

python -m pytest tests/test_data -q

and catalog/runtime alignment tests.

If frontend changed:

npm run lint

and targeted frontend tests/build where practical.

Do not fix unrelated failures.

---

# 17. ACCEPTANCE CRITERIA

AC-01
Frontend analyte identity/group metadata aligns with canonical catalog.

AC-02
No runtime capability expansion.

AC-03
Uric acid remains HOLD.

AC-04
eGFR remains UNSUPPORTED.

AC-05
BASO/MPV are not silently promoted.

AC-06
Mock aliases are either canonical-resolvable or explicitly unresolved.

AC-07
Unit mismatch is either validated through an existing conversion path or reported, not guessed.

AC-08
No medical numeric value changes.

AC-09
Backend behavior remains unchanged.

AC-10
Prior DATA guardrails remain green.

---

# 18. STOP CONDITIONS

STOP/PARTIAL if:

- unit alignment requires new medical conversion;
- BASO/MPV support must be decided;
- frontend architecture requires major redesign;
- mock schema migration becomes repository-wide;
- canonical catalog conflicts with actual UI business semantics;
- teammate modifications conflict with required frontend file.

Do not self-decide these.

---

# 19. COMPLETION REPORT

Return:

# COMPLETION REPORT — TIP-DATA-004

## STATUS
DONE / PARTIAL / BLOCKED

## FRONTEND AUTHORITY — BEFORE / AFTER

## MANUAL ENTRY RESULT

supported entries:
hold entries:
unsupported entries:
unresolved entries:

## GROUP ALIGNMENT

canonical groups:
frontend labels:
mismatches remaining:

## MOCK ALIGNMENT

mock unique names:
canonical:
aliases resolved:
HOLD:
UNSUPPORTED:
UNRESOLVED:

List unresolved explicitly.

## UNIT CONTRACT AUDIT

| Analyte | UI/Mock Unit | Canonical Unit | Existing Conversion | Action |

Do not omit HCT/lipid mismatches.

## URIC ACID

## eGFR

## BASO / MPV

## FILES CHANGED

## TEST RESULTS

DATA-001:
DATA-002:
DATA-003:
DATA-004 targeted:
frontend lint/tests:
broader data tests:

## MEDICAL DATA CHANGES

Expected:
NONE

## RUNTIME CAPABILITY CHANGES

Expected:
NONE

## BACKEND BEHAVIOR CHANGES

Expected:
NONE

## CONFLICT RISK

## REMAINING DECISIONS

## DEVIATIONS

## RECOMMENDATION FOR NEXT TIP

Do not implement next TIP.

# FINAL RULE

The purpose is not to make every mock name look identical.

The purpose is:

canonical identity
+
explicit support status
+
safe unit contract
+
consistent frontend grouping

without turning unsupported/demo data into medical runtime capability.