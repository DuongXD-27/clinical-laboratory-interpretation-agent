# Data Architecture & Reference Registry Guide

Tài liệu hướng dẫn bản đồ dữ liệu trong thư mục `data/` dành cho kỹ sư phát triển và maintainer hệ thống.

---

## 1. Data Flow & Build Lineage

```text
data/reference/source/adult_outpatient_laboratory_reference_map.csv  (Authoring Source)
                             +
data/reference/explanations.json                                     (Authoring & Supplemental)
                             ↓
              src/scripts/build_reference_config.py
                             ↓
    ┌────────────────────────┼────────────────────────┬────────────────────────┐
    ↓                        ↓                        ↓                        ↓
reference_ranges.json  reference_ranges.csv     quarantine.csv     reference_build_report.json
(Runtime Rules)        (Build Artifact)         (Governance)       (Audit Hash Report)
    ↓
ReferenceRepository.from_default_files()
(Enforces reference_checker_config.json & units_metric.csv)
```

* **Runtime Loader**: Backend (`ReferenceRepository`, `AnalyteCatalog`, `critical_detector_node`) chỉ đọc `reference_ranges.json`, `reference_checker_config.json`, `units_metric.csv`, `critical_thresholds.json`, `explanations.json`, `question_templates.json`, `templates.json`.
* Các file CSV xuất kèm và report phục vụ build verification, governance và CI test kiểm toán.

---

## 2. Reference Files Inventory

| File Path | Role | Runtime Reads? | Editable Manually? | Notes |
| :--- | :--- | :---: | :---: | :--- |
| `reference/source/adult_outpatient_laboratory_reference_map.csv` | `AUTHORING_SOURCE` | NO | **YES** | Nguồn tác quyền gốc trích dẫn Tạp chí Y học VN. Chứa 80 dòng tham chiếu. |
| `reference/reference_ranges.json` | `GENERATED_RUNTIME_DATA` | **YES** | **NO** | 80 rules tham chiếu đã compile chuẩn hóa. Sinh tự động bởi build script. |
| `reference/reference_ranges.csv` | `BUILD_ARTIFACT` | NO | **NO** | Bản xuất CSV song song của `reference_ranges.json` phục vụ diff/audit. |
| `reference/reference_checker_config.json` | `RUNTIME_CONFIG` | **YES** | **YES** | Whitelist 9 chỉ số approved, alias mapping và age scope bounds. |
| `reference/units_metric.csv` | `RUNTIME_SOURCE_OF_TRUTH` | **YES** | **YES** | Bảng đơn vị SI chuẩn hóa duy nhất (Unit Verification Gate). |
| `reference/critical_thresholds.json` | `RUNTIME_SOURCE_OF_TRUTH` | **YES** | **YES** | Bảng ngưỡng báo động đỏ panic values theo ARUP Revision 46. |
| `reference/explanations.json` | `CURATED_SOURCE_DATA` & `RUNTIME_SOURCE_OF_TRUTH` | **YES** | **YES** | Tri thức giải thích y khoa tiếng Việt cho `AnalyteCatalog` và KB vector store. |
| `reference/question_templates.json` | `RUNTIME_SOURCE_OF_TRUTH` | **YES** | **YES** | Bộ câu hỏi gợi ý bác sĩ tất định theo `(analyte, status)`. |
| `reference/templates.json` | `RUNTIME_CONFIG` | **YES** | **YES** | Văn bản mẫu fallback an toàn y tế và disclaimer. |
| `reference/quarantine.csv` | `QUARANTINE_DATA` | NO | **NO** | Bằng chứng kiểm toán các chỉ số bị loại khỏi outpatient RI (eGFR, MPV,...). |
| `reference/reference_build_report.json` | `AUDIT_REPORT` | NO | **NO** | Báo cáo hash SHA-256 đối chiếu toàn vẹn dữ liệu build. |

---

