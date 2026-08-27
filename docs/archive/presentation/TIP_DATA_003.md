# VMEC-05 — TIP-DATA-003 BACKEND / RUNTIME CATALOG ALIGNMENT

## MODE

FOCUSED MIGRATION → BACKWARD COMPATIBILITY → VERIFY

## ROLE

Bạn là BUILDER.

Các trạng thái đã được xác nhận:

```text
TIP-DATA-001: DONE
- Data consistency audit + guardrails
- Medical data changes: NONE

TIP-DATA-002: DONE
- Canonical catalog:
  data/reference/analyte_catalog.json
- Loader/service:
  src/services/analyte_catalog.py
- 36 catalog entries
- APPROVED = 9
- HOLD = 1
- UNSUPPORTED = 26
- Medical data changes: NONE
- Runtime behavior changes: NONE

HAL-039: DONE / VERIFIED
- HAL039_REGRESSION = 0
- HAL-039 quality gate = PASS
```

Current exact runtime-approved analytes:

```text
WBC
RBC
HGB
Fasting plasma glucose
HbA1c
LDL-C
HDL-C
Creatinine
Potassium
```

Locked special status:

```text
Uric acid = HOLD
eGFR = UNSUPPORTED
```

---

# 1. OBJECTIVE

Hiện tại canonical catalog đã tồn tại nhưng runtime vẫn còn đọc identity/support information từ nhiều nơi.

Mục tiêu TIP này:

> Migrate backend analyte identity/support consumers sang canonical analyte catalog để giảm duplicate source-of-truth, trong khi giữ nguyên 100% externally observable runtime behavior.

Canonical catalog phải trở thành authority backend cho các field:

```text
analyte_id
canonical_name
aliases
group
canonical_unit
runtime_status
```

Nhưng KHÔNG trở thành authority cho:

```text
reference ranges
critical thresholds
clinical bands
medical interpretation
unit conversion factors
RAG content
source authority
```

---

# 2. ABSOLUTE BOUNDARIES

## DO NOT TOUCH

```text
frontend/**
data/mock/**
src/orchestrator/**
eval/**
RAG/retrieval/vector-store code
auth/**
history/**
trend/**
database schema/migrations
deployment
```

Đặc biệt:

> KHÔNG sửa 4 orchestrator pytest failures hoặc 11 response-quality failures đã được chứng minh PRE_EXISTING trong HAL-039 verification.

Chúng thuộc remediation track khác.

Không mở rộng scope task để làm repository xanh 125/125.

---

# 3. MEDICAL SAFETY BOUNDARY

ABSOLUTELY FORBIDDEN:

```text
change reference interval
change critical threshold
change clinical band
change comparison operator
change unit conversion factor
change rounding semantics
change diagnostic interpretation
add medical rule
approve additional analyte
calculate eGFR
add Uric acid reference range
```

Expected:

```text
MEDICAL DATA CHANGES = NONE
RUNTIME CAPABILITY CHANGES = NONE
```

---

# 4. PRE-FLIGHT

Trước khi code:

```bash
git status --short --untracked-files=all
git diff --name-only
git diff --stat
git log --oneline -10
```

## GATE

TIP-DATA-001, TIP-DATA-002 và HAL-039 phải đã được commit/tracked.

Nếu dependency còn untracked/uncommitted theo cách có nguy cơ bị overwrite:

```text
STATUS = BLOCKED_BY_UNCOMMITTED_DEPENDENCY
```

Không tự xử lý bằng:

```bash
git reset --hard
git clean -fd
git checkout .
git stash
```

---

# 5. FOCUSED SCAN — KHÔNG CODE TRƯỚC

Đọc:

```text
data/reference/analyte_catalog.json
data/reference/reference_checker_config.json

src/services/analyte_catalog.py
src/services/analyte_resolver.py
src/services/reference_repository.py
src/services/indicator_catalog_service.py
src/services/analyte_sections.py

tests/test_data/test_analyte_catalog_contract.py
tests/test_data/test_data_catalog_consistency.py

tests/test_services/test_analyte_catalog.py
tests/test_services/test_indicator_catalog_service.py
tests/test_services/test_analyte_sections.py
tests/test_services/test_reference_repository.py

tests/test_agents/test_reference_range_checker_node.py
```

Search actual consumers:

```bash
rg "reference_checker_config" src tests
rg "approved_analytes|approved_analyte|APPROVED" src tests
rg "alias|aliases" src/services tests
rg "analyte_catalog|get_analyte_catalog" src tests
rg "analyte_sections" src tests
```

Không giả định danh sách consumer trong prompt là hoàn chỉnh.

---

# 6. OUTPUT SCAN BEFORE IMPLEMENTATION

