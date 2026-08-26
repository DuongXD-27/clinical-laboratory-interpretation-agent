# LumiLab 35-Analyte Name Resolution Matrix

This report inventories identity metadata only. It does not alter or reinterpret
reference ranges, thresholds, units, demographic rules, or medical source text.

## Resolution contract

- Precedence: exact canonical/approved alias → normalized approved alias → safe
  structural hospital-wrapper candidate → explicit ambiguity → unsupported.
- Safe lexical normalization: Unicode NFKD, Vietnamese diacritic-insensitive
  matching, case/space normalization, punctuation and conventional dotted
  abbreviation normalization, and `%`/`absolute` semantics preservation.
- Structurally recognized wrappers: `Định lượng ...`, `Xét nghiệm ...`, `(máu)`,
  and `[Máu]`. A stripped candidate resolves only when the remaining core is an
  exact approved canonical name or alias.
- Alias classes: A = SAFE_EXACT_EQUIVALENT, B = SAFE_LEXICAL_VARIANT,
  C = SAFE_ABBREVIATION, D = AMBIGUOUS_DO_NOT_MAP,
  E = WRONG_SEMANTICS_DO_NOT_MAP, F = UNKNOWN_NEEDS_REVIEW.

## Authoritative locked set

`WBC, RBC, HGB, HCT, MCV, MCH, MCHC, RDW-CV, PLT, Neutrophils %, Neutrophils abs, Lymphocytes %, Lymphocytes abs, Monocytes %, Monocytes abs, Eosinophils %, Eosinophils abs, Sodium, Potassium, Chloride, Fasting plasma glucose, HbA1c, Creatinine, Urea, Uric acid, AST, ALT, GGT, Total bilirubin, Total protein, Albumin, Total cholesterol, Triglyceride, HDL-C, LDL-C`

LOCKED_COUNT=35

## Coverage matrix

