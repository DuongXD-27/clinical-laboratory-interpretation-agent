# Evaluation Artifact Consolidation Manifest

CLEAN-002 consolidates only byte-identical evaluation artifacts. Distinct JSON
snapshots and distinct safety states remain separate even when filenames match.

## Exact duplicate mappings

| Former path | Canonical retained path | SHA-256 | Context and reason |
|---|---|---|---|
| `eval/manual/pre_rag_fix/TC-G2-01.json` | `eval/manual/TC-G2-01.json` | `387dfae4a88b277477186940e3ba4a0b49e1ed94a28da096fdd46682254e89f7` | Pre-RAG label preserved here; bytes were identical to the canonical case. |
| `eval/manual/pre_rag_fix/TC-G2-02.json` | `eval/manual/TC-G2-02.json` | `337c714103af183e74f8ec94991f6a2b6d40a964bed3ae301dc911f204a2db58` | Pre-RAG label preserved here; bytes were identical to the canonical case. |
| `eval/manual/pre_rag_fix/TC-G2-03.json` | `eval/manual/TC-G2-03.json` | `b1c97ff2e807a86af686682b3e587a8b0766ea93fea0efee9333c5fec616e75d` | Pre-RAG label preserved here; bytes were identical to the canonical case. |
| `eval/manual/pre_rag_fix/TC-G2-04.json` | `eval/manual/TC-G2-04.json` | `ea7a1362e8cbe5752708587b3262de15ed26f6d9de7dfe8b62a1dfcf36bf85cf` | Pre-RAG label preserved here; bytes were identical to the canonical case. |
| `eval/manual/pre_rag_fix/TC-G2-05.json` | `eval/manual/TC-G2-05.json` | `7d2ac7c68e49c3c086b93267ad11b7c09f006612b0089d62617744255c546f47` | Pre-RAG label preserved here; bytes were identical to the canonical case. |
| `eval/manual/pre_rag_fix/verified_reference_rules.json` | `eval/manual/verified_reference_rules.json` | `7ff5a64d72c59c0344b2e723bf5c509c651bc73bf4dc1e6cdc3035a9275267e9` | Pre-RAG rule snapshot was byte-identical to the canonical verified snapshot. |
| `eval/manual/post_rag_fix/verified_reference_rules.json` | `eval/manual/verified_reference_rules.json` | `7ff5a64d72c59c0344b2e723bf5c509c651bc73bf4dc1e6cdc3035a9275267e9` | Post-RAG rule snapshot was byte-identical to the canonical verified snapshot. |
| `eval/manual/post_safety_fix_attempt2_preconsent/TC-G2-01.json` | `eval/manual/post_safety_fix/TC-G2-01.json` | `06bc7b68a95cb6f6bd89adce9ee9e599cffbc5c000c03e5eb1c9643744a85675` | Named attempt remains traceable here; content equals the retained post-safety case. |
| `eval/manual/post_safety_fix_attempt2_preconsent/TC-G2-02.json` | `eval/manual/post_safety_fix/TC-G2-02.json` | `2e27c1d0ff27ae56653ea624525fb47d679897372754f0f3b6a5742af61b438f` | Named attempt remains traceable here; content equals the retained post-safety case. |
| `eval/manual/post_safety_fix_attempt2_preconsent/TC-G2-03.json` | `eval/manual/post_safety_fix/TC-G2-03.json` | `1abc0f04134c3640c3087230f77599d6f57e1adb1f12112ddfcfa2b60494b629` | Named attempt remains traceable here; content equals the retained post-safety case. |
| `eval/manual/post_safety_fix_attempt2_preconsent/TC-G2-04.json` | `eval/manual/post_safety_fix/TC-G2-04.json` | `6203d3dea7320c591df9b992160502a2bf5f80d61fe8c9ad26f9756e155605fc` | Named attempt remains traceable here; content equals the retained post-safety case. |
| `eval/manual/post_safety_fix_attempt2_preconsent/TC-G2-05.json` | `eval/manual/post_safety_fix/TC-G2-05.json` | `38fd9d8c7640f7f52f51ac42e8009094ffb3d832c4c629e32ff71ad645349336` | Named attempt remains traceable here; content equals the retained post-safety case. |
| `eval/manual/response_quality_post_a2_report.md` | `eval/manual/response_quality_baseline_report.md` | `7a5581af9dce9e8293221ed74e32d641267cd24446533ff617a57acb8e4d3b3b` | Run label preserved here; the Markdown report was byte-identical. Distinct `response_quality_post_a2.json` is retained. |
| `eval/manual/response_quality_post_v1_4b_report.md` | `eval/manual/response_quality_baseline_report.md` | `7a5581af9dce9e8293221ed74e32d641267cd24446533ff617a57acb8e4d3b3b` | Run label preserved here; the Markdown report was byte-identical. Distinct `response_quality_post_v1_4b.json` is retained. |

## Report generation anomaly

`response_quality_baseline_report.md`, `response_quality_post_a2_report.md`, and
`response_quality_post_v1_4b_report.md` were byte-identical even though their
paired JSON snapshots differ. This is a `REPORT_GENERATION_ANOMALY`, not evidence
that the runs were identical. The baseline Markdown is retained as the canonical
content, both later run labels are mapped above, and all three distinct JSON
snapshots are retained for forensic comparison.