Tạo internal authority map:

| Field                  | Current authority | Consumers |
| ---------------------- | ----------------- | --------- |
| canonical identity     | ...               | ...       |
| aliases                | ...               | ...       |
| runtime approval       | ...               | ...       |
| canonical unit         | ...               | ...       |
| group                  | ...               | ...       |
| numeric reference rule | ...               | ...       |

Xác định duplicate nào thực sự đang tồn tại.

---

# 7. CORE ARCHITECTURE TARGET

Desired direction:

```text
              analyte_catalog.json
                      │
                      ▼
             analyte_catalog.py
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
 analyte resolver  indicator      group metadata
                   catalog
        │
        ▼
 reference repository/checker
```

Separately:

```text
reference_ranges
critical_thresholds
unit conversions
medical rules
```

tiếp tục có authority riêng.

Không nhập numeric rules vào analyte catalog.

---

# 8. ANALYTE CATALOG SERVICE

Reuse:

```text
src/services/analyte_catalog.py
```

Không tạo service thứ hai.

Expose chỉ API cần thiết.

Conceptually có thể cần equivalent của:

```text
get_analyte_catalog()
resolve_analyte()
get_alias_map()
get_runtime_status()
get_runtime_approved_analytes()
get_canonical_unit()
get_group()
```

Nhưng:

> Không mechanical-add toàn bộ function nếu consumer không cần.

Reuse API hiện tại trước.

Keep module small.

---

# 9. ANALYTE RESOLVER

Nếu `analyte_resolver.py` có:

```text
locked constants
independent canonical-name sets
duplicate alias map
```

mà đã thuộc catalog contract:

migrate sang catalog-derived values.

## Required compatibility

Với mọi alias runtime đang support:

```text
BEFORE alias → canonical
AFTER  alias → canonical
```

phải giống nhau.

Unknown vẫn fail closed.

HOLD vẫn fail closed.

UNSUPPORTED vẫn fail closed.

Không mở rộng alias recognition ngoài catalog đã approved.

---

# 10. REFERENCE REPOSITORY

`reference_repository.py` có thể sử dụng catalog cho:

```text
canonical identity
aliases
runtime approval/status
```

Nhưng numeric rule authority vẫn nằm trong reference data hiện tại.

Invariant:

```text
same currently-supported input
→ same reference classification
```

trước và sau TIP.

Không để catalog `canonical_unit` vô tình override medical reference-rule unit semantics.

---

# 11. INDICATOR CATALOG SERVICE

Nếu service đang giữ duplicate metadata:

```text
canonical name
unit
group
supported status
```

thì migrate field phù hợp sang canonical catalog.

Public output/API contract phải giữ nguyên.

Nếu catalog taxonomy khác legacy API taxonomy:

> dùng internal adapter.

Không đổi client-visible response shape trong TIP này.

---

# 12. GROUP COMPATIBILITY

Canonical catalog:

```text
hematology
electrolytes
glucose
renal
liver
lipids
```

Legacy backend hiện có thể dùng:

```text
hematology
chemistry
lipids
```

TIP này KHÔNG được thay đổi externally observable legacy grouping.

Nếu cần adapter, derive mapping từ behavior/test hiện hữu.

Không dùng medical intuition để tự map.

Ví dụ chỉ mang tính conceptual:

```text
canonical detailed group
        ↓
legacy backend group adapter
        ↓
same existing behavior
```

Frontend taxonomy migration thuộc TIP-DATA-004.

---

# 13. REFERENCE_CHECKER_CONFIG — TRỌNG TÂM TASK

Đọc chính xác:

```text
data/reference/reference_checker_config.json
```

Phân loại từng field:

```text
A. CATALOG_OWNED
B. CHECKER_SPECIFIC
C. MEDICAL_RULE
D. UNKNOWN
```

Potential catalog-owned:

```text
approved analyte names
aliases
canonical identity
canonical unit metadata
```

Potential checker-specific:

```text
checker behavior/configuration
```

Potential medical-rule:

```text
numeric/demographic/reference semantics
```

Không tự move field loại B/C nếu không cần.

---

# 14. DUAL SOURCE-OF-TRUTH POLICY

Sau TIP-DATA-003, không được tồn tại hai independently editable authority cho cùng:

```text
aliases
approved set
canonical identity
runtime status
```

Preferred:

```text
analyte_catalog.json
→ runtime authority
```

Nếu legacy config chưa thể bỏ duplicate field an toàn:

acceptable transitional state:

```text
analyte_catalog.json
→ actual authority

reference_checker_config.json
→ legacy compatibility
→ strict sync validation
```

Nhưng Completion Report phải ghi rõ duplication còn lại.

