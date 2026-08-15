"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AnalysisResultView from "@/components/patient/AnalysisResultView";
import MetricInput from "@/components/MetricInput";
import MetricSelector, { type MetricDefinition } from "@/components/MetricSelector";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { buildManualIndicators, MANUAL_ANALYTES } from "@/lib/manualEntry.mjs";
import type { AnalysisResult } from "@/types/analysis";

function metricInputId(name: string) {
  return name.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

export default function PatientAnalysisPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [criticalAcknowledged, setCriticalAcknowledged] = useState(false);
  const [inputMode, setInputMode] = useState<"manual" | "ocr">("manual");
  const [ocrPanelKey, setOcrPanelKey] = useState(0);
  const [manualMeta, setManualMeta] = useState({ age: "35", gender: "male", date: "" });
  const [manualValues, setManualValues] = useState<Record<string, string>>({});
  const [selectedManualMetrics, setSelectedManualMetrics] = useState<string[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [isGuest, setIsGuest] = useState(false);

  useEffect(() => {
    const role = getRole();
    if (!getToken() || (role !== "patient" && role !== "guest")) {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage auth is available only after mount.
    setIsGuest(role === "guest");
    setCheckingAuth(false);
  }, [router]);

  function resetAnalysis() {
    setResult(null);
    setError(null);
    setCriticalAcknowledged(false);
    if (inputMode === "manual") {
      setManualValues({});
      setSelectedManualMetrics([]);
      setSelectorOpen(false);
    } else {
      setOcrPanelKey((current) => current + 1);
    }
  }

  function addManualMetric(metric: MetricDefinition) {
    setSelectedManualMetrics((current) => current.includes(metric.name) ? current : [...current, metric.name]);
  }

  function removeManualMetric(name: string) {
    setSelectedManualMetrics((current) => current.filter((item) => item !== name));
    setManualValues((current) => {
      const next = { ...current };
      delete next[name];
      return next;
    });
  }

  async function runAnalyze(body: unknown) {
    setLoading(true);
    setError(null);
    setResult(null);
    setCriticalAcknowledged(false);
    try {
      const response = await authFetch("/api/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 401) {
        clearSession();
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail = typeof payload?.detail === "string" ? payload.detail : null;
        throw new Error(response.status >= 500
          ? "Chưa thể phân tích kết quả lúc này. Vui lòng thử lại sau."
          : (detail ?? "Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại."));
      }
      setResult(await response.json() as AnalysisResult);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Đã xảy ra lỗi. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  async function handleManualAnalyze() {
    const age = Number(manualMeta.age);
    if (!Number.isInteger(age) || age < 18 || age > 60) {
      setError("Dữ liệu tham chiếu hiện hỗ trợ người từ 18 đến 60 tuổi.");
      return;
    }
    if (!manualMeta.date) {
      setError("Hãy chọn ngày xét nghiệm.");
      return;
    }
    try {
      const indicators = buildManualIndicators(manualValues);
      await runAnalyze({
        patient_age: age,
        patient_gender: manualMeta.gender,
        test_date: manualMeta.date,
        language: "vi",
        indicators,
      });
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Dữ liệu nhập tay không hợp lệ.");
    }
  }

  if (checkingAuth) {
    return <div className="loading-message" role="status">Đang mở khu vực phân tích...</div>;
  }

  const selectedMetrics = MANUAL_ANALYTES.filter((metric) => selectedManualMetrics.includes(metric.name));

  return (
    <div className="analysis-layout">
      {result ? (
        <AnalysisResultView
          result={result}
          criticalAcknowledged={criticalAcknowledged}
          onAcknowledgeCritical={() => setCriticalAcknowledged(true)}
          onNewAnalysis={resetAnalysis}
          sourceMode={inputMode}
          onUnauthorized={() => {
            clearSession();
            router.replace("/login");
          }}
        />
      ) : (
        <>
          <div className="page-section-heading">
            <div>
              <span className="eyebrow">Phân tích mới</span>
              <h2>Nhập kết quả xét nghiệm</h2>
              <p>Chọn cách nhập phù hợp, kiểm tra thông tin và bắt đầu phân tích.</p>
            </div>
            <button type="button" onClick={resetAnalysis} className="secondary-button">Xóa dữ liệu đang nhập</button>
          </div>

          {isGuest && (
            <div className="info-message" role="status">
              <p className="font-semibold text-slate-800">Bạn đang dùng thử với tư cách khách</p>
              <p className="mt-1">Kết quả phân tích không được lưu lại và sẽ mất khi bạn thoát phiên.</p>
            </div>
          )}

          <div className="input-workspace">
            <div className="mode-tabs" role="tablist" aria-label="Cách nhập kết quả xét nghiệm">
              <button
                type="button"
                role="tab"
                id="manual-tab"
                aria-selected={inputMode === "manual"}
                aria-controls="manual-panel"
                tabIndex={inputMode === "manual" ? 0 : -1}
                onClick={() => setInputMode("manual")}
                className={inputMode === "manual" ? "active" : ""}
              >
                Nhập tay
              </button>
              <button
                type="button"
                role="tab"
                id="ocr-tab"
                aria-selected={inputMode === "ocr"}
                aria-controls="upload-panel"
                tabIndex={inputMode === "ocr" ? 0 : -1}
                onClick={() => setInputMode("ocr")}
                className={inputMode === "ocr" ? "active" : ""}
              >
                Tải ảnh phiếu
              </button>
            </div>

            {inputMode === "manual" && (
              <section id="manual-panel" role="tabpanel" aria-labelledby="manual-tab" className="patient-card p-5 sm:p-7">
                <ol className="manual-flow" aria-label="Quy trình nhập tay">
                  <li className="active"><span>1</span> Nhập chỉ số</li>
                  <li><span>2</span> Thông tin chung</li>
                  <li><span>3</span> Phân tích kết quả</li>
                </ol>

                <div className="section-heading mt-7">
                  <span className="eyebrow">Bước 1</span>
                  <h2>Chỉ số xét nghiệm</h2>
                  <p>Chỉ thêm những chỉ số có trên phiếu của bạn. Số lượng chỉ số không bị giới hạn cố định.</p>
                </div>

                <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm text-slate-500">Đã chọn {selectedMetrics.length} chỉ số</p>
                  <button type="button" onClick={() => setSelectorOpen(true)} className="secondary-button w-full sm:w-auto">
                    <span aria-hidden="true">+</span> Thêm chỉ số
                  </button>
                </div>

                {selectedMetrics.length === 0 ? (
                  <div className="empty-metrics mt-5">
                    <div className="empty-metrics-icon" aria-hidden="true">+</div>
                    <p className="font-medium text-slate-700">Bạn chưa thêm chỉ số xét nghiệm.</p>
                    <button type="button" onClick={() => setSelectorOpen(true)} className="text-button mt-2">Thêm chỉ số đầu tiên</button>
                  </div>
                ) : (
                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    {selectedMetrics.map((metric) => (
                      <MetricInput
                        key={metric.name}
                        id={`manual-${metricInputId(metric.name)}`}
                        name={metric.name}
                        label={metric.label}
                        unit={metric.unit}
                        value={manualValues[metric.name] ?? ""}
                        onValueChange={(value) => setManualValues((current) => ({ ...current, [metric.name]: value }))}
                        onRemove={() => removeManualMetric(metric.name)}
                      />
                    ))}
                  </div>
                )}

                <div className="manual-meta-section">
                  <div className="section-heading">
                    <span className="eyebrow">Bước 2</span>
                    <h2>Thông tin chung</h2>
                    <p>Thông tin này được gửi theo đúng payload hiện tại để đối chiếu khoảng tham chiếu.</p>
                  </div>
                  <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <label className="field-label" htmlFor="manual-age">Tuổi
                      <input id="manual-age" type="number" min="18" max="60" value={manualMeta.age} onChange={(event) => setManualMeta((current) => ({ ...current, age: event.target.value }))} className="form-control mt-2" />
                    </label>
                    <label className="field-label" htmlFor="manual-gender">Giới tính
                      <select id="manual-gender" value={manualMeta.gender} onChange={(event) => setManualMeta((current) => ({ ...current, gender: event.target.value }))} className="form-control mt-2">
                        <option value="male">Nam</option>
                        <option value="female">Nữ</option>
                      </select>
                    </label>
                    <label className="field-label" htmlFor="manual-date">Ngày xét nghiệm
                      <input id="manual-date" type="date" value={manualMeta.date} onChange={(event) => setManualMeta((current) => ({ ...current, date: event.target.value }))} className="form-control mt-2" />
                    </label>
                  </div>
                </div>

                {error && <div role="alert" className="error-message">{error}</div>}
                <button type="button" onClick={handleManualAnalyze} disabled={loading} className="primary-button mt-6 w-full">
                  {loading ? "Đang phân tích kết quả..." : "Phân tích kết quả"}
                </button>
              </section>
            )}

            {inputMode === "ocr" && (
              <div id="upload-panel" role="tabpanel" aria-labelledby="ocr-tab">
                <OcrReviewPanel
                  key={ocrPanelKey}
                  onResult={(data) => {
                    setResult(data);
                    setError(null);
                    setCriticalAcknowledged(false);
                  }}
                  onUnauthorized={() => {
                    clearSession();
                    router.replace("/login");
                  }}
                />
              </div>
            )}
          </div>
        </>
      )}

      <MetricSelector
        open={selectorOpen}
        catalog={MANUAL_ANALYTES}
        selectedNames={selectedManualMetrics}
        onAdd={addManualMetric}
        onClose={() => setSelectorOpen(false)}
      />
    </div>
  );
}
