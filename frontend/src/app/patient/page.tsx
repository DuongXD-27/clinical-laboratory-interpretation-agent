"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import { authFetch, clearSession, getRole, getToken, getUsername } from "@/lib/api";
import { buildManualIndicators, MANUAL_ANALYTES } from "@/lib/manualEntry.mjs";
import type { AnalysisResult } from "@/types/analysis";

export default function PatientPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [isGuest, setIsGuest] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gate3Acknowledged, setGate3Acknowledged] = useState(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);

  const [inputMode, setInputMode] = useState<"manual" | "ocr">("manual");
  const [ocrPanelKey, setOcrPanelKey] = useState(0);
  const [manualMeta, setManualMeta] = useState({ age: "35", gender: "male", date: "" });
  const [manualValues, setManualValues] = useState<Record<string, string>>({});

  useEffect(() => {
    const role = getRole();
    // Khách dùng chung màn này với bệnh nhân (ma trận cho khách nhập chỉ số +
    // tải ảnh); phần lịch sử mới là chỗ phân biệt.
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
        throw new Error(detail ?? `Server trả về lỗi ${response.status}`);
      }

      const data: AnalysisResult = await response.json();
      setResult(data);
      // Phiếu chỉ được lưu khi backend trả về ID — khách thì không có, nên
      // không cần nạp lại danh sách lịch sử.
      if (data.saved_report_id) {
        setHistoryRefresh((current) => current + 1);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đã xảy ra lỗi hệ thống");
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

  const hasCritical = (result?.critical_alerts.length ?? 0) > 0;
  const showCriticalBanner = hasCritical && !gate3Acknowledged;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 p-6 font-sans text-zinc-900 dark:text-zinc-100 transition-colors duration-300">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Header */}
        <div className="bg-white dark:bg-zinc-900 p-6 rounded-2xl shadow-sm border border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              Phân Tích Sức Khỏe AI
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
              Trải nghiệm người bệnh (Patient View) — {isGuest ? "phiên khách" : username}
              <button
                type="button"
                onClick={handleLogout}
                className="ml-3 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                {isGuest ? "Thoát phiên khách" : "Đăng xuất"}
              </button>
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setResult(null);
              setError(null);
              if (inputMode === "manual") {
                setManualValues({});
              } else {
                setOcrPanelKey((current) => current + 1);
              }
            }}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-all shadow-md shadow-blue-500/20"
          >
            Đặt lại
          </button>
        </div>

        {isGuest && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
            Bạn đang dùng thử với tư cách khách. Kết quả phân tích{" "}
            <strong>không được lưu lại</strong> — thoát phiên là mất. Đăng ký tài khoản nếu muốn xem
            lại lịch sử xét nghiệm của mình về sau.
          </div>
        )}

        {/* Mode toggle */}
        <div className="flex gap-2">
          <button
            onClick={() => setInputMode("manual")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
              inputMode === "manual"
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 border-zinc-300 dark:border-zinc-700 hover:border-blue-400"
            }`}
          >
            Nhập tay
          </button>
          <button
            onClick={() => setInputMode("ocr")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
              inputMode === "ocr"
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 border-zinc-300 dark:border-zinc-700 hover:border-blue-400"
            }`}
          >
            Tải ảnh phiếu
          </button>
        </div>

        {inputMode === "manual" && (
          <section className="bg-white dark:bg-zinc-900 p-6 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm space-y-5">
            <div>
              <h2 className="font-semibold text-lg">Nhập kết quả xét nghiệm</h2>
              <p className="text-sm text-zinc-500 mt-1">
                Nhập một hoặc nhiều chỉ số. Hiện hệ thống có khoảng tham chiếu đã duyệt cho 4 chỉ số dưới đây và người từ 18–60 tuổi.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <label className="text-sm space-y-1">
                <span className="font-medium">Tuổi</span>
                <input
                  aria-label="Tuổi bệnh nhân"
                  type="number"
                  min="18"
                  max="60"
                  value={manualMeta.age}
                  onChange={(event) => setManualMeta((current) => ({ ...current, age: event.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
                />
              </label>
              <label className="text-sm space-y-1">
                <span className="font-medium">Giới tính</span>
                <select
                  aria-label="Giới tính bệnh nhân"
                  value={manualMeta.gender}
                  onChange={(event) => setManualMeta((current) => ({ ...current, gender: event.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
                >
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                </select>
              </label>
              <label className="text-sm space-y-1">
                <span className="font-medium">Ngày xét nghiệm</span>
                <input
                  aria-label="Ngày xét nghiệm"
                  type="date"
                  value={manualMeta.date}
                  onChange={(event) => setManualMeta((current) => ({ ...current, date: event.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {MANUAL_ANALYTES.map((analyte) => (
                <label key={analyte.name} className="grid grid-cols-[1fr_7rem_auto] items-center gap-2 border rounded-xl px-3 py-2 dark:border-zinc-700">
                  <span className="text-sm font-medium">{analyte.label}</span>
                  <input
                    aria-label={analyte.label}
                    type="number"
                    min="0"
                    step="any"
                    value={manualValues[analyte.name] ?? ""}
                    onChange={(event) => setManualValues((current) => ({
                      ...current,
                      [analyte.name]: event.target.value,
                    }))}
                    placeholder="Nhập số"
                    className="min-w-0 border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700"
                  />
                  <span className="text-xs text-zinc-500 min-w-14">{analyte.unit}</span>
                </label>
              ))}
            </div>

            <button
              type="button"
              onClick={handleManualAnalyze}
              disabled={loading}
              className="w-full px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold disabled:opacity-50"
            >
              {loading ? "Đang phân tích..." : "Phân tích các chỉ số đã nhập"}
            </button>
          </section>
        )}

        {inputMode === "ocr" && (
          <OcrReviewPanel
            key={ocrPanelKey}
            onResult={(data) => {
              setResult(data);
              setError(null);
              setGate3Acknowledged(false);
            }}
            onUnauthorized={() => {
              clearSession();
              router.replace("/");
            }}
          />
        )}

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl text-red-600 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Results Container */}
        {result && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">

            {result.saved_report_id ? (
              <p className="text-xs text-zinc-500">
                Đã lưu vào lịch sử của bạn (phiếu #{result.saved_report_id}).
              </p>
            ) : (
              isGuest && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Kết quả này không được lưu vì bạn đang ở phiên khách.
                </p>
              )
            )}

            {/* Critical Banner (Gate 3) */}
            {showCriticalBanner && (
              <div className="bg-red-600 text-white p-6 rounded-2xl shadow-lg shadow-red-600/20 flex flex-col md:flex-row items-center justify-between gap-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-10 opacity-10 pointer-events-none">
                  <svg className="w-32 h-32" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
                </div>
                <div className="flex items-start gap-4 z-10 w-full">
                  <div className="bg-white/20 p-2 rounded-full shrink-0">
                    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold mb-1">Cảnh Báo Sức Khỏe Nguy Kịch</h3>
                    <div className="text-red-50 text-sm space-y-1">
                      {result.critical_alerts?.map((alert, idx) => (
                        <p key={idx}>{alert.message}</p>
                      ))}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => setGate3Acknowledged(true)}
                  className="z-10 shrink-0 w-full md:w-auto px-6 py-3 bg-white text-red-600 font-semibold rounded-xl hover:bg-red-50 transition-colors shadow-sm"
                >
                  Tôi sẽ liên hệ bác sĩ
                </button>
              </div>
            )}

            {/* General Info */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white dark:bg-zinc-900 p-5 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm flex flex-col justify-center">
                <span className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Bệnh nhân</span>
                <span className="text-lg font-medium mt-1">{result.patient_info?.name || "N/A"}</span>
                <span className="text-sm text-zinc-600 dark:text-zinc-400">{result.patient_info?.age} tuổi • {result.patient_info?.gender === 'M' ? 'Nam' : 'Nữ'}</span>
              </div>
              <div className="bg-white dark:bg-zinc-900 p-5 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm flex flex-col justify-center md:col-span-2">
                <span className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Đánh giá chung</span>
                <span className="text-base text-zinc-700 dark:text-zinc-300 mt-2 leading-relaxed">
                  Hệ thống ghi nhận <strong className="text-zinc-900 dark:text-white">{result.indicators?.length || 0}</strong> chỉ số. 
                  Có <strong className={hasCritical ? 'text-red-500' : 'text-zinc-900 dark:text-white'}>{result.critical_alerts?.length || 0}</strong> cảnh báo nguy hiểm.
                </span>
              </div>
            </div>

            {/* Explanations Grid */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold px-1">Chi tiết kết quả</h2>
              <div className="grid grid-cols-1 gap-4">
                {result.indicators?.map((ind, idx) => {
                  const isCrit = ind.is_critical;
                  const isAbnormal = ind.is_abnormal;
                  
                  let badgeColor = "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800";
                  if (isCrit) {
                    badgeColor = "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800";
                  } else if (isAbnormal) {
                    badgeColor = "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 border-orange-200 dark:border-orange-800";
                  }

                  return (
                    <div key={idx} className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden hover:shadow-md transition-shadow">
                      <div className="p-5 border-b border-zinc-100 dark:border-zinc-800/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-2 h-10 rounded-full ${isCrit ? 'bg-red-500' : isAbnormal ? 'bg-orange-500' : 'bg-green-500'}`} />
                          <div>
                            <h3 className="font-semibold text-lg">{ind.name}</h3>
                            <div className="text-2xl font-bold tracking-tight mt-1">
                              {ind.value} <span className="text-sm font-normal text-zinc-500">{ind.unit}</span>
                            </div>
                          </div>
                        </div>
                        <div className={`px-3 py-1 rounded-full border text-xs font-semibold tracking-wide uppercase ${badgeColor}`}>
                          {ind.status}
                        </div>
                      </div>
                      
                      {ind.explanation && (
                        <div className="p-5 bg-zinc-50/50 dark:bg-zinc-900/50 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                          <p>{ind.explanation}</p>
                          {ind.sources && ind.sources.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700/50">
                              <span className="text-xs text-zinc-500 mr-2">Nguồn tham khảo:</span>
                              {ind.sources.map((src, sIdx) => (
                                <a key={sIdx} href={src} target="_blank" rel="noopener noreferrer" className="inline-block text-xs text-blue-600 dark:text-blue-400 hover:underline mr-3 break-all">
                                  [{sIdx + 1}] {new URL(src).hostname}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Disclaimer */}
            <div className="mt-8 p-4 bg-zinc-100 dark:bg-zinc-800/50 rounded-xl text-center text-xs text-zinc-500 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700/50">
              <p className="font-semibold mb-1">Tuyên bố miễn trừ trách nhiệm</p>
              <p>Kết quả phân tích này được tạo ra bởi AI nhằm mục đích tham khảo, KHÔNG thay thế cho chẩn đoán y khoa. Vui lòng luôn tham vấn bác sĩ chuyên môn.</p>
            </div>

          </div>
        )}

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
    </div>
  );
}
