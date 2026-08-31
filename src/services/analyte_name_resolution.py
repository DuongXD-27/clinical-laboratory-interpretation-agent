"""Conservative lexical resolution primitives for locked analyte names.

This module handles presentation noise only. It never infers analyte identity
from values, units, reference intervals, or medical similarity.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "UNSUPPORTED"]

OCR_RUNTIME_ALIAS_GROUPS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "WBC": (
            "WBC",
            "Số lượng bạch cầu (WBC)",
            "Bạch cầu (WBC)",
            "Bạch cầu WBC",
            "WBC bạch cầu",
            "W.B.C",
            "White blood cell count",
            "White blood cells",
            "Leukocyte count",
            "Leucocyte count",
            "Tổng số bạch cầu",
            "Tổng bạch cầu",
        ),
        "RBC": (
            "RBC",
            "Số lượng hồng cầu (RBC)",
            "Hồng cầu (RBC)",
            "Hồng cầu RBC",
            "RBC hồng cầu",
            "R.B.C",
            "Red blood cell count",
            "Red blood cells",
            "Erythrocyte count",
            "So luong hong cau RBC",
            "Tổng số hồng cầu",
            "Tổng hồng cầu",
        ),
        "HGB": (
            "HGB",
            "Nồng độ huyết sắc tố (HGB)",
            "Huyết sắc tố (HGB)",
            "Huyết sắc tố HGB",
            "Hemoglobin HGB",
            "Haemoglobin HGB",
            "H.G.B",
            "Nong do huyet sac to HGB",
            "Lượng huyết sắc tố",
            "Lượng hemoglobin",
            "Hemoglobin concentration",
        ),
        "HCT": (
            "HCT",
            "Thể tích khối hồng cầu trong máu toàn phần (HCT)",
            "Dung tích hồng cầu (HCT)",
            "Hematocrit HCT",
            "Haematocrit HCT",
            "HCT hematocrit",
            "H.C.T",
            "The tich khoi hong cau HCT",
            "Thể tích khối hồng cầu",
            "Tỷ lệ thể tích hồng cầu",
            "Packed cell volume",
        ),
        "MCV": (
            "MCV",
            "Thể tích trung bình hồng cầu (MCV)",
            "Thể tích hồng cầu trung bình (MCV)",
            "MCV hồng cầu",
            "Mean corpuscular volume",
            "Mean cell volume",
            "M.C.V",
            "The tich trung binh hong cau MCV",
            "Thể tích TB hồng cầu",
            "Hồng cầu MCV",
        ),
        "MCH": (
            "MCH",
            "Lượng huyết sắc tố trung bình hồng cầu (MCH)",
            "Huyết sắc tố trung bình hồng cầu (MCH)",
            "MCH hồng cầu",
            "Mean corpuscular hemoglobin",
            "Mean cell hemoglobin",
            "M.C.H",
            "Luong huyet sac to trung binh hong cau MCH",
            "Lượng Hb trung bình hồng cầu",
            "Hb trung bình hồng cầu",
        ),
        "MCHC": (
            "MCHC",
            "Nồng độ huyết sắc tố trung bình hồng cầu (MCHC)",
            "Nồng độ Hb trung bình hồng cầu (MCHC)",
            "MCHC hồng cầu",
            "Mean corpuscular hemoglobin concentration",
            "Mean cell hemoglobin concentration",
            "M.C.H.C",
            "Nong do huyet sac to trung binh hong cau MCHC",
            "Nồng độ HST trung bình hồng cầu",
            "Hb concentration corpuscular",
        ),
        "RDW-CV": (
            "Độ phân bố hồng cầu (RDW-CV)",
            "Dải phân bố hồng cầu (RDW-CV)",
            "RDW CV",
            "RDW-CV",
            "RDWCV",
            "R.D.W-C.V",
            "Red cell distribution width CV",
            "Red blood cell distribution width",
            "Do phan bo hong cau RDW CV",
            "Độ rộng phân bố hồng cầu",
        ),
        "PLT": (
            "PLT",
            "Số lượng tiểu cầu (PLT)",
            "Tiểu cầu (PLT)",
            "Tiểu cầu PLT",
            "PLT tiểu cầu",
            "P.L.T",
            "Platelet count",
            "Platelets",
            "Thrombocyte count",
            "So luong tieu cau PLT",
            "Tổng số tiểu cầu",
            "Tổng tiểu cầu",
        ),
        "Neutrophils %": (
            "Neutrophils %",
            "Tỷ lệ bạch cầu trung tính (NEUT%)",
            "Tỷ lệ bạch cầu trung tính (NEU%)",
            "Bạch cầu trung tính (NEUT%)",
            "Bạch cầu trung tính NEUT%",
            "NEUT%",
            "NEU%",
            "Neutrophils percent",
            "Neutrophil percentage",
            "Segmented neutrophils %",
            "Ty le bach cau trung tinh NEUT%",
            "Phần trăm bạch cầu trung tính",
        ),
        "Neutrophils abs": (
            "Neutrophils abs",
            "Số lượng bạch cầu trung tính (NEUT#)",
            "Số lượng bạch cầu trung tính (NEU#)",
            "Bạch cầu trung tính tuyệt đối (NEUT#)",
            "Bạch cầu trung tính NEUT#",
            "NEUT#",
            "NEU#",
            "ANC",
            "Absolute neutrophil count",
            "Neutrophils absolute",
            "Neutrophil abs",
            "So luong bach cau trung tinh NEUT#",
        ),
        "Lymphocytes %": (
            "Lymphocytes %",
            "Tỷ lệ bạch cầu lympho (LYMPH%)",
            "Tỷ lệ bạch cầu lympho (LYM%)",
            "Bạch cầu lympho (LYMPH%)",
            "Bạch cầu lympho LYMPH%",
            "LYMPH%",
            "LYM%",
            "Lymphocytes percent",
            "Lymphocyte percentage",
            "Lympho bào %",
            "Ty le bach cau lympho LYMPH%",
            "Phần trăm lympho",
        ),
        "Lymphocytes abs": (
            "Lymphocytes abs",
            "Số lượng bạch cầu lympho (LYMPH#)",
            "Số lượng bạch cầu lympho (LYM#)",
            "Bạch cầu lympho tuyệt đối (LYMPH#)",
            "Bạch cầu lympho LYMPH#",
            "LYMPH#",
            "LYM#",
            "Absolute lymphocyte count",
            "Lymphocytes absolute",
            "Lymphocyte abs",
            "Lympho bào tuyệt đối",
            "So luong bach cau lympho LYMPH#",
        ),
        "Monocytes %": (
            "Monocytes %",
            "Tỷ lệ bạch cầu mono (MONO%)",
            "Tỷ lệ bạch cầu mono (MON%)",
            "Bạch cầu mono (MONO%)",
            "Bạch cầu mono MONO%",
            "MONO%",
            "MON%",
            "Monocytes percent",
            "Monocyte percentage",
            "Mono %",
            "Ty le bach cau mono MONO%",
            "Phần trăm mono",
        ),
        "Monocytes abs": (
            "Monocytes abs",
            "Số lượng bạch cầu mono (MONO#)",
            "Số lượng bạch cầu mono (MON#)",
            "Bạch cầu mono tuyệt đối (MONO#)",
            "Bạch cầu mono MONO#",
            "MONO#",
            "MON#",
            "Absolute monocyte count",
            "Monocytes absolute",
            "Monocyte abs",
            "Mono tuyệt đối",
            "So luong bach cau mono MONO#",
        ),
        "Eosinophils %": (
            "Eosinophils %",
            "Tỷ lệ bạch cầu ái toan (EO%)",
            "Tỷ lệ bạch cầu ái toan (EOS%)",
            "Bạch cầu ái toan (EO%)",
            "Bạch cầu ái toan EOS%",
            "EO%",
            "EOS%",
            "Eosinophils percent",
            "Eosinophil percentage",
            "Eos %",
            "Ty le bach cau ai toan EO%",
            "Phần trăm ái toan",
        ),
        "Eosinophils abs": (
            "Eosinophils abs",
            "Số lượng bạch cầu ái toan (EO#)",
            "Số lượng bạch cầu ái toan (EOS#)",
            "Bạch cầu ái toan tuyệt đối (EO#)",
            "Bạch cầu ái toan EOS#",
            "EO#",
            "EOS#",
            "Absolute eosinophil count",
            "Eosinophils absolute",
            "Eosinophil abs",
            "Eos tuyệt đối",
            "So luong bach cau ai toan EO#",
        ),
        "Sodium": (
            "Sodium",
            "Natri máu (Na)",
            "Natri (Na)",
            "Sodium Na",
            "Na+",
            "Na",
            "Sodium ion",
            "Serum sodium",
            "Blood sodium",
            "Nồng độ natri",
            "Nong do natri Na",
        ),
        "Chloride": (
            "Chloride",
            "Clor máu (Cl-)",
            "Clorua (Cl)",
            "Chloride Cl",
            "Chloride Cl-",
            "Cl",
            "Cl-",
            "Serum chloride",
            "Blood chloride",
            "Nồng độ clor",
            "Nong do clor Cl",
        ),
        "Fasting plasma glucose": (
            "Glucose máu lúc đói",
            "Đường huyết lúc đói",
            "Đường máu lúc đói",
            "Fasting blood glucose",
            "Fasting plasma glucose",
            "Fasting glucose",
            "FPG",
            "FBG",
            "Glu lúc đói",
            "Glucose fasting",
            "Duong huyet luc doi",
        ),
        "HbA1c": (
            "HbA1c",
            "Hb A1c",
            "A1c",
            "Hemoglobin A1c",
            "Haemoglobin A1c",
            "Glycated hemoglobin",
            "Glycosylated hemoglobin",
            "Đường huyết trung bình HbA1c",
            "Xét nghiệm HbA1c",
            "HBA1C",
        ),
        "Creatinine": (
            "Creatinin máu",
            "Creatinine máu",
            "Creatinin",
            "Creatinine",
            "CREA",
            "CRE",
            "Serum creatinine",
            "Blood creatinine",
            "Nồng độ creatinin",
            "Nong do creatinin",
        ),
        "Urea": (
            "Ure máu",
            "Urê máu",
            "Urea máu",
            "Urea",
            "Ure",
            "Urê",
            "Serum urea",
            "Blood urea",
            "Nồng độ ure",
            "Nong do ure",
        ),
        "Uric acid": (
            "Acid uric máu",
            "Axit uric máu",
            "Uric acid",
            "Uric Acid",
            "Acid Uric",
            "Axit uric",
            "Serum uric acid",
            "Blood uric acid",
            "Nồng độ acid uric",
            "Nong do acid uric",
        ),
        "AST": (
            "AST",
            "AST (GOT)",
            "AST (SGOT)",
            "SGOT",
            "GOT",
            "Aspartate aminotransferase",
            "Aspartate transaminase",
            "Men gan AST",
            "Hoạt độ AST",
            "AST máu",
        ),
        "ALT": (
            "ALT",
            "ALT (GPT)",
            "ALT (SGPT)",
            "SGPT",
            "GPT",
            "Alanine aminotransferase",
            "Alanine transaminase",
            "Men gan ALT",
            "Hoạt độ ALT",
            "ALT máu",
        ),
        "GGT": (
            "GGT",
            "Gamma GT",
            "Gamma-GT",
            "Gamma glutamyl transferase",
            "Gamma glutamyl transpeptidase",
            "Gamma-glutamyl transferase",
            "Men gan GGT",
            "Hoạt độ GGT",
            "GGT máu",
            "γ-GT",
        ),
        "Total bilirubin": (
            "Bilirubin toàn phần",
            "Bilirubin TP",
            "Bilirubin total",
            "Total bilirubin",
            "TBIL",
            "T-BIL",
            "Bilirubin toàn phần (TP)",
            "Nồng độ bilirubin toàn phần",
            "Nong do bilirubin toan phan",
            "Total bili",
        ),
        "Total protein": (
            "Protein toàn phần",
            "Protein TP",
            "Total protein",
            "Protein total",
            "TP protein",
            "Total serum protein",
            "Serum total protein",
            "Đạm toàn phần",
            "Nồng độ protein toàn phần",
            "Nong do protein toan phan",
        ),
        "Albumin": (
            "Albumin",
            "Albumin máu",
            "Serum albumin",
            "Blood albumin",
            "ALB",
            "Albumine",
            "Nồng độ albumin",
            "Nong do albumin",
            "Albumin huyết thanh",
            "Albumin serum",
        ),
        "Total cholesterol": (
            "Cholesterol toàn phần",
            "Total cholesterol",
            "Cholesterol total",
            "Cholesterol TP",
            "Tổng cholesterol",
            "Cholesterol toàn phần (TC)",
            "Serum total cholesterol",
            "Blood total cholesterol",
            "Nồng độ cholesterol toàn phần",
            "Nong do cholesterol toan phan",
        ),
        "Triglyceride": (
            "Triglyceride",
            "Triglycerides",
            "Triglycerid",
            "TG",
            "Triglyceride máu",
            "Triglycerid máu",
            "Serum triglyceride",
            "Blood triglyceride",
            "Mỡ máu triglyceride",
            "Nồng độ triglyceride",
        ),
        "LDL-C": (
            "LDL-C",
            "LDL C",
            "LDLC",
            "LDL-Cholesterol",
            "LDL cholesterol",
            "LDL-cho.",
            "LDL cho",
            "Cholesterol LDL",
            "Low density lipoprotein cholesterol",
            "Nồng độ LDL cholesterol",
        ),
        "HDL-C": (
            "HDL-C",
            "HDL C",
            "HDLC",
            "HDL-Cholesterol",
            "HDL cholesterol",
            "HDL-cho.",
            "HDL cho",
            "Cholesterol HDL",
            "High density lipoprotein cholesterol",
            "Nồng độ HDL cholesterol",
        ),
        "Potassium": (
            "Potassium",
            "Kali máu (K+)",
            "Kali (K+)",
            "Potassium K",
            "Potassium K+",
            "K+",
            "K",
            "Potassium ion",
            "Serum potassium",
            "Blood potassium",
            "Nồng độ kali",
            "Nong do kali K",
        ),
    }
)


def _flatten_runtime_aliases(groups: Mapping[str, tuple[str, ...]]) -> dict[str, str]:
    return {alias: canonical for canonical, aliases in groups.items() for alias in aliases}


# Identity-only aliases verified as exact lexical equivalents. Clinical rules
# and source data remain unchanged.
SAFE_RUNTIME_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        **_flatten_runtime_aliases(OCR_RUNTIME_ALIAS_GROUPS),
        "Triglycerid": "Triglyceride",
    }
)

# Labels whose analyte family is recognizable but whose locked canonical rule
# requires a qualifier absent from the source label.
AMBIGUOUS_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "glucose": "Fasting plasma glucose",
        "glucose mau": "Fasting plasma glucose",
        "duong huyet": "Fasting plasma glucose",
    }
)

_HOSPITAL_PREFIXES = (
    "dinh luong",
    "xet nghiem",
)
_ANNOTATION_RE = re.compile(r"[\[(]([^\])]+)[\])]", re.IGNORECASE)
_SAFE_SPECIMEN_ANNOTATIONS = frozenset({"mau", "blood"})


@dataclass(frozen=True)
class AnalyteNameResolution:
    status: ResolutionStatus
    raw_name: str
    normalized_name: str
    lookup_key: str
    canonical_name: str | None
    specimen_annotations: tuple[str, ...] = ()
    reason: str = ""


def normalize_analyte_lookup_key(value: Any) -> str:
    """Normalize safe lexical variation without adding medical semantics."""
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("đ", "d").replace("%", " percent ").replace("#", " abs ")
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [{"percentage": "percent", "absolute": "abs"}.get(token, token) for token in tokens]
    if len(tokens) >= 2 and all(len(token) == 1 and token.isalpha() for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)


def _structural_candidate(value: Any) -> tuple[str, tuple[str, ...]]:
    raw_name = str(value or "").strip()
    annotations: list[str] = []

    def remove_safe_annotation(match: re.Match[str]) -> str:
        annotation = normalize_analyte_lookup_key(match.group(1))
        if annotation in _SAFE_SPECIMEN_ANNOTATIONS:
            annotations.append(annotation)
            return " "
        return match.group(0)

    without_safe_annotations = _ANNOTATION_RE.sub(remove_safe_annotation, raw_name)
    candidate = normalize_analyte_lookup_key(without_safe_annotations)
    for prefix in _HOSPITAL_PREFIXES:
        if candidate == prefix:
            candidate = ""
            break
        if candidate.startswith(f"{prefix} "):
            candidate = candidate[len(prefix) + 1 :]
            break
    return candidate, tuple(dict.fromkeys(annotations))


def analyte_lookup_candidates(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return exact-first lookup candidates and preserved specimen annotations."""
    exact = normalize_analyte_lookup_key(value)
    structural, annotations = _structural_candidate(value)
    parenthetical = tuple(
        normalize_analyte_lookup_key(match)
        for match in _ANNOTATION_RE.findall(str(value or ""))
        if normalize_analyte_lookup_key(match) not in _SAFE_SPECIMEN_ANNOTATIONS
    )
    without_annotations = normalize_analyte_lookup_key(_ANNOTATION_RE.sub(" ", str(value or "")))
    candidates = tuple(dict.fromkeys(key for key in (exact, structural, without_annotations, *parenthetical) if key))
    return candidates, annotations


