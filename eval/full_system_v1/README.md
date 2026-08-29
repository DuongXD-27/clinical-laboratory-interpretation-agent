# VMEC-05 Golden Set V1 — Phase A

This package is intentionally limited to Golden Set construction and review.
It does **not** call the production checker, critical detector, retriever, LLM,
agent, API, database, or frontend, and it does not calculate system scores.

## Build the candidate set

```powershell
$env:PYTHONUTF8='1'
.\scratch\python3119\python.exe eval\full_system_v1\build_golden_set.py
```

The builder reads only:

- authoritative files under `data/reference/`;
- explicit medical/product contracts documented in the repository;
- fixed evaluation-intent fixtures declared inside the builder.

It writes candidate JSONL files, the inventory, the case-level traceability
queue, `review_decisions.json`, a manifest, and
`GOLDEN_V1_FREEZE_REPORT.md` below this directory. Every candidate
contains `case_id`, `gold_source`, `gold_derivation`, `expected`,
`review_status`, `review_decision_ids`, and `gold_version`.

Review uses five states: `AUTO_DERIVED`, `HUMAN_REVIEW_REQUIRED`,
`MEDICAL_REVIEW_REQUIRED`, `HUMAN_APPROVED`, and `MEDICAL_APPROVED`. Approval is
performed on decision families, not by approving equivalent cases one by one.

Golden V1 is frozen as `VMEC_GOLDEN_SET_V1_FROZEN_2026-08-29`. Final counts are
`AUTO_DERIVED=633`, `HUMAN_APPROVED=270`, `MEDICAL_APPROVED=124`, and
`MEDICAL_REVIEW_REQUIRED=0`. The manifest records SHA-256 hashes for all six
case files, `review_decisions.json`, the builder, and all file-backed
authoritative artifacts. Phase B has not started, and Phase B output may not be
used to alter the frozen expectations.

## Approval gate

Do not run the production system against these candidates until the Human owner
explicitly replies:

`APPROVE GOLDEN V1 — START PHASE B`