## 3. Directory Roles

```text
data/
├── README.md               # Tài liệu bản đồ dữ liệu này
├── app.db                  # Local SQLite database [Gitignored: *.db]
├── chroma/                 # ChromaDB vector store persistence [Gitignored: data/chroma/]
├── ocr_samples/            # Ảnh phiếu mẫu (normal, blur, lowlight, skew) cho demo & upload gate
├── mock/                   # Fixture mẫu cho development & testing
│   ├── templates/          # 7 JSON templates cho các panel xét nghiệm (CBC, Lipid, Renal...)
│   └── generated/          # Mock reports theo kịch bản (normal, abnormal, edge_case)
└── reference/              # Medical reference registry & configurations
    └── source/             # Human-curated medical literature & authoring inputs
```

---

## 4. Current Operational Analytes (9 Approved)

Hệ thống hiện tại hỗ trợ vận hành chính thức **9 chỉ số xét nghiệm**:

```text
1. WBC                     (Bạch cầu)
2. RBC                     (Hồng cầu)
3. HGB                     (Huyết sắc tố / Hemoglobin)
4. Fasting plasma glucose  (Đường huyết lúc đói)
5. HbA1c                   (Chỉ số đường huyết tích lũy)
6. LDL-C                   (Cholesterol xấu)
7. HDL-C                   (Cholesterol tốt)
8. Creatinine              (Chức năng thận)
9. Potassium               (Kali máu / K+)
```

> **QUY TẮC BẮT BUỘC**: Có dữ liệu reference trong repository không đồng nghĩa analyte đã operationally supported. Mọi analyte muốn chạy runtime phải nằm trong whitelist `approved_analytes` của `reference_checker_config.json`.

---

## 5. Medical Safety & Governance Warnings

1. **Không sửa trực tiếp `reference_ranges.json` / `reference_ranges.csv`**: File này là build artifact được sinh tự động. Muốn cập nhật khoảng tham chiếu, sửa `reference/source/adult_outpatient_laboratory_reference_map.csv` rồi chạy build command.
2. **Không xóa `quarantine.csv`**: Dù runtime không đọc trực tiếp, file này là bằng chứng Medical Governance giải thích lý do loại trừ các xét nghiệm đặc thù.
3. **Không tự ý đổi `critical_thresholds.json`**: Mọi ngưỡng cấp cứu phải có source provenance (ARUP / Bộ Y tế) và được kiểm toán an toàn.
4. **Không tự ý thêm analyte vào `approved_analytes`**: Thêm chỉ số mới đòi hỏi đồng bộ 4 lớp: reference rule, unit verification, explanation template, và doctor questions.
5. **Cấm map generic `Glucose` ➔ `Fasting plasma glucose`**: Kết quả đường huyết ngẫu nhiên không tương đương đường huyết lúc đói; map tự động sẽ gây nguy cơ sai lệch đánh giá y khoa.
6. **Phân biệt External Aliases vs Canonical Names**: OCR aliases (`K+`, `Creatinin`, `HDL-cho.`, `LDL-cho.`) chỉ dùng để phân giải text đầu vào. Toàn bộ logic nội bộ bắt buộc sử dụng tên canonical chuẩn.

---

## 6. Build Reference Command

Khi cập nhật file nguồn y khoa `adult_outpatient_laboratory_reference_map.csv` hoặc `explanations.json`, thực hiện lệnh sau để build lại reference data:

```bash
# Rebuild reference catalog
python -m src.scripts.build_reference_config

# Kiểm tra tính toàn vẹn và regression test
pytest tests/test_data/
```

* **INPUT**: `data/reference/source/adult_outpatient_laboratory_reference_map.csv` & `data/reference/explanations.json`
* **OUTPUTS**: `data/reference/reference_ranges.json`, `data/reference/reference_ranges.csv`, `data/reference/quarantine.csv`, `data/reference/reference_build_report.json`