| Canonical | Safe aliases / variants | VN variants | EN variants | Ambiguous or conflicting labels | Rule / unit / semantic qualifiers | Collision | Tests | Result |
|---|---|---|---|---|---|---:|---|---|
| WBC | W.B.C [C], wrapper forms [B] | Bạch cầu; Số lượng bạch cầu [A] | WBC [C] | W8C [F] | RI; 10^9/L; WHOLE_BLOOD | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| RBC | wrapper forms [B] | Hồng cầu; Số lượng hồng cầu [A] | RBC [C] | corrupted OCR [F] | RI; 10^12/L; WHOLE_BLOOD | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| HGB | wrapper forms [B] | Huyết sắc tố [A] | Hemoglobin [A] | corrupted OCR [F] | RI; g/L; WHOLE_BLOOD | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| HCT | wrapper forms [B] | — | Hematocrit [A] | corrupted OCR [F] | RI; L/L; WHOLE_BLOOD | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| MCV | wrapper/case forms [B] | — | MCV [C] | corrupted OCR [F] | RI; fL; WHOLE_BLOOD | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| MCH | wrapper/case forms [B] | — | MCH [C] | corrupted OCR [F] | RI; pg; WHOLE_BLOOD | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| MCHC | wrapper/case forms [B] | — | MCHC [C] | corrupted OCR [F] | RI; g/L; WHOLE_BLOOD | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| RDW-CV | RDW [C], RDW CV [B] | — | RDW [C] | other RDW subtype [D] | RI; %; WHOLE_BLOOD; CV | 0 | canonical/alias/lexical/fail-closed | AMBIGUOUS_PROTECTED |
| PLT | wrapper forms [B] | Tiểu cầu [A] | PLT [C] | corrupted OCR [F] | RI; 10^9/L; WHOLE_BLOOD | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| Neutrophils % | percentage forms [B] | Bạch cầu trung tính % [A] | NEU/NEUT percentage [C] | bare Neutrophils [D]; absolute count [E] | RI; %; WHOLE_BLOOD; FRACTION | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Neutrophils abs | absolute forms [B] | Bạch cầu trung tính tuyệt đối [A] | NEU/NEUT absolute [C] | bare Neutrophils [D]; percentage [E] | RI; 10^9/L; WHOLE_BLOOD; ABSOLUTE | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Lymphocytes % | percentage forms [B] | Lympho bào % [A] | LYM percentage [C] | bare Lymphocytes [D]; absolute count [E] | RI; %; WHOLE_BLOOD; FRACTION | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Lymphocytes abs | absolute forms [B] | Lympho bào tuyệt đối [A] | LYM absolute [C] | bare Lymphocytes [D]; percentage [E] | RI; 10^9/L; WHOLE_BLOOD; ABSOLUTE | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Monocytes % | percentage forms [B] | Bạch cầu mono % [A] | MONO percentage [C] | bare Monocytes [D]; absolute count [E] | RI; %; WHOLE_BLOOD; FRACTION | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Monocytes abs | absolute forms [B] | Bạch cầu mono tuyệt đối [A] | MONO absolute [C] | bare Monocytes [D]; percentage [E] | RI; 10^9/L; WHOLE_BLOOD; ABSOLUTE | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Eosinophils % | percentage forms [B] | Bạch cầu ái toan % [A] | EOS percentage [C] | bare Eosinophils [D]; absolute count [E] | RI; %; WHOLE_BLOOD; FRACTION | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Eosinophils abs | absolute forms [B] | Bạch cầu ái toan tuyệt đối [A] | EOS absolute [C] | bare Eosinophils [D]; percentage [E] | RI; 10^9/L; WHOLE_BLOOD; ABSOLUTE | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Sodium | Na [C], wrapper forms [B] | Natri [A] | Sodium [A] | corrupted OCR [F] | RI; mmol/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| Potassium | K+ [C], wrapper forms [B] | Kali [A] | Potassium [A] | corrupted OCR [F] | RI; mmol/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| Chloride | Cl- [C], wrapper forms [B] | Clor [A] | Chloride [A] | corrupted OCR [F] | RI; mmol/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| Fasting plasma glucose | wrapper forms retain fasting core [B] | Đường huyết lúc đói; Glucose máu lúc đói [A] | Fasting Blood Glucose [A] | Glucose; Glucose máu; Đường huyết [D] | CDL; mmol/L; FASTING; PLASMA | 0 | canonical/alias/lexical/ambiguity | AMBIGUOUS_PROTECTED |
| HbA1c | wrapper/case forms [B] | — | HbA1c [C] | generic glucose [E] | CDL; %; WHOLE_BLOOD | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| Creatinine | Creatinin [B], wrapper forms [B] | Creatinin [B] | Creatinine [A] | eGFR [E] | RI; umol/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| Urea | wrapper/case forms [B] | — | Urea [A] | BUN [D] | RI; mmol/L; SERUM_OR_PLASMA | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| Uric acid | Acid Uric [B], wrapper forms [B] | Acid Uric [B] | Uric acid [A] | Urea [E] | RI; umol/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| AST | AST (GOT), AST (SGOT) [C] | — | AST/SGOT [C] | ALT [E] | ONE_SIDED_LIMIT; U/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| ALT | ALT (GPT), ALT (SGPT) [C] | — | ALT/SGPT [C] | AST [E] | ONE_SIDED_LIMIT; U/L; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/fail-closed | ROBUST |
| GGT | wrapper/case forms [B] | — | GGT [C] | other transferases [E] | ONE_SIDED_LIMIT; U/L; SERUM_OR_PLASMA | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| Total bilirubin | wrapper forms [B] | Bilirubin toàn phần [A] | Total bilirubin [A] | Bilirubin [D]; direct/indirect bilirubin [E] | ONE_SIDED_LIMIT; umol/L; TOTAL; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Total protein | wrapper forms [B] | Protein toàn phần [A] | Total Protein [A] | Protein [D]; fractions [E] | RI; g/L; TOTAL; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| Albumin | wrapper/case forms [B] | — | Albumin [A] | total protein [E] | RI; g/L; SERUM_OR_PLASMA | 0 | canonical/lexical/fail-closed | CANONICAL_ONLY |
| Total cholesterol | hospital wrapper fixture [B] | Cholesterol toàn phần [A] | Total Cholesterol [A] | Cholesterol [D]; HDL/LDL fractions [E] | BAND; mmol/L; TOTAL; SERUM_OR_PLASMA | 0 | canonical/alias/fixture/do-not-map | AMBIGUOUS_PROTECTED |
| Triglyceride | Triglycerides; Triglycerid [B] | Triglycerid [B] | Triglyceride(s) [B] | corrupted OCR [F] | BAND; mmol/L; FASTING_PREFERRED; SERUM_OR_PLASMA | 0 | canonical/alias/fixture/fail-closed | ROBUST |
| HDL-C | HDL C; HDL-cho. [B/C] | — | HDL-Cholesterol [A] | HDL [D] | BAND; mmol/L; FRACTION; SERUM_OR_PLASMA | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |
| LDL-C | LDL C; LDL-cho. [B/C] | — | LDL-Cholesterol [A] | LDL [D]; calculated/direct ambiguity [D] | BAND; mmol/L; FRACTION; METHOD_UNSPECIFIED | 0 | canonical/alias/lexical/do-not-map | AMBIGUOUS_PROTECTED |

## Collision and ambiguity audit

- Existing catalog aliases: 59.
- Added identity-only safe aliases: 1 (`Triglycerid` → `Triglyceride`).
- Effective safe aliases after: 60.
- Deterministic normalized collisions: 0.
- Explicit ambiguous labels: `Glucose`, `Glucose máu`, `Đường huyết`.
- Unsupported/conflicting labels remain outside deterministic aliases, including
  bare differential names, generic bilirubin/protein/cholesterol, LDL, HDL,
  BUN, eGFR, and severely corrupted OCR strings.

## Observed fixture trace

| OCR raw name | Normalized structural core | Lookup result |
|---|---|---|
| Định lượng Cholesterol toàn phần (máu) | cholesterol toan phan | RESOLVED → Total cholesterol |
| Định lượng Triglycerid (máu) [Máu] | triglycerid | RESOLVED → Triglyceride |
| Định lượng Glucose [Máu] | glucose | AMBIGUOUS; no canonical result |
