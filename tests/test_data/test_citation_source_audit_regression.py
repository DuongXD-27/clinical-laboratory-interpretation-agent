"""Deterministic regression tests for citation source audit manifest compliance.

Ensures:
- Removed source IDs are completely absent from patient-facing corpus.
- Old REPLACE URLs are absent.
- Every replacement URL exactly matches the approved audit manifest.
- All KEEP records remain unmodified.
- No exact duplicate patient-facing URLs remain after removals.
- No homepage-only citations remain (e.g. SRC-TAMANH-CRE).
- Dynamic derivation of corpus manifest fields matches medical_kb_manifest.json without hardcoded assumptions.
- Runtime provenance regression for FPG, HbA1c, Creatinine, and Lipids.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.scripts.ingest_kb import corpus_sha256
from src.services.corpus_builder import build_corpus_chunks
from src.services.corpus_validator import CorpusValidator
from src.services.medical_citations import MedicalCitationRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLANATIONS_PATH = REPO_ROOT / "data/reference/explanations.json"
MANIFEST_PATH = REPO_ROOT / "data/reference/medical_kb_manifest.json"

# Authoritative audit manifest records specification
AUDIT_RECORDS = [
    {
        "analyte": "WBC",
        "source_id": "SRC-VM-WBC-001",
        "source_title": "Ý nghĩa chỉ số bạch cầu trong xét nghiệm máu",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-chi-so-bach-cau-trong-xet-nghiem-mau-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-cac-chi-so-trong-xet-nghiem-mau-vi",
    },
    {
        "analyte": "WBC",
        "source_id": "SRC-LC-WBC-002",
        "source_title": "Chỉ số WBC trong xét nghiệm máu là gì?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-wbc-trong-xet-nghiem-mau-la-gi-co-y-nghia-nhu-the-nao.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/giai-dap-thac-mac-chi-so-wbc-trong-xet-nghiem-mau-la-gi-68482.html",
    },
    {
        "analyte": "WBC",
        "source_id": "SRC-VN-VMJ-HAIHA-WBC",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "WBC",
        "source_id": "SRC-MEDLINEPLUS-WBC",
        "source_title": "White Blood Count (WBC)",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/white-blood-count-wbc/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "WBC",
        "source_id": "SRC-MAYOCLINIC-WBC",
        "source_title": "High white blood cell count",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/symptoms/high-white-blood-cell-count/basics/definition/sym-20050611",
        "action": "REPLACE",
        "replacement_url": "https://www.mayoclinic.org/symptoms/high-white-blood-cell-count/basics/causes/sym-20050611",
    },
    {
        "analyte": "RBC",
        "source_id": "SRC-VM-RBC-001",
        "source_title": "Ý nghĩa chỉ số RBC trong xét nghiệm công thức máu",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-chi-so-rbc-trong-xet-nghiem-cong-thuc-mau-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-xet-nghiem-hong-cau-trong-mau-vi",
    },
    {
        "analyte": "RBC",
        "source_id": "SRC-LC-RBC-002",
        "source_title": "Chỉ số RBC trong xét nghiệm máu nói lên điều gì?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-rbc-trong-xet-nghiem-mau-noi-len-dieu-gi.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/rbc-thap-co-sao-khong-nguyen-nhan-va-cach-cai-thien-an-toan.html",
    },
    {
        "analyte": "RBC",
        "source_id": "SRC-MEDLINEPLUS-RBC",
        "source_title": "Red Blood Cell (RBC) Count",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/red-blood-cell-rbc-count/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "RBC",
        "source_id": "SRC-MAYOCLINIC-RBC",
        "source_title": "High red blood cell count",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/symptoms/high-red-blood-cell-count/basics/definition/sym-20050858",
        "action": "REPLACE",
        "replacement_url": "https://www.mayoclinic.org/symptoms/high-red-blood-cell-count/basics/causes/sym-20050858",
    },
    {
        "analyte": "HGB",
        "source_id": "SRC-VM-HGB-001",
        "source_title": "Chỉ số hemoglobin trong xét nghiệm máu là gì?",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/chi-so-hemoglobin-trong-xet-nghiem-mau-la-gi-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/chi-so-hgb-trong-xet-nghiem-mau-co-y-nghia-gi-vi",
    },
    {
        "analyte": "HGB",
        "source_id": "SRC-LC-HGB-002",
        "source_title": "Chỉ số Hemoglobin (HGB) trong máu có ý nghĩa gì?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-hgb-trong-xet-nghiem-mau-co-y-nghia-nhu-the-nao.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-xet-nghiem-mau-hgb-la-gi-70837.html",
    },
    {
        "analyte": "HGB",
        "source_id": "SRC-MEDLINEPLUS-HGB",
        "source_title": "Hemoglobin Test",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/hemoglobin-test/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HGB",
        "source_id": "SRC-MAYOCLINIC-HGB",
        "source_title": "Hemoglobin test",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/tests-procedures/hemoglobin-test/about/pac-20385075",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HCT",
        "source_id": "SRC-VN-VMJ-HAIHA-HCT",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "MCV",
        "source_id": "SRC-VN-VMJ-HAIHA-MCV",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "MCH",
        "source_id": "SRC-VN-VMJ-HAIHA-MCH",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "MCHC",
        "source_id": "SRC-VN-VMJ-HAIHA-MCHC",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "RDW-CV",
        "source_id": "SRC-VN-VMJ-HAIHA-RDW",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "PLT",
        "source_id": "SRC-VN-VMJ-HAIHA-PLT",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Neutrophils %",
        "source_id": "SRC-VN-VMJ-HAIHA-NEUTP",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Neutrophils abs",
        "source_id": "SRC-VN-VMJ-HAIHA-NEUTA",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Lymphocytes %",
        "source_id": "SRC-VN-VMJ-HAIHA-LYMP",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Lymphocytes abs",
        "source_id": "SRC-VN-VMJ-HAIHA-LYMA",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Monocytes %",
        "source_id": "SRC-VN-VMJ-HAIHA-MONOP",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Monocytes abs",
        "source_id": "SRC-VN-VMJ-HAIHA-MONOA",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Eosinophils %",
        "source_id": "SRC-VN-VMJ-HAIHA-EOSP",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Eosinophils abs",
        "source_id": "SRC-VN-VMJ-HAIHA-EOSA",
        "source_title": "Nghiên cứu khoảng tham chiếu các chỉ số huyết học người trưởng thành",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Sodium",
        "source_id": "SRC-UK-NHS-GLOSHOSP-NA",
        "source_title": "Sodium (Na) Pathology Test Guide",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/sodium-na/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-VM-K-001",
        "source_title": "Kali máu bao nhiêu là bình thường?",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/kali-mau-bao-nhieu-la-binh-thuong-vi",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-LC-K-002",
        "source_title": "Kali máu bình thường có chỉ số bao nhiêu?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/kali-mau-binh-thuong-co-chi-so-bao-nhieu.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-UK-NHS-GLOSHOSP-K",
        "source_title": "Potassium (K) Pathology Handbook",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/potassium-k/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-MEDLATEC-K-HIGH",
        "source_title": "Tăng kali máu",
        "organization": "Bệnh viện Đa khoa MEDLATEC",
        "source_tier": "TIER_3",
        "current_url": "https://medlatec.vn/tu-dien-benh-ly/tang-kali-mau-srsce",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-MEDLATEC-K-LOW",
        "source_title": "Hạ kali máu",
        "organization": "Bệnh viện Đa khoa MEDLATEC",
        "source_tier": "TIER_3",
        "current_url": "https://medlatec.vn/tu-dien-benh-ly/ha-kali-mau-sosia",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Potassium",
        "source_id": "SRC-VM-K-002",
        "source_title": "Ý nghĩa xét nghiệm kali máu",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-xet-nghiem-kali-mau-vi",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Chloride",
        "source_id": "SRC-UK-NHS-GLOSHOSP-CL",
        "source_title": "Chloride Pathology Test Guide",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/chloride-ci/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Fasting plasma glucose",
        "source_id": "SRC-VM-GLU-001",
        "source_title": "Chỉ số đường huyết lúc đói là gì?",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/chi-so-glucose-khi-doi-la-gi-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/xet-nghiem-glucose-huyet-tuong-luc-doi-la-gi-vi",
    },
    {
        "analyte": "Fasting plasma glucose",
        "source_id": "SRC-LC-GLU-002",
        "source_title": "Đường huyết lúc đói bao nhiêu là bình thường?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-glucose-khi-doi-la-gi-bao-nhieu-la-binh-thuong.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-duong-huyet-luc-sang-som-bao-nhieu-la-binh-thuong.html",
    },
    {
        "analyte": "Fasting plasma glucose",
        "source_id": "SRC-MEDLINEPLUS-GLU",
        "source_title": "Blood Glucose Test",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/blood-glucose-test/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Fasting plasma glucose",
        "source_id": "SRC-CDC-GLU",
        "source_title": "Diabetes Testing",
        "organization": "Centers for Disease Control and Prevention (CDC)",
        "source_tier": "TIER_2",
        "current_url": "https://www.cdc.gov/diabetes/diabetes-testing/index.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Fasting plasma glucose",
        "source_id": "SRC-ADA-SOC-2026",
        "source_title": "Standards of Care in Diabetes—2026",
        "organization": "American Diabetes Association (ADA)",
        "source_tier": "TIER_1",
        "current_url": "https://diabetesjournals.org/care/issue/49/Supplement_1",
        "action": "REPLACE",
        "replacement_url": "https://diabetesjournals.org/care/article/49/Supplement_1/S27/163926/2-Diagnosis-and-Classification-of-Diabetes",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-VM-A1C-001",
        "source_title": "Xét nghiệm HbA1c là gì và có ý nghĩa như thế nào?",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/xet-nghiem-hba1c-la-gi-va-co-y-nghia-nhu-the-nao-trong-chan-doan-dieu-tri-tieu-duong-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-xet-nghiem-hba1c-trong-benh-dai-thao-duong-vi",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-LC-A1C-002",
        "source_title": "Chỉ số HbA1c có ý nghĩa gì trong chẩn đoán tiểu đường?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/xet-nghiem-hba1c-la-gi-y-nghia-cua-chi-so-hba1c-trong-chan-doan-tieu-duong.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/xet-nghiem-a1c-la-gi-y-nghia-cua-hb-a1c-trong-viec-kiem-soat-duong-huyet.html",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-MEDLINEPLUS-A1C",
        "source_title": "Hemoglobin A1C (HbA1c) Test",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/hemoglobin-a1c-hba1c-test/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-CDC-A1C",
        "source_title": "Prediabetes and A1C Test",
        "organization": "Centers for Disease Control and Prevention (CDC)",
        "source_tier": "TIER_2",
        "current_url": "https://www.cdc.gov/diabetes/diabetes-testing/prediabetes-a1c-test.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-MAYOCLINIC-A1C",
        "source_title": "A1C test",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/tests-procedures/a1c-test/about/pac-20384643",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-ADA-SOC-2026-A1C",
        "source_title": "Standards of Care in Diabetes—2026",
        "organization": "American Diabetes Association (ADA)",
        "source_tier": "TIER_1",
        "current_url": "https://diabetesjournals.org/care/issue/49/Supplement_1",
        "action": "REPLACE",
        "replacement_url": "https://diabetesjournals.org/care/article/49/Supplement_1/S27/163926/2-Diagnosis-and-Classification-of-Diabetes",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-CDC-A1C-MGMT",
        "source_title": "All About Your A1C",
        "organization": "Centers for Disease Control and Prevention (CDC)",
        "source_tier": "TIER_2",
        "current_url": "https://www.cdc.gov/diabetes/managing/managing-blood-sugar/a1c.html",
        "action": "REMOVE",
        "replacement_url": "",
    },
    {
        "analyte": "HbA1c",
        "source_id": "SRC-ADA-A1C-PATIENT",
        "source_title": "Understanding A1C",
        "organization": "American Diabetes Association (ADA)",
        "source_tier": "TIER_1",
        "current_url": "https://diabetes.org/about-diabetes/a1c",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-VM-CRE-001",
        "source_title": "Ý nghĩa chỉ số xét nghiệm creatinine trong chẩn đoán suy thận",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-chi-so-xet-nghiem-creatinine-trong-chan-doan-suy-vi",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-LC-CRE-002",
        "source_title": "Những điều cần biết về xét nghiệm creatinine máu",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/nhung-dieu-can-biet-ve-xet-nghiem-creatinine-mau.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-MEDLINEPLUS-CRE",
        "source_title": "Creatinine Test",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/lab-tests/creatinine-test/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-NKF-CRE",
        "source_title": "Creatinine and Kidney Disease",
        "organization": "National Kidney Foundation (NKF)",
        "source_tier": "TIER_2",
        "current_url": "https://www.kidney.org/kidney-topics/creatinine",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-TAMANH-CRE",
        "source_title": "Xét nghiệm creatinine đánh giá chức năng thận",
        "organization": "Bệnh viện Đa khoa Tâm Anh",
        "source_tier": "TIER_2",
        "current_url": "https://tamanhhospital.vn",
        "action": "REMOVE",
        "replacement_url": "",
    },
    {
        "analyte": "Creatinine",
        "source_id": "SRC-UHNM-NHS-CREATININE",
        "source_title": "Creatinine Pathology Test Directory",
        "organization": "University Hospitals of North Midlands NHS Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.uhnm.nhs.uk/our-services/pathology/tests/creatinine/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Urea",
        "source_id": "SRC-UK-NHS-GLOSHOSP-UREA",
        "source_title": "Urea Pathology Test Guide",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/urea/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Uric acid",
        "source_id": "SRC-EULAR-GOUT-2016",
        "source_title": "2016 updated EULAR evidence-based recommendations for the management of gout",
        "organization": "European Alliance of Associations for Rheumatology (EULAR)",
        "source_tier": "TIER_1",
        "current_url": "https://ard.bmj.com/content/76/1/29",
        "action": "REPLACE",
        "replacement_url": "https://pubmed.ncbi.nlm.nih.gov/27457514/",
    },
    {
        "analyte": "AST",
        "source_id": "SRC-VN-VMJ-UMCHCMC-AST",
        "source_title": "Xác nhận giá trị tham chiếu một số xét nghiệm sinh hóa tại Bệnh viện Đại học Y Dược TP.HCM",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/10898/9528/19171",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "ALT",
        "source_id": "SRC-VN-VMJ-UMCHCMC-ALT",
        "source_title": "Xác nhận giá trị tham chiếu một số xét nghiệm sinh hóa tại Bệnh viện Đại học Y Dược TP.HCM",
        "organization": "Tạp chí Y học Việt Nam",
        "source_tier": "TIER_1",
        "current_url": "https://tapchiyhocvietnam.vn/index.php/vmj/article/download/10898/9528/19171",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "GGT",
        "source_id": "SRC-UK-NHS-GLOSHOSP-GGT",
        "source_title": "Gamma-GT (GGT) Pathology Handbook",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/gamma-gt-ggt/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Total bilirubin",
        "source_id": "SRC-UK-NHS-GLOSHOSP-BIL",
        "source_title": "Bilirubin (Total) Pathology Directory",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/bilirubin-total-sbr/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Total protein",
        "source_id": "SRC-UK-NHS-GLOSHOSP-TP",
        "source_title": "Protein (Total) Pathology Handbook",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/protein-total/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Albumin",
        "source_id": "SRC-UK-NHS-GLOSHOSP-ALB",
        "source_title": "Albumin Pathology Test Directory",
        "organization": "Gloucestershire Hospitals NHS Foundation Trust",
        "source_tier": "TIER_2",
        "current_url": "https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/albumin/",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "Total cholesterol",
        "source_id": "SRC-NCEP-ATP3-TC",
        "source_title": "Third Report of the National Cholesterol Education Program (NCEP) Expert Panel (Adult Treatment Panel III)",
        "organization": "National Heart, Lung, and Blood Institute (NHLBI)",
        "source_tier": "TIER_1",
        "current_url": "https://www.nhlbi.nih.gov/files/docs/guidelines/atp3full.pdf",
        "action": "REPLACE",
        "replacement_url": "https://www.nhlbi.nih.gov/resources/third-report-expert-panel-detection-evaluation-and-treatment-high-blood-cholesterol-0",
    },
    {
        "analyte": "Triglyceride",
        "source_id": "SRC-NCEP-ATP3-TG",
        "source_title": "Third Report of the NCEP Expert Panel (Adult Treatment Panel III)",
        "organization": "National Heart, Lung, and Blood Institute (NHLBI)",
        "source_tier": "TIER_1",
        "current_url": "https://www.nhlbi.nih.gov/files/docs/guidelines/atp3full.pdf",
        "action": "REPLACE",
        "replacement_url": "https://www.nhlbi.nih.gov/resources/third-report-expert-panel-detection-evaluation-and-treatment-high-blood-cholesterol-0",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-VM-HDL-001",
        "source_title": "Ý nghĩa chỉ số mỡ máu HDL-Choleterol",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/y-nghia-chi-so-mo-mau-hdl-choleterol-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/phan-biet-giua-ldl-cholesterol-va-hdl-cholesterol-vi",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-LC-HDL-002",
        "source_title": "Chỉ số HDL Cholesterol trong xét nghiệm máu nói lên điều gì?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-hdl-cholesterol-trong-xet-nghiem-mau-noi-len-dieu-gi.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/hdl-cholesterol-la-gi-va-nhung-canh-bao-suc-khoe-khi-chi-so-hdl-cholesterol-giam-59240.html",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-MEDLINEPLUS-HDL",
        "source_title": "HDL: The \"Good\" Cholesterol",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/hdlthegoodcholesterol.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-MAYOCLINIC-HDL",
        "source_title": "HDL cholesterol: How to boost your 'good' cholesterol",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/diseases-conditions/high-blood-cholesterol/in-depth/hdl-cholesterol/art-20046388",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-NCEP-ATP3-HDL",
        "source_title": "Third Report of the NCEP Expert Panel (Adult Treatment Panel III)",
        "organization": "National Heart, Lung, and Blood Institute (NHLBI)",
        "source_tier": "TIER_1",
        "current_url": "https://www.nhlbi.nih.gov/files/docs/guidelines/atp3full.pdf",
        "action": "REPLACE",
        "replacement_url": "https://www.nhlbi.nih.gov/resources/third-report-expert-panel-detection-evaluation-and-treatment-high-blood-cholesterol-0",
    },
    {
        "analyte": "HDL-C",
        "source_id": "SRC-AHA-CHOL-TYPES-HDL",
        "source_title": "HDL (Good), LDL (Bad) Cholesterol and Triglycerides",
        "organization": "American Heart Association (AHA)",
        "source_tier": "TIER_1",
        "current_url": "https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-and-triglycerides",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-VM-LDL-001",
        "source_title": "Xét nghiệm LDL-Cholesterol và ý nghĩa các chỉ số",
        "organization": "Hệ thống Y tế Vinmec",
        "source_tier": "TIER_2",
        "current_url": "https://www.vinmec.com/vie/bai-viet/xet-nghiem-ldl-cholesterol-va-y-nghia-cac-chi-so-vi",
        "action": "REPLACE",
        "replacement_url": "https://www.vinmec.com/vie/bai-viet/chi-so-ldl-cholesterol-trong-mau-la-gi-vi",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-LC-LDL-002",
        "source_title": "Chỉ số LDL Cholesterol trong xét nghiệm máu là gì?",
        "organization": "Nhà thuốc Long Châu",
        "source_tier": "TIER_3",
        "current_url": "https://nhathuoclongchau.com.vn/bai-viet/chi-so-ldl-cholesterol-trong-xet-nghiem-mau-la-gi.html",
        "action": "REPLACE",
        "replacement_url": "https://nhathuoclongchau.com.vn/bai-viet/nhung-dieu-can-biet-ve-chi-so-ldl-cholesterol-trong-mau.html/",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-MEDLINEPLUS-LDL",
        "source_title": "LDL: The \"Bad\" Cholesterol",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/ldlthebadcholesterol.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-CDC-LDL",
        "source_title": "LDL and HDL Cholesterol and Triglycerides",
        "organization": "Centers for Disease Control and Prevention (CDC)",
        "source_tier": "TIER_2",
        "current_url": "https://www.cdc.gov/cholesterol/ldl-hdl.htm",
        "action": "REPLACE",
        "replacement_url": "https://www.cdc.gov/cholesterol/about/ldl-and-hdl-cholesterol-and-triglycerides.html",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-MAYOCLINIC-LDL",
        "source_title": "Cholesterol test",
        "organization": "Mayo Clinic",
        "source_tier": "TIER_2",
        "current_url": "https://www.mayoclinic.org/tests-procedures/cholesterol-test/about/pac-20384601",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-NLA-NCEP-2014",
        "source_title": "National Lipid Association Recommendations for Dyslipidemia Management",
        "organization": "National Lipid Association & NCEP ATP III",
        "source_tier": "TIER_1",
        "current_url": "https://www.lipidjournal.com/article/S1933-2874(14)00272-6/fulltext",
        "action": "REPLACE",
        "replacement_url": "https://www.lipid.org/resource/nla-recommendations-for-patient-centered-management-of-dyslipidemia/",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-CDC-CHOL-ABOUT",
        "source_title": "About Cholesterol",
        "organization": "Centers for Disease Control and Prevention (CDC)",
        "source_tier": "TIER_2",
        "current_url": "https://www.cdc.gov/cholesterol/about/index.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-MEDLINEPLUS-CHOL-LEVELS",
        "source_title": "Cholesterol Levels: What You Need to Know",
        "organization": "National Library of Medicine (MedlinePlus)",
        "source_tier": "TIER_2",
        "current_url": "https://medlineplus.gov/cholesterollevelswhatyouneedtoknow.html",
        "action": "KEEP",
        "replacement_url": "",
    },
    {
        "analyte": "LDL-C",
        "source_id": "SRC-AHA-CHOL-TYPES",
        "source_title": "HDL (Good), LDL (Bad) Cholesterol and Triglycerides",
        "organization": "American Heart Association (AHA)",
        "source_tier": "TIER_1",
        "current_url": "https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-and-triglycerides",
        "action": "KEEP",
        "replacement_url": "",
    },
]


def _load_explanations() -> list[dict]:
    return json.loads(EXPLANATIONS_PATH.read_text(encoding="utf-8"))


def _load_sources_map() -> dict[str, dict]:
    data = _load_explanations()
    res: dict[str, dict] = {}
    for entry in data:
        for src in entry.get("sources", []):
            sid = src.get("source_id")
            if sid:
                res[sid] = src
    return res


def test_removed_source_ids_are_completely_absent():
    sources_map = _load_sources_map()
    removed_ids = [r["source_id"] for r in AUDIT_RECORDS if r["action"] == "REMOVE"]
    assert removed_ids == ["SRC-CDC-A1C-MGMT", "SRC-TAMANH-CRE"]
    for rid in removed_ids:
        assert rid not in sources_map, f"Removed source ID {rid} must not exist in explanations.json"


def test_old_replace_urls_are_completely_absent():
    sources_map = _load_sources_map()
    all_current_urls = {src["url"] for src in sources_map.values()}
    replace_records = [r for r in AUDIT_RECORDS if r["action"] == "REPLACE"]
    for r in replace_records:
        old_url = r["current_url"]
        assert old_url not in all_current_urls, (
            f"Old REPLACE URL {old_url} for {r['source_id']} must not be present in explanations.json"
        )


def test_every_replacement_url_matches_approved_manifest_exactly():
    sources_map = _load_sources_map()
    replace_records = [r for r in AUDIT_RECORDS if r["action"] == "REPLACE"]
    assert len(replace_records) == 24
    for r in replace_records:
        sid = r["source_id"]
        assert sid in sources_map, f"Source ID {sid} must be present in explanations.json"
        actual_url = sources_map[sid]["url"]
        expected_url = r["replacement_url"]
        assert actual_url == expected_url, (
            f"Source ID {sid} URL mismatch: expected {expected_url}, got {actual_url}"
        )


def test_all_keep_records_remain_unchanged():
    sources_map = _load_sources_map()
    keep_records = [r for r in AUDIT_RECORDS if r["action"] == "KEEP"]
    assert len(keep_records) == 53
    for r in keep_records:
        sid = r["source_id"]
        assert sid in sources_map, f"KEEP source ID {sid} must be present in explanations.json"
        actual_src = sources_map[sid]
        assert actual_src["url"] == r["current_url"]
        assert actual_src["source_title"] == r["source_title"]
        assert actual_src["organization"] == r["organization"]
        assert actual_src["source_tier"] == r["source_tier"]


def test_no_exact_duplicate_patient_facing_urls_on_same_analyte():
    data = _load_explanations()
    for entry in data:
        analyte = entry.get("canonical_name") or entry.get("name")
        urls = [s["url"] for s in entry.get("sources", []) if "url" in s]
        duplicates = [url for url in set(urls) if urls.count(url) > 1]
        assert not duplicates, f"Analyte {analyte} has duplicate source URLs: {duplicates}"


def test_no_homepage_only_citation_remains_for_creatinine_or_tamanh():
    sources_map = _load_sources_map()
    assert "SRC-TAMANH-CRE" not in sources_map
    for sid, src in sources_map.items():
        assert src["url"] != "https://tamanhhospital.vn", (
            f"Homepage-only URL found on source {sid}"
        )


def test_source_metadata_consistency():
    sources_map = _load_sources_map()
    assert len(sources_map) == 77
    for sid, src in sources_map.items():
        assert src.get("source_title", "").strip(), f"{sid} missing source_title"
        assert src.get("organization", "").strip(), f"{sid} missing organization"
        assert src.get("source_tier") in {"TIER_1", "TIER_2", "TIER_3"}, f"{sid} invalid source_tier"
        assert src.get("url", "").startswith(("http://", "https://")), f"{sid} invalid URL"


def test_derived_manifest_values_match_medical_kb_manifest_programmatically():
    data = _load_explanations()
    derived_sha256 = corpus_sha256(EXPLANATIONS_PATH)
    derived_chunks = build_corpus_chunks(data)
    derived_source_count = sum(len(e.get("sources", [])) for e in data)
    derived_analyte_count = len(data)
    derived_chunk_count = len(derived_chunks)

    assert derived_source_count == 77
    assert derived_analyte_count == 35
    assert derived_chunk_count == 199

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["corpus_sha256"] == derived_sha256
    assert manifest["source_corpus_sha256"] == derived_sha256
    assert manifest["chunk_count"] == derived_chunk_count
    assert manifest["source_record_count"] == derived_source_count
    assert manifest["analyte_count"] == derived_analyte_count

    report = CorpusValidator.validate(data, mode="release")
    assert report.is_valid is True
    assert not report.errors


def test_runtime_provenance_representative_cases():
    repo = MedicalCitationRepository.from_default_file()

    # 1. Fasting plasma glucose (FPG)
    fpg_old_urls = [
        "https://www.vinmec.com/vie/bai-viet/chi-so-glucose-khi-doi-la-gi-vi",
        "https://nhathuoclongchau.com.vn/bai-viet/chi-so-glucose-khi-doi-la-gi-bao-nhieu-la-binh-thuong.html",
        "https://diabetesjournals.org/care/issue/49/Supplement_1",
    ]
    for old_url in fpg_old_urls:
        assert repo.resolve(analyte="Fasting plasma glucose", url=old_url) is None

    fpg_approved_urls = [
        "https://www.vinmec.com/vie/bai-viet/xet-nghiem-glucose-huyet-tuong-luc-doi-la-gi-vi",
        "https://nhathuoclongchau.com.vn/bai-viet/chi-so-duong-huyet-luc-sang-som-bao-nhieu-la-binh-thuong.html",
        "https://diabetesjournals.org/care/article/49/Supplement_1/S27/163926/2-Diagnosis-and-Classification-of-Diabetes",
    ]
    for new_url in fpg_approved_urls:
        citation = repo.resolve(analyte="Fasting plasma glucose", url=new_url)
        assert citation is not None
        assert citation.url == new_url

    # 2. HbA1c: SRC-CDC-A1C-MGMT absent, active CDC citation preserved
    assert repo.resolve(analyte="HbA1c", source_id="SRC-CDC-A1C-MGMT") is None
    assert repo.resolve(analyte="HbA1c", url="https://www.cdc.gov/diabetes/managing/managing-blood-sugar/a1c.html") is None
    cdc_active = repo.resolve(analyte="HbA1c", source_id="SRC-CDC-A1C")
    assert cdc_active is not None
    assert cdc_active.url == "https://www.cdc.gov/diabetes/diabetes-testing/prediabetes-a1c-test.html"

    # 3. Creatinine: SRC-TAMANH-CRE absent
    assert repo.resolve(analyte="Creatinine", source_id="SRC-TAMANH-CRE") is None
    assert repo.resolve(analyte="Creatinine", url="https://tamanhhospital.vn") is None
    uhnm_nhs = repo.resolve(analyte="Creatinine", source_id="SRC-UHNM-NHS-CREATININE")
    assert uhnm_nhs is not None
    assert uhnm_nhs.url == "https://www.uhnm.nhs.uk/our-services/pathology/tests/creatinine/"

    # 4. Lipids: NHLBI ATP III canonical replacement used consistently across Total cholesterol, Triglyceride, HDL-C
    nhlbi_canonical = "https://www.nhlbi.nih.gov/resources/third-report-expert-panel-detection-evaluation-and-treatment-high-blood-cholesterol-0"
    for lipid_analyte in ["Total cholesterol", "Triglyceride", "HDL-C"]:
        citation = repo.resolve(analyte=lipid_analyte, url=nhlbi_canonical)
        assert citation is not None
        assert citation.url == nhlbi_canonical
        assert "nhlbi.nih.gov/files/docs/guidelines/atp3full.pdf" not in citation.url

    # LDL-C: NLA canonical & CDC canonical
    nla_citation = repo.resolve(analyte="LDL-C", source_id="SRC-NLA-NCEP-2014")
    assert nla_citation is not None
    assert nla_citation.url == "https://www.lipid.org/resource/nla-recommendations-for-patient-centered-management-of-dyslipidemia/"

    cdc_ldl = repo.resolve(analyte="LDL-C", source_id="SRC-CDC-LDL")
    assert cdc_ldl is not None
    assert cdc_ldl.url == "https://www.cdc.gov/cholesterol/about/ldl-and-hdl-cholesterol-and-triglycerides.html"