Không coi việc “hai file giống nhau” là giải quyết source-of-truth.

---

# 15. DO NOT DELETE LEGACY CONFIG BLINDLY

Không xóa `reference_checker_config.json` chỉ để architecture trông sạch.

Nếu file còn checker-specific responsibility:

giữ nó.

Mục tiêu:

> ownership separation

không phải:

> ít file nhất có thể.

---

# 16. APPROVED SET — HARD INVARIANT

Before:

```text
{
 WBC,
 RBC,
 HGB,
 Fasting plasma glucose,
 HbA1c,
 LDL-C,
 HDL-C,
 Creatinine,
 Potassium
}
```

After:

phải EXACTLY giống.

Assert set equality.

Không chỉ:

```python
assert len(approved) == 9
```

---

# 17. ALIAS SNAPSHOT

Trước implementation:

capture tất cả runtime aliases hiện hợp lệ:

```text
alias
canonical_result
```

Sau implementation:

so sánh.

Required:

```text
changed alias mappings = 0
```

Nếu phát hiện existing alias không có trong catalog:

KHÔNG tự thêm ngay.

Report:

```text
CATALOG_GAP
```

Nếu đó là blocker cho backward compatibility → STOP/PARTIAL và báo rõ.

---

# 18. FAIL-CLOSED SNAPSHOT

Test trước/sau ít nhất:

```text
unknown analyte
Uric acid
eGFR
```

Required:

```text
UNKNOWN → not approved
Uric acid → HOLD / not approved
eGFR → UNSUPPORTED / not approved
```

Không được nhận deterministic reference classification mới ngoài behavior đã approved.

---

# 19. TESTS REQUIRED

## RT-CAT-001

Canonical catalog thực sự cung cấp backend identity/support metadata cho consumer đã migrate.

## RT-CAT-002

Exact approved set unchanged.

## RT-CAT-003

Existing alias resolution snapshot unchanged.

## RT-CAT-004

Unknown analyte fail closed.

## RT-CAT-005

Uric acid remains HOLD/non-approved.

## RT-CAT-006

eGFR remains UNSUPPORTED/non-approved.

## RT-CAT-007

Reference-range classifications remain unchanged.

## RT-CAT-008

Indicator catalog public semantics remain compatible.

## RT-CAT-009

Legacy backend grouping remains externally compatible.

## RT-CAT-010

TIP-DATA-001 guardrails pass.

## RT-CAT-011

TIP-DATA-002 catalog contract tests pass.

## RT-CAT-012

No dual-authority drift where migration completed.

Nếu legacy duplicate vẫn tồn tại vì compatibility, test synchronization explicitly.

---

# 20. TEST DESIGN RULE

Ưu tiên behavior test.

Bad:

```python
assert "get_analyte_catalog" in source_code
```

Good:

```text
input alias
→ resolver
→ canonical analyte
→ runtime status
→ expected behavior
```

Chỉ dùng implementation-level assertion khi cần chứng minh không còn hard-coded duplicate authority.

---

# 21. EXPECTED DIFF

Target:

```text
2–5 production Python files
2–4 focused test files
0 frontend files
0 medical numeric JSON changes
0 orchestrator files
0 RAG files
```

Không phải quota.

Chỉ sửa file scan chứng minh cần thiết.

---

# 22. CONFLICT GUARD

Trước khi sửa production file:

```bash
git status --short <file>
git diff -- <file>
```

Nếu có teammate modification:

```text
CONFLICT_RISK
```

Không overwrite.

Không format/rewrite entire module.

Không cleanup unrelated code.

---

# 23. PRE-EXISTING FAILURES POLICY

Trusted known failures ngoài task:

```text
orchestrator:
217 passed / 4 PRE_EXISTING failed

response quality:
114/125
11 PRE_EXISTING failed
```

TIP-DATA-003 không sở hữu chúng.

Nếu chạy broad suite và thấy đúng các failure đó:

report:

```text
KNOWN_PRE_EXISTING
```

Không sửa.

Nếu xuất hiện failure mới liên quan DATA-003:

phải investigate.

---

# 24. VERIFY ORDER

Run:

```bash
python -m pytest tests/test_data/test_analyte_catalog_contract.py -q
python -m pytest tests/test_data/test_data_catalog_consistency.py -q
```

Sau đó targeted tests của file/service đã sửa.

Sau đó:

```bash
python -m pytest tests/test_data -q
```

Sau đó relevant:

```text
analyte catalog
resolver
indicator catalog
analyte sections
reference repository
reference range checker
```

Run Ruff trên changed Python files.

Nếu practical, chạy broader backend regression.

Không cần đạt `125/125` để hoàn thành DATA-003 vì đó là unrelated known quality debt.

---