def resolve_analyte_name(
    value: Any,
    alias_map: Mapping[str, str],
) -> AnalyteNameResolution:
    """Resolve exact/approved lexical forms, then fail closed on ambiguity."""
    raw_name = str(value or "").strip()
    candidates, annotations = analyte_lookup_candidates(raw_name)
    for candidate in candidates:
        canonical = alias_map.get(candidate)
        if canonical:
            return AnalyteNameResolution(
                status="RESOLVED",
                raw_name=raw_name,
                normalized_name=candidate,
                lookup_key=candidate,
                canonical_name=canonical,
                specimen_annotations=annotations,
                reason="approved_exact_or_lexical_match",
            )

    for candidate in reversed(candidates):
        possible_canonical = AMBIGUOUS_LABELS.get(candidate)
        if possible_canonical:
            return AnalyteNameResolution(
                status="AMBIGUOUS",
                raw_name=raw_name,
                normalized_name=candidate,
                lookup_key=candidate,
                canonical_name=None,
                specimen_annotations=annotations,
                reason=f"missing required qualifier for {possible_canonical}",
            )

    key = candidates[-1] if candidates else ""
    return AnalyteNameResolution(
        status="UNSUPPORTED",
        raw_name=raw_name,
        normalized_name=key,
        lookup_key=key,
        canonical_name=None,
        specimen_annotations=annotations,
        reason="no approved deterministic alias",
    )
