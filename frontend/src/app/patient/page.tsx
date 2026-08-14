"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import MetricInput from "@/components/MetricInput";
import MetricSelector, { type MetricDefinition } from "@/components/MetricSelector";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import { authFetch, clearSession, getRole, getToken, getUsername } from "@/lib/api";
import { buildManualIndicators, MANUAL_ANALYTES } from "@/lib/manualEntry.mjs";
import type { AnalysisResult } from "@/types/analysis";

function sourceHostname(source: string) {
  try {
    return new URL(source).hostname;
  } catch {
    return source;
  }
}

function metricInputId(name: string) {
  return name.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

export default function PatientPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gate3Acknowledged, setGate3Acknowledged] = useState(false);
  const [inputMode, setInputMode] = useState<"manual" | "ocr">("manual");
  const [ocrPanelKey, setOcrPanelKey] = useState(0);
  const [manualMeta, setManualMeta] = useState({ age: "35", gender: "male", date: "" });
  const [manualValues, setManualValues] = useState<Record<string, string>>({});
  const [selectedManualMetrics, setSelectedManualMetrics] = useState<string[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [isGuest, setIsGuest] = useState(false);
  // Tăng sau mỗi lần lưu phiếu để panel lịch sử nạp lại, không phải bấm Lọc.
  const [historyRefresh, setHistoryRefresh] = useState(0);

  useEffect(() => {
    const role = getRole();
    // Khách dùng chung màn này với bệnh nhân (ma trận cho khách nhập chỉ số và
    // tải ảnh); phần lịch sử mới là chỗ phân biệt. Nếu chỉ cho `patient` vào
    // đây thì nút "Dùng thử với tư cách khách" ở trang đăng nhập thành vòng lặp
    // chết: mở phiên khách rồi bị đá ngay về `/`.
    if (!getToken() || (role !== "patient" && role !== "guest")) {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage is client-only.
    setUsername(getUsername());
    setIsGuest(role === "guest");
    setCheckingAuth(false);
  }, [router]);

  function handleLogout() {
    clearSession();
    router.replace("/");
  }

  function handleReset() {
    setResult(null);
    setError(null);
    setGate3Acknowledged(false);
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

  const runAnalyze = async (body: unknown) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setGate3Acknowledged(false);
    try {
      const response = await authFetch("/api/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (response.status === 401) {
        clearSession();
        router.replace("/");
        return;
      }

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail = typeof payload?.detail === "string" ? payload.detail : null;
        throw new Error(response.status >= 500
          ? "Chưa thể phân tích kết quả lúc này. Vui lòng thử lại sau."
          : (detail ?? "Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại."));
      }
      const analysed: AnalysisResult = await response.json();
      setResult(analysed);
      if (analysed.saved_report_id) setHistoryRefresh((current) => current + 1);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Đã xảy ra lỗi. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  const handleManualAnalyze = async () => {
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
  };

  if (checkingAuth) return null;

  const selectedMetrics = MANUAL_ANALYTES.filter((metric) => selectedManualMetrics.includes(metric.name));
  const hasCritical = (result?.critical_alerts.length ?? 0) > 0;
  const showCriticalBanner = hasCritical && !gate3Acknowledged;

  return (
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div className="flex min-w-0 items-center gap-3.5">
            <div className="brand-mark" aria-hidden="true">+</div>
            <div className="min-w-0">
              <h1>Phân Tích Sức Khỏe AI</h1>
              <p className="truncate">
                Xin chào,{" "}
                <span className="font-medium text-slate-700">
                  {isGuest ? "bạn đang dùng thử (phiên khách)" : username}
                </span>
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" onClick={handleReset} className="secondary-button px-3 py-2.5 sm:px-4">
              Đặt lại
            </button>
            <button type="button" onClick={handleLogout} className="text-button px-2 py-2.5 sm:px-3">
              {isGuest ? "Thoát phiên khách" : "Đăng xuất"}
            </button>
          </div>
        </header>

        {isGuest && (
          <div className="info-message" role="status">
            <p className="font-semibold text-slate-800">Bạn đang dùng thử với tư cách khách</p>
            <p className="mt-1">
              Kết quả phân tích <strong>không được lưu lại</strong> — thoát phiên là mất. Đăng ký
              tài khoản nếu muốn xem lại lịch sử xét nghiệm của mình về sau.
            </p>
          </div>
        )}

        <div className="intro-copy">
          <span className="eyebrow">Kết quả xét nghiệm của bạn</span>
          <h2>Hiểu rõ hơn các chỉ số sức khỏe</h2>
          <p>Nhập kết quả hoặc tải ảnh phiếu xét nghiệm để nhận phần giải thích dễ hiểu.</p>
        </div>

        <div className="mode-tabs" role="tablist" aria-label="Cách nhập kết quả xét nghiệm">
          <button
            type="button"
            role="tab"
            aria-selected={inputMode === "manual"}
            aria-controls="manual-panel"
            onClick={() => setInputMode("manual")}
            className={inputMode === "manual" ? "active" : ""}
          >
            Nhập tay
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={inputMode === "ocr"}
            aria-controls="upload-panel"
            onClick={() => setInputMode("ocr")}
            className={inputMode === "ocr" ? "active" : ""}
          >
            Tải ảnh phiếu
          </button>
        </div>

        {inputMode === "manual" && (
          <section id="manual-panel" role="tabpanel" className="patient-card p-5 sm:p-7" aria-labelledby="manual-title">
            <div className="section-heading">
              <span className="eyebrow">Nhập kết quả</span>
              <h2 id="manual-title">Thông tin xét nghiệm</h2>
              <p>Điền thông tin chung, sau đó chỉ thêm những chỉ số bạn muốn phân tích.</p>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <label className="field-label" htmlFor="manual-age">
                Tuổi
                <input
                  id="manual-age"
                  type="number"
                  min="18"
                  max="60"
                  value={manualMeta.age}
                  onChange={(event) => setManualMeta((current) => ({ ...current, age: event.target.value }))}
                  className="form-control mt-2"
                />
              </label>
              <label className="field-label" htmlFor="manual-gender">
                Giới tính
                <select
                  id="manual-gender"
                  value={manualMeta.gender}
                  onChange={(event) => setManualMeta((current) => ({ ...current, gender: event.target.value }))}
                  className="form-control mt-2"
                >
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                </select>
              </label>
              <label className="field-label" htmlFor="manual-date">
                Ngày xét nghiệm
                <input
                  id="manual-date"
                  type="date"
                  value={manualMeta.date}
                  onChange={(event) => setManualMeta((current) => ({ ...current, date: event.target.value }))}
                  className="form-control mt-2"
                />
              </label>
            </div>

            <div className="mt-8 border-t border-slate-100 pt-7">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-semibold text-slate-950">Chỉ số xét nghiệm</h3>
                  <p className="mt-1 text-sm text-slate-500">Chọn các chỉ số có trên phiếu của bạn.</p>
                </div>
                <button type="button" onClick={() => setSelectorOpen(true)} className="secondary-button w-full sm:w-auto">
                  <span aria-hidden="true">+</span> Thêm chỉ số
                </button>
              </div>

              {selectedMetrics.length === 0 ? (
                <div className="empty-metrics mt-5">
                  <div className="empty-metrics-icon" aria-hidden="true">+</div>
                  <p className="font-medium text-slate-700">Bạn chưa thêm chỉ số xét nghiệm.</p>
                  <button type="button" onClick={() => setSelectorOpen(true)} className="text-button mt-2">
                    Thêm chỉ số đầu tiên
                  </button>
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
            </div>

            <button type="button" onClick={handleManualAnalyze} disabled={loading} className="primary-button mt-6 w-full">
              {loading ? "Đang phân tích kết quả..." : "Phân tích kết quả"}
            </button>
          </section>
        )}

        {inputMode === "ocr" && (
          <div id="upload-panel" role="tabpanel">
            <OcrReviewPanel
              key={ocrPanelKey}
              onResult={(data) => {
                setResult(data);
                setError(null);
                setGate3Acknowledged(false);
                if (data.saved_report_id) setHistoryRefresh((current) => current + 1);
              }}
              onUnauthorized={() => {
                clearSession();
                router.replace("/");
              }}
            />
          </div>
        )}

        {error && <div role="alert" className="error-message">{error}</div>}

        {result && (
          <section className="results-section" aria-labelledby="result-title">
            {showCriticalBanner && (
              <div className="critical-banner" role="alert">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-red-100">Cần chú ý ngay</p>
                  <h2 className="mt-1 text-xl font-bold">Cảnh báo sức khỏe nghiêm trọng</h2>
                  <div className="mt-2 space-y-1 text-sm leading-6 text-red-50">
                    {result.critical_alerts.map((alert, index) => <p key={index}>{alert.message}</p>)}
                  </div>
                </div>
                <button type="button" onClick={() => setGate3Acknowledged(true)} className="critical-button">
                  Tôi sẽ liên hệ bác sĩ
                </button>
              </div>
            )}

            <div className="patient-card p-5 sm:p-7">
              <div className="section-heading">
                <span className="eyebrow">Kết quả phân tích</span>
                <h2 id="result-title">Chi tiết các chỉ số</h2>
                <p>Hệ thống đã phân tích {result.indicators?.length ?? 0} chỉ số trong phiếu xét nghiệm.</p>
              </div>

              {result.summary && <div className="summary-box mt-5">{result.summary}</div>}

              {(result.out_of_scope_indicators?.length ?? 0) > 0 && (
                <div className="info-message mt-5" role="status">
                  <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
                  <p className="mt-1">
                    {result.out_of_scope_indicators?.join(", ")} hiện tại chưa được hỗ trợ, nên chưa được đưa vào phần phân tích.
                  </p>
                </div>
              )}

              <div className="mt-5 grid gap-3">
                {result.indicators?.map((indicator, index) => {
                  const tone = indicator.is_critical ? "critical" : indicator.is_abnormal ? "abnormal" : "normal";
                  return (
                    <article key={`${indicator.name}-${index}`} className={`result-card result-card-${tone}`}>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <h3 className="font-semibold text-slate-950">{indicator.name}</h3>
                          <p className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
                            {indicator.value} <span className="text-sm font-medium text-slate-500">{indicator.unit}</span>
                          </p>
                        </div>
                        <span className={`status-badge status-${tone}`}>{indicator.status}</span>
                      </div>
                      {indicator.explanation && <p className="mt-4 text-sm leading-6 text-slate-600">{indicator.explanation}</p>}
                      {indicator.sources && indicator.sources.length > 0 && (
                        <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                          <span className="mr-2">Nguồn tham khảo:</span>
                          {indicator.sources.map((source, sourceIndex) => (
                            <a key={sourceIndex} href={source} target="_blank" rel="noopener noreferrer" className="mr-3 text-blue-700 hover:underline">
                              [{sourceIndex + 1}] {sourceHostname(source)}
                            </a>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>

              <div className="disclaimer-box mt-6">
                <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
                <p className="mt-1">{result.disclaimer ?? "Kết quả do AI tạo ra chỉ nhằm mục đích tham khảo, không thay thế chẩn đoán y khoa. Vui lòng tham vấn bác sĩ chuyên môn."}</p>
              </div>
            </div>

            {/* Màn 6 — câu hỏi gợi ý, đứng sau màn kết quả.
                Chỉ hiện khi cảnh báo nguy kịch đã được xác nhận (Gate 3): danh
                sách câu hỏi phục vụ một cuộc hẹn khám trong tương lai, còn cảnh
                báo nguy kịch yêu cầu hành động ngay, nên không được đặt ở vị trí
                làm loãng cảnh báo. */}
            {!showCriticalBanner && (
              <QuestionsForDoctorPanel
                questions={result.questions_for_doctor ?? []}
                reportId={result.saved_report_id ?? null}
                onUnauthorized={() => {
                  clearSession();
                  router.replace("/");
                }}
              />
            )}
          </section>
        )}

        {/* Khách không thấy mục này vì `/history` trả 403 cho khách ở backend,
            không phải vì giao diện giấu đi. */}
        {!isGuest && (
          <HistoryPanel
            mode="patient"
            refreshToken={historyRefresh}
            onUnauthorized={() => {
              clearSession();
              router.replace("/");
            }}
          />
        )}
      </div>

      <MetricSelector
        open={selectorOpen}
        catalog={MANUAL_ANALYTES}
        selectedNames={selectedManualMetrics}
        onAdd={addManualMetric}
        onClose={() => setSelectorOpen(false)}
      />
    </main>
  );
}
