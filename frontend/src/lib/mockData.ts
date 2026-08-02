export const mockScenarios = [
  {
    id: "normal",
    label: "Phiếu 1: Bình thường",
    data: {
      patient_id: "PT-001",
      patient_name: "Nguyễn Văn A",
      patient_age: 35,
      patient_gender: "male",
      test_date: "2026-08-01",
      language: "vi",
      indicators: [
        { name: "Glucose", value: 5.2, unit: "mmol/L" },
        { name: "LDL-Cholesterol", value: 2.2, unit: "mmol/L" },
        { name: "Kali", value: 4.0, unit: "mmol/L" }
      ]
    }
  },
  {
    id: "abnormal",
    label: "Phiếu 2: Bất thường (LDL Cao)",
    data: {
      patient_id: "PT-002",
      patient_name: "Trần Thị B",
      patient_age: 45,
      patient_gender: "female",
      test_date: "2026-08-02",
      language: "vi",
      indicators: [
        { name: "Glucose", value: 5.5, unit: "mmol/L" },
        { name: "LDL-Cholesterol", value: 4.5, unit: "mmol/L" },
        { name: "Kali", value: 4.2, unit: "mmol/L" }
      ]
    }
  },
  {
    id: "critical",
    label: "Phiếu 3: Nguy kịch (Kali)",
    data: {
      patient_id: "PT-003",
      patient_name: "Lê Văn C",
      patient_age: 60,
      patient_gender: "male",
      test_date: "2026-08-03",
      language: "vi",
      indicators: [
        { name: "Glucose", value: 6.1, unit: "mmol/L" },
        { name: "LDL-Cholesterol", value: 3.5, unit: "mmol/L" },
        { name: "Kali", value: 7.2, unit: "mmol/L" }
      ]
    }
  }
];
