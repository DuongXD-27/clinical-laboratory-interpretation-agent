# Medical Baseline Audit Artifacts

These files are audit/provenance evidence. They are **not** runtime medical
authorities. Runtime authorities remain under `data/reference/`.

All artifacts below were moved byte-for-byte from the tracked `scratch/` tree
during CLEAN-002. None is imported or read by the application at runtime.

| Current path | Former scratch path | SHA-256 | Purpose and provenance | Introduction commit | Runtime consumes it |
|---|---|---|---|---|---|
| `authoring/authoring_map_dump.txt` | `scratch/authoring_map_dump.txt` | `725d1ef20a6894e0ca0a32471cea19c822d05a287ac199e204181f08ba42e808` | Human-readable dump of the 65-row reference authoring map, including authority URLs and rule metadata. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `authoring/snapshot_35_extracted.json` | `scratch/snapshot_35_extracted.json` | `1c0f5f788af96187b67bb57fc2ae8bdfaa1baf6a2711c7246e5cc22410847370` | Extracted 35-analyte audit snapshot used while reconciling authoring evidence. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `source-extraction/extracted_pdf_strings.txt` | `scratch/extracted_pdf_strings.txt` | `e38b12a02c8d7c996310a975019eadbd4ad44c95ab3eaa22880288c100c28612` | Raw PDF string-extraction evidence retained to reproduce source inspection. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `source-extraction/vmj_9352.pdf` | `scratch/vmj_9352.pdf` | `1d135f74cd8b6fb3d006ce29ba4129ede20d83567aa47057ff03db99042be48b` | Downloaded Vietnam Medical Journal article used as reference-interval provenance. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `source-extraction/vmj_clean_extracted_text.txt` | `scratch/vmj_clean_extracted_text.txt` | `505148c62ae45319123be2646b9d7eb8eff0750fd8d3e86a4f8d3088ae0d7650` | Cleaned/examined text extraction from the VMJ source PDF. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `reference-build/quarantine.csv` | `scratch/test_out/quarantine.csv` | `f8cd17a48820e5164735e07aad36d0059a69537ee166ac115612606607d45229` | Empty-quarantine output from the accepted deterministic reference build. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `reference-build/reference_build_report.json` | `scratch/test_out/reference_build_report.json` | `be5dd70db52d15285cac5f4b307529b545f584e2440fbdf27be87e8d5759ea02` | Build receipt recording input integrity, accepted rows, output hashes, and generation time. Paths inside the receipt record the original run location. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `reference-build/reference_ranges.csv` | `scratch/test_out/reference_ranges.csv` | `cf34d12ee3b668eda469ae20177eadb77ca414b34a9404386ba4e2ecdd4adfae` | Deterministic CSV output captured as medical baseline evidence. | `a7c9ad019f9b6fc554c2ed9b7e19b1c10e1d1ffa` | No |
| `reference-build/reference_ranges.json` | `scratch/test_out/reference_ranges.json` | `d0396e0b5edd4ba370f3a8ef684ebe3943dca7f010916c9db2ae58fd484278af` | Deterministic JSON output captured as medical baseline evidence. | `1170e32369153e7ab8b60eabf3ab43731df35b97` | No |

## Removed placeholder

`scratch/raw_pdf_text.txt` was a zero-byte placeholder (`SHA-256
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
It contained no evidence, had no consumers, and remains recoverable from Git
history.
