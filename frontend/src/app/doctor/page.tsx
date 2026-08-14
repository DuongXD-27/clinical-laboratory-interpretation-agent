"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import { mockScenarios } from "@/lib/mockData";
import { authFetch, clearSession, getRole, getToken, getUsername } from "@/lib/api";
import type { AnalysisResult } from "@/types/analysis";

export default function DoctorPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [selectedScenario, setSelectedScenario] = useState(mockScenarios[0].id);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "doctor") {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage is client-only.
    setUsername(getUsername());
    setCheckingAuth(false);
  }, [router]);

  function handleLogout() {
    clearSession();
    router.replace("/");
  }

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    const scenario = mockScenarios.find((s) => s.id === selectedScenario);
    if (!scenario) return;

    try {
      const response = await authFetch("/api/v1/analyze", {
        method: "POST",
        body: JSON.stringify(scenario.data),
      });

      if (response.status === 401) {
        clearSession();
        router.replace("/");
        return;
      }

      if (!response.ok) {
        throw new Error("Lỗi kết nối đến server");
      }

      const data = await response.json();
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đã xảy ra lỗi hệ thống");
    } finally {
      setLoading(false);
    }
  };

  if (checkingAuth) return null;

  return (
    <div className="min-h-screen bg-zinc-100 dark:bg-zinc-950 p-6 font-sans text-zinc-900 dark:text-zinc-100 transition-colors duration-300">
      <div className="max-w-6xl mx-auto space-y-6">
        
        {/* Header Dashboard */}
        <div className="bg-white dark:bg-zinc-900 p-6 rounded-xl shadow-sm border border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-zinc-800 dark:text-zinc-100">
              Phân Hệ Bác Sĩ (Doctor Portal)
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Phân tích lâm sàng hỗ trợ bởi AI — {username}
              <button
                type="button"
                onClick={handleLogout}
                className="ml-3 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
              >
                Đăng xuất
              </button>
            </p>
          </div>
          <div className="flex gap-3 w-full md:w-auto">
            <select
              className="flex-1 md:w-64 bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
            >
              {mockScenarios.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
            <button
              onClick={handleAnalyze}
              disabled={loading}
              className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center min-w-[120px]"
            >
              {loading ? "Đang xử lý..." : "Tải Dữ Liệu"}
            </button>
          </div>
        </div>

        <HistoryPanel
          mode="doctor"
          accent="indigo"
          onUnauthorized={() => {
            clearSession();
            router.replace("/");
          }}
        />

        <OcrReviewPanel
          accent="indigo"
          onResult={(data) => {
            setResult(data);
            setError(null);
          }}
          onUnauthorized={() => {
            clearSession();
            router.replace("/");
          }}
        />

        {error && (
          <div className="p-4 bg-red-50 text-red-600 rounded-xl border border-red-200 text-sm">
            {error}
          </div>
        )}

        {/* Dashboard Content */}
        {result && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            
            {/* Left Column: Patient Info & Notes */}
            <div className="lg:col-span-1 space-y-6">
              
              {/* Patient Profile Card */}
              <div className="bg-white dark:bg-zinc-900 p-6 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-sm">
                <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-4">Thông tin bệnh nhân</h2>
                <div className="space-y-3">
                  <div>
                    <div className="text-xs text-zinc-400">Họ và tên</div>
                    <div className="font-medium">{result.patient_info?.name || "N/A"}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-zinc-400">Tuổi</div>
                      <div className="font-medium">{result.patient_info?.age}</div>
                    </div>
                    <div>
                      <div className="text-xs text-zinc-400">Giới tính</div>
                      <div className="font-medium">{result.patient_info?.gender === 'M' ? 'Nam' : 'Nữ'}</div>
                    </div>
                  </div>
                </div>
              </div>

               {/* System Alerts */}
               {result.critical_alerts?.length > 0 && (
                <div className="bg-red-50 dark:bg-red-950/30 p-5 rounded-xl border border-red-200 dark:border-red-900 shadow-sm">
                  <h2 className="text-sm font-semibold text-red-600 dark:text-red-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                    Cảnh báo từ hệ thống
                  </h2>
                  <ul className="list-disc list-inside text-sm text-red-700 dark:text-red-300 space-y-1">
                    {result.critical_alerts?.map((alert, idx) => (
                      <li key={idx}>{alert.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Ghi chú lâm sàng KHÔNG nằm ở đây.
                  Màn này là phân tích thử trên dữ liệu mô phỏng và không sinh ra
                  phiếu nào (phân tích của bác sĩ không được lưu thành lịch sử
                  bệnh nhân), nên không có phiếu để gắn ghi chú vào. Ô nhập cũ ở
                  đây là giao diện suông: gõ vào rồi rời trang là mất, và nó tạo
                  ấn tượng sai rằng tính năng đã tồn tại.

                  Ghi chú thật nằm trong "Lịch sử xét nghiệm của bệnh nhân" bên
                  dưới: mở một phiếu cụ thể rồi ghi nhận xét vào đúng phiếu đó,
                  đúng Luồng 1 của nghiệp vụ. */}
              <div className="bg-white dark:bg-zinc-900 p-6 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-sm">
                <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-3">Ghi chú lâm sàng (HITL)</h2>
                <p className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                  Ghi chú được gắn vào một phiếu xét nghiệm cụ thể của bệnh nhân, không gắn vào
                  phân tích thử ở màn này. Mở phần <strong>Lịch sử xét nghiệm của bệnh nhân</strong>{" "}
                  bên dưới, chọn một phiếu, rồi ghi nhận xét vào đúng phiếu đó — bệnh nhân sở hữu
                  phiếu sẽ đọc được.
                </p>
              </div>

            </div>

            {/* Right Column: Data Grid */}
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden">
                <div className="p-5 border-b border-zinc-100 dark:border-zinc-800">
                  <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Chi tiết chỉ số xét nghiệm</h2>
                </div>
                
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-zinc-50 dark:bg-zinc-950/50 text-zinc-500 uppercase font-semibold text-xs border-b border-zinc-200 dark:border-zinc-800">
                      <tr>
                        <th className="px-6 py-4">Chỉ số</th>
                        <th className="px-6 py-4">Kết quả</th>
                        <th className="px-6 py-4">Khoảng TC</th>
                        <th className="px-6 py-4">Phân loại</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                      {result.indicators?.map((ind, idx) => {
                        let statusColor = "text-green-600 bg-green-50 dark:bg-green-900/20";
                        if (ind.is_critical) statusColor = "text-red-600 bg-red-50 dark:bg-red-900/20";
                        else if (ind.is_abnormal) statusColor = "text-orange-600 bg-orange-50 dark:bg-orange-900/20";

                        const refRange = (ind.reference_low ?? "-") + " - " + (ind.reference_high ?? "-");

                        return (
                          <tr key={idx} className="hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20 transition-colors">
                            <td className="px-6 py-4 font-medium">{ind.name}</td>
                            <td className="px-6 py-4">
                              <span className="font-bold">{ind.value}</span> <span className="text-zinc-500 text-xs">{ind.unit}</span>
                            </td>
                            <td className="px-6 py-4 text-zinc-500 text-xs">{refRange}</td>
                            <td className="px-6 py-4">
                              <span className={`px-2.5 py-1 rounded-md text-xs font-semibold uppercase tracking-wider ${statusColor}`}>
                                {ind.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* AI Analysis Breakdowns */}
              <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden">
                <div className="p-5 border-b border-zinc-100 dark:border-zinc-800">
                  <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Luận điểm của AI</h2>
                </div>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {result.indicators?.map((ind, idx) => (
                    ind.explanation ? (
                      <div key={idx} className="p-5">
                        <h3 className="font-medium text-sm text-indigo-600 dark:text-indigo-400 mb-2">{ind.name}</h3>
                        <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">{ind.explanation}</p>
                      </div>
                    ) : null
                  ))}
                </div>
              </div>

            </div>
          </div>
        )}
      </div>
    </div>
  );
}
