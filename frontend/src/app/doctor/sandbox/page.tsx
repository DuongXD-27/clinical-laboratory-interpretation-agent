"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import OcrReviewPanel from "@/components/OcrReviewPanel";
import SeverityBadge from "@/components/common/SeverityBadge";
import { mockScenarios } from "@/lib/mockData";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import type { AnalysisResult } from "@/types/analysis";

export default function DoctorSandboxPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [selectedScenario, setSelectedScenario] = useState(mockScenarios[0].id);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "doctor") {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage session values are client-only.
    setCheckingAuth(false);
  }, [router]);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    const scenario = mockScenarios.find((item) => item.id === selectedScenario);
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

      if (!response.ok) throw new Error("Lỗi kết nối đến server");
      setResult(await response.json());
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Đã xảy ra lỗi hệ thống");
    } finally {
      setLoading(false);
    }
  };

  if (checkingAuth) return null;

  return (
    <div className="bg-zinc-100 dark:bg-zinc-950 font-sans text-zinc-900 dark:text-zinc-100 transition-colors duration-300 -m-4 lg:-m-6 p-4 lg:p-6 min-h-full">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="bg-white dark:bg-zinc-900 p-6 rounded-xl shadow-sm border border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-zinc-800 dark:text-zinc-100">
              Môi trường kiểm thử
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Phân tích mock và OCR sandbox
            </p>
          </div>
          <div className="flex gap-3 w-full md:w-auto">
            <select
              className="flex-1 md:w-64 bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
              value={selectedScenario}
              onChange={(event) => setSelectedScenario(event.target.value)}
            >
              {mockScenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>{scenario.label}</option>
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

        {result && (
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
                  {result.indicators?.map((indicator, index) => {
                    const level = indicator.is_critical ? "critical" : indicator.is_abnormal ? "abnormal" : "normal";
                    return (
                      <tr key={`${indicator.name}-${index}`} className="hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20 transition-colors">
                        <td className="px-6 py-4 font-medium">{indicator.name}</td>
                        <td className="px-6 py-4">
                          <span className="font-bold">{indicator.value}</span> <span className="text-zinc-500 text-xs">{indicator.unit}</span>
                        </td>
                        <td className="px-6 py-4 text-zinc-500 text-xs">{indicator.reference_low ?? "-"} - {indicator.reference_high ?? "-"}</td>
                        <td className="px-6 py-4"><SeverityBadge level={level} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
