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
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import LocalizedDateInput from "@/components/common/LocalizedDateInput";
import SegmentedControl from "@/components/common/SegmentedControl";
import { SystemState } from "@/components/common/SystemState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

const INPUT_MODES = [
  { value: "manual", label: "Nhập tay", controls: "manual-analysis-panel" },
  { value: "ocr", label: "Tải ảnh phiếu", controls: "ocr-analysis-panel" },
] as const;

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
    return <SystemState kind="loading" title="Đang mở khu vực phân tích…" compact />;
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

          <div className="analysis-workspace">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <SegmentedControl
                value={inputMode}
                options={INPUT_MODES}
                onValueChange={setInputMode}
                ariaLabel="Cách nhập kết quả xét nghiệm"
                semantics="tabs"
                className="analysis-mode-control"
              />
              
              <Button type="button" variant="ghost" onClick={resetAnalysis} className="text-[var(--status-critical-fg)]">
                Xóa dữ liệu đang nhập
              </Button>
            </div>

            {inputMode === "manual" && (
              <div id="manual-analysis-panel" role="tabpanel" className="analysis-panel motion-tab-pane motion-tab-pane--clinical">
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
                      <Button type="button" variant="outline" onClick={() => setSelectorOpen(true)} className="w-full sm:w-auto">
                        <span aria-hidden="true">+</span> Thêm chỉ số
                      </Button>
                      <p className="text-xs font-medium text-muted-foreground">Đã chọn {selectedMetrics.length} chỉ số</p>
                    </div>
                  </div>

                  {selectedMetrics.length === 0 ? (
                    <SystemState
                      kind="empty"
                      title="Chưa có chỉ số xét nghiệm"
                      description="Hãy thêm các chỉ số có trên phiếu kết quả của bạn."
                      className="analysis-empty-state"
                      action={<Button type="button" variant="outline" onClick={() => setSelectorOpen(true)}>Thêm chỉ số đầu tiên</Button>}
                    />
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
                  
                  <div className="analysis-meta-grid">
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-age">Tuổi
                      <Input id="manual-age" type="number" min="18" max="60" value={manualMeta.age} onChange={(event) => setManualMeta((current) => ({ ...current, age: event.target.value }))} className="mt-2" />
                    </label>
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-gender">Giới tính
                      <NativeSelect className="mt-2 w-full" id="manual-gender" value={manualMeta.gender} onChange={(event) => setManualMeta((current) => ({ ...current, gender: event.target.value }))}>
                        <NativeSelectOption value="male">Nam</NativeSelectOption>
                        <NativeSelectOption value="female">Nữ</NativeSelectOption>
                      </NativeSelect>
                    </label>
                    <label className="flex flex-col text-sm font-medium text-foreground" htmlFor="manual-date">Ngày xét nghiệm
                      <LocalizedDateInput id="manual-date" ariaLabel="Ngày xét nghiệm" value={manualMeta.date} onChange={(event) => setManualMeta((current) => ({ ...current, date: event.target.value }))} className="mt-2 w-full px-3 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--brand-soft)] transition-shadow" />
                    </label>
                  </div>
                </div>

                {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
                
                <div className="pt-2">
                  <Button type="button" size="lg" onClick={handleManualAnalyze} disabled={loading} className="w-full sm:w-auto">
                    {loading ? "Đang phân tích kết quả…" : "Phân tích kết quả"}
                  </Button>
                </div>
              </div>
            </div>
          )}

            {inputMode === "ocr" && (
              <div id="ocr-analysis-panel" role="tabpanel" className="motion-tab-pane motion-tab-pane--clinical">
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
