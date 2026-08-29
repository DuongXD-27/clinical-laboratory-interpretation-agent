"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AnalysisResultView from "@/components/patient/AnalysisResultView";
import MetricInput from "@/components/MetricInput";
import MetricSelector, { type MetricDefinition } from "@/components/MetricSelector";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { buildManualIndicators, MANUAL_ANALYTES, manualAnalyteAttentionMessage } from "@/lib/manualEntry.mjs";
import type { AnalysisResult } from "@/types/analysis";
import { cn } from "@/lib/utils";
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import LocalizedDateInput from "@/components/common/LocalizedDateInput";

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
    if (new URLSearchParams(window.location.search).get("mode") === "ocr") {
      setInputMode("ocr");
    }
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
    <div className="patient-page-layout">
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
          <PatientPageHeader
            eyebrow="Phân tích xét nghiệm"
            title="Nhập kết quả xét nghiệm"
            description="Tải phiếu xét nghiệm hoặc nhập các chỉ số để hệ thống giải thích kết quả."
          />

          {isGuest && (
            <div className="p-4 rounded-xl bg-[var(--surface-subtle)] border border-[var(--border)] text-sm" role="status">
              <p className="font-semibold text-foreground">Bạn đang dùng thử với tư cách khách</p>
              <p className="mt-1 text-muted-foreground">Kết quả phân tích không được lưu lại và sẽ mất khi bạn thoát phiên.</p>
            </div>
          )}

          <div className="space-y-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-2" aria-label="Cách nhập kết quả xét nghiệm" role="group">
                <button
                  type="button"
                  aria-pressed={inputMode === "manual"}
                  onClick={() => setInputMode("manual")}
                  className={cn(
                    "inline-flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    inputMode === "manual"
                      ? "bg-[var(--glass-surface)] backdrop-blur-xl shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_2px_10px_rgba(0,0,0,0.05)] border border-[var(--holo-cyan)]/20 text-foreground"
                      : "bg-[var(--surface)] border border-[var(--border)] text-muted-foreground hover:bg-[var(--surface-subtle)] hover:text-foreground"
                  )}
                >
                  Nhập tay
                </button>
                <button
                  type="button"
                  aria-pressed={inputMode === "ocr"}
                  onClick={() => setInputMode("ocr")}
                  className={cn(
                    "inline-flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    inputMode === "ocr"
                      ? "bg-[var(--glass-surface)] backdrop-blur-xl shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_2px_10px_rgba(0,0,0,0.05)] border border-[var(--holo-cyan)]/20 text-foreground"
                      : "bg-[var(--surface)] border border-[var(--border)] text-muted-foreground hover:bg-[var(--surface-subtle)] hover:text-foreground"
                  )}
                >
                  Tải ảnh phiếu
                </button>
              </div>
              
              <button type="button" onClick={resetAnalysis} className="px-4 py-2 text-sm font-medium text-destructive/90 bg-transparent hover:text-destructive hover:bg-destructive/5 transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-destructive/30 rounded-xl outline-none">
                Xóa dữ liệu đang nhập
              </button>
            </div>

            {inputMode === "manual" && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex items-center text-sm font-medium whitespace-nowrap overflow-x-auto pb-2 sm:pb-0 select-none" aria-label="Quy trình nhập tay">
                  <div className="flex items-center gap-2 text-foreground">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-[var(--surface)] border border-[var(--border)] text-xs font-semibold shadow-sm">1</span>
                    <span>Nhập kết quả</span>
                  </div>
                  <div className="w-8 sm:w-12 h-px bg-[var(--border)]/60 mx-3 sm:mx-4" />
                  <div className="flex items-center gap-2 text-muted-foreground/70">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full border border-[var(--border)]/50 text-xs font-semibold">2</span>
                    <span>Phân tích</span>
                  </div>
                  <div className="w-8 sm:w-12 h-px bg-[var(--border)]/60 mx-3 sm:mx-4" />
                  <div className="flex items-center gap-2 text-muted-foreground/70">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full border border-[var(--border)]/50 text-xs font-semibold">3</span>
                    <span>Kết quả</span>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-bold text-foreground">Chỉ số xét nghiệm</h2>
                      <p className="text-sm text-muted-foreground mt-1 max-w-xl">
                        Chỉ thêm những chỉ số có trên phiếu của bạn. Số lượng chỉ số không bị giới hạn cố định.
                      </p>
                    </div>
                    <div className="flex flex-col sm:items-end gap-2 shrink-0">
                      <button type="button" onClick={() => setSelectorOpen(true)} className="px-4 py-2 text-sm font-medium bg-[var(--surface)] border border-[var(--border)] rounded-xl hover:bg-[var(--surface-subtle)] transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 flex items-center gap-2 justify-center w-full sm:w-auto">
                        <span aria-hidden="true">+</span> Thêm chỉ số
                      </button>
                      <p className="text-xs font-medium text-muted-foreground">Đã chọn {selectedMetrics.length} chỉ số</p>
                    </div>
                  </div>

                  {selectedMetrics.length === 0 ? (
                    <div className="flex flex-col items-center justify-center p-8 sm:p-10 bg-[var(--surface-subtle)] border border-[var(--border)]/60 border-dashed rounded-[1.25rem] text-center shadow-[inset_0_2px_10px_rgba(0,0,0,0.01)]">
                      <div className="w-12 h-12 flex items-center justify-center rounded-full bg-background border border-[var(--border)] text-[var(--brand)] text-xl shadow-sm mb-4 transition-transform hover:scale-105 duration-200 motion-reduce:transition-none motion-reduce:hover:scale-100" aria-hidden="true">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                      </div>
                      <p className="text-base font-semibold text-foreground">Chưa có chỉ số xét nghiệm</p>
                      <p className="text-sm text-muted-foreground mt-1 mb-4">Hãy thêm các chỉ số có trên phiếu kết quả của bạn.</p>
                      <button type="button" onClick={() => setSelectorOpen(true)} className="text-sm font-medium text-[var(--brand)] hover:text-[var(--brand-strong)] hover:underline focus-visible:ring-2 focus-visible:ring-ring rounded outline-none transition-colors duration-200">
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
                        attentionMessage={manualAnalyteAttentionMessage(metric)}
                      />
                    ))}
                  </div>
                )}

                <div className="space-y-6 pt-4 border-t border-[var(--border)]/50">
                  <div>
                    <h2 className="text-lg font-bold text-foreground">Thông tin chung</h2>
                    <p className="text-sm text-muted-foreground mt-1">Thông tin này được dùng để đối chiếu khoảng tham chiếu.</p>
                  </div>
                  
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 bg-[var(--surface-subtle)] p-5 sm:p-6 rounded-2xl border border-[var(--border)]">
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-age">Tuổi
                      <input id="manual-age" type="number" min="18" max="60" value={manualMeta.age} onChange={(event) => setManualMeta((current) => ({ ...current, age: event.target.value }))} className="mt-2 w-full px-3 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--brand-soft)] transition-shadow text-foreground" />
                    </label>
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-gender">Giới tính
                      <select id="manual-gender" value={manualMeta.gender} onChange={(event) => setManualMeta((current) => ({ ...current, gender: event.target.value }))} className="mt-2 w-full px-3 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--brand-soft)] transition-shadow text-foreground">
                        <option value="male">Nam</option>
                        <option value="female">Nữ</option>
                      </select>
                    </label>
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-date">Ngày xét nghiệm
                      <LocalizedDateInput id="manual-date" ariaLabel="Ngày xét nghiệm" value={manualMeta.date} onChange={(event) => setManualMeta((current) => ({ ...current, date: event.target.value }))} className="mt-2 w-full px-3 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--brand-soft)] transition-shadow" />
                    </label>
                  </div>
                </div>

                {error && <div role="alert" className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm font-medium">{error}</div>}
                
                <div className="pt-2">
                  <button type="button" onClick={handleManualAnalyze} disabled={loading} className="w-full sm:w-auto px-8 py-3.5 bg-[var(--brand)] text-primary-foreground text-sm font-semibold rounded-xl hover:bg-[var(--brand-strong)] transition-all focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none shadow-sm shadow-[var(--brand-soft)] hover:shadow-md hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
                    {loading ? "Đang phân tích kết quả..." : "Phân tích kết quả"}
                  </button>
                </div>
              </div>
            </div>
          )}

            {inputMode === "ocr" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
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
