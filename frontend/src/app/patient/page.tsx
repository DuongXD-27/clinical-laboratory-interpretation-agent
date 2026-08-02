"use client";

import { useState } from "react";
import { mockScenarios } from "@/lib/mockData";

export default function PatientPage() {
  const [selectedScenario, setSelectedScenario] = useState(mockScenarios[0].id);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [gate3Acknowledged, setGate3Acknowledged] = useState(false);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setGate3Acknowledged(false);

    const scenario = mockScenarios.find((s) => s.id === selectedScenario);
    if (!scenario) return;

    try {
      const response = await fetch("http://localhost:8000/api/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scenario.data),
      });

      if (!response.ok) {
        throw new Error("Lỗi kết nối đến server");
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Đã xảy ra lỗi hệ thống");
    } finally {
      setLoading(false);
    }
  };

  const hasCritical = result?.critical_alerts?.length > 0;
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
              Trải nghiệm người bệnh (Patient View)
            </p>
          </div>
          <div className="flex gap-3 w-full sm:w-auto">
            <select
              className="flex-1 sm:w-64 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
            >
              {mockScenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              onClick={handleAnalyze}
              disabled={loading}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-all shadow-md shadow-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 min-w-[120px]"
            >
              {loading ? (
                <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              ) : (
                "Phân Tích"
              )}
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl text-red-600 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Results Container */}
        {result && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            
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
                      {result.critical_alerts?.map((alert: any, idx: number) => (
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
                {result.indicators?.map((ind: any, idx: number) => {
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
                              {ind.sources.map((src: string, sIdx: number) => (
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
      </div>
    </div>
  );
}