# 25. DIFF REVIEW

Cuối task:

```bash
git status --short --untracked-files=all
git diff --check
git diff --stat
git diff
```

Nếu staged/new:

```bash
git diff --cached --check
git diff --cached --stat
git diff --cached
```

Audit:

```text
medical number changed?       NO
approved analyte changed?     NO
new capability?               NO
frontend changed?             NO
orchestrator changed?         NO
RAG changed?                  NO
mock changed?                 NO
API contract changed?         NO
format churn?                 NO
```

---

# 26. STOP CONDITIONS

STOP / report PARTIAL nếu:

```text
catalog conflicts with actual runtime alias behavior
same alias resolves to multiple canonical analytes
migration requires changing medical numeric semantics
migration changes approved scope
legacy group compatibility cannot be maintained
public API requires breaking change
reference_checker_config field semantics are ambiguous
teammate conflict exists in required production file
```

Do not self-design around blockers.

---

# 27. ACCEPTANCE CRITERIA

### AC-01

Canonical analyte catalog becomes actual backend authority for migrated identity/support metadata.

### AC-02

Exact 9 approved analytes unchanged.

### AC-03

Existing alias behavior unchanged.

### AC-04

Unknown/HOLD/UNSUPPORTED remain fail-closed.

### AC-05

Reference classification behavior unchanged.

### AC-06

Legacy grouping externally unchanged.

### AC-07

No frontend files changed.

### AC-08

No orchestrator/HAL files changed.

### AC-09

No RAG files changed.

### AC-10

Medical data changes = NONE.

### AC-11

Previous DATA-001 and DATA-002 tests remain green.

### AC-12

Any remaining duplicate authority is explicit and guarded.

---

# 28. COMPLETION REPORT

Return:

# COMPLETION REPORT — TIP-DATA-003

## STATUS

```text
DONE / PARTIAL / BLOCKED
```

## PRE-MIGRATION AUTHORITY MAP

| Field | Authority | Consumers |
| ----- | --------- | --------- |

Cover:

```text
identity
aliases
runtime approval
runtime status
canonical unit
canonical group
numeric reference rules
```

## POST-MIGRATION AUTHORITY MAP

| Field | Authority | Consumers |
| ----- | --------- | --------- |

## MIGRATION SUMMARY

```text
consumers scanned:
consumers migrated:
consumers intentionally retained:
```

## REFERENCE_CHECKER_CONFIG RESULT

```text
catalog-owned fields:
checker-owned fields:
medical-rule fields:
fields migrated:
fields retained:
duplicate authority remaining:
```

## APPROVED EXACT SET

```text
BEFORE:
AFTER:
CHANGED: YES/NO
```

Expected `NO`.

## ALIAS COMPATIBILITY

```text
aliases tested:
unchanged:
changed:
catalog gaps:
```

## FAIL-CLOSED

```text
Uric acid:
eGFR:
unknown:
```

## GROUP COMPATIBILITY

```text
canonical taxonomy:
legacy taxonomy:
observable behavior changed:
```

Expected:

```text
NO
```

## FILES CHANGED

File + exact purpose.

## TESTS

```text
DATA-001:
DATA-002:
DATA-003 targeted:
data suite:
service/reference suite:
ruff:
```

## KNOWN PRE-EXISTING FAILURES

If broad tests encounter the known HAL-independent failures, report separately.

Do not fix.

## MEDICAL DATA CHANGES

Expected:

```text
NONE
```

## RUNTIME CAPABILITY CHANGES

Expected:

```text
NONE
```

## API/UI BEHAVIOR CHANGES

Expected:

```text
NONE
```

## CONFLICT RISK

```text
CONFLICT_RISK_FILES:
UNRELATED_FILES_TOUCHED:
```

## REMAINING DUPLICATE SOURCES OF TRUTH

List explicitly.

## DEVIATIONS

## ISSUES DISCOVERED

Do not fix out-of-scope issues.

## RECOMMENDATION FOR TIP-DATA-004

Identify exactly:

```text
frontend manual entry drift
mock alias drift
mock support-status representation
canonical six-group UI alignment
unit display/input drift
```

and files affected.

DO NOT implement TIP-DATA-004.

---

# FINAL RULE

Success is NOT:

> tất cả code đều dùng một JSON file.

Success is:

> backend có một authority duy nhất cho analyte identity/support metadata, trong khi numeric medical knowledge vẫn có authority chuyên biệt và runtime behavior không thay đổi.

Required end state:

```text
ONE backend authority for identity/support
SEPARATE authority for medical numeric rules
9 approved remain exactly 9
ZERO new medical capability
ZERO medical semantic change
ZERO frontend change
ZERO orchestrator change
ZERO RAG change
```
