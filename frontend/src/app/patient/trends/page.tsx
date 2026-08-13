"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TrendChart from "@/components/TrendChart";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import {
  canRenderTrendChart,
  defaultTrendAnalyte,
  trendReasonMessage,
} from "@/lib/trendUi.mjs";
import type {
  TrendAnalyteSummary,
  TrendExplanationResponse,
  TrendFilter,
  TrendResponse,
} from "@/types/analysis";

const TREND_DISCLAIMER =
  "Biểu đồ và phần giải thích xu hướng chỉ hỗ trợ theo dõi dữ liệu xét nghiệm theo thời gian, không phải chẩn đoán và không thay thế đánh giá của bác sĩ.";

const FILTERS: { value: TrendFilter; label: string }[] = [
  { value: "latest5", label: "5 kết quả gần nhất" },
  { value: "three_months", label: "3 tháng gần nhất" },
];

export default function PatientTrendsPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [analytes, setAnalytes] = useState<TrendAnalyteSummary[]>([]);
  const [selectedAnalyte, setSelectedAnalyte] = useState("");
  const [filter, setFilter] = useState<TrendFilter>("latest5");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [trendLoading, setTrendLoading] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage auth gate is client-only.
    setCheckingAuth(false);
  }, [router]);

  useEffect(() => {
    if (checkingAuth) return;
    const loadAnalytes = async () => {
      setCatalogLoading(true);
      setCatalogError(null);
      try {
        const response = await authFetch("/api/v1/patient/me/trends/analytes");
        if (response.status === 401) {
          clearSession();
          router.replace("/");
          return;
        }
        if (!response.ok) throw new Error("Chưa tải được danh sách chỉ số.");
        const data = await response.json();
        const items = Array.isArray(data.analytes) ? data.analytes as TrendAnalyteSummary[] : [];
        setAnalytes(items);
        setSelectedAnalyte(defaultTrendAnalyte(items));
      } catch (caught: unknown) {
        setCatalogError(caught instanceof Error ? caught.message : "Chưa tải được danh sách chỉ số.");
      } finally {
        setCatalogLoading(false);
      }
    };
    void loadAnalytes();
  }, [checkingAuth, router]);

  useEffect(() => {
    if (!selectedAnalyte) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset stale trend state when catalog has no eligible analyte.
      setTrend(null);
      setExplanation(null);
      return;
    }
    const loadTrend = async () => {
      setTrendLoading(true);
      setTrendError(null);
      setTrend(null);
      setExplanation(null);
      setExplanationError(null);
      try {
        const response = await authFetch(
          `/api/v1/patient/me/trends/${encodeURIComponent(selectedAnalyte)}?filter=${filter}`,
        );
        if (response.status === 401) {
          clearSession();
          router.replace("/");
          return;
        }
        if (!response.ok) throw new Error("Chưa tải được dữ liệu xu hướng.");
        setTrend(await response.json());
      } catch (caught: unknown) {
        setTrendError(caught instanceof Error ? caught.message : "Chưa tải được dữ liệu xu hướng.");
      } finally {
        setTrendLoading(false);
      }
    };
    void loadTrend();
  }, [selectedAnalyte, filter, router]);

  useEffect(() => {
    if (!trend?.trend_available) return;
    const loadExplanation = async () => {
      setExplanationLoading(true);
      setExplanationError(null);
      try {
        const response = await authFetch(
          `/api/v1/patient/me/trends/${encodeURIComponent(trend.analyte_canonical)}/explain?filter=${trend.filter}`,
          { method: "POST" },
        );
        if (response.status === 401) {
          clearSession();
          router.replace("/");
          return;
        }
        if (!response.ok) throw new Error("Phần giải thích xu hướng hiện chưa khả dụng.");
        const data = await response.json() as TrendExplanationResponse;
        setExplanation(data.explanation);
      } catch (caught: unknown) {
        setExplanationError(caught instanceof Error ? caught.message : "Phần giải thích xu hướng hiện chưa khả dụng.");
      } finally {
        setExplanationLoading(false);
      }
    };
    void loadExplanation();
  }, [trend, router]);

  const eligibleCount = useMemo(
    () => analytes.filter((item) => item.trend_available).length,
    [analytes],
  );

  if (checkingAuth) return null;

  return (
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div>
            <h1>Xu hướng chỉ số</h1>
            <p>Theo dõi một chỉ số xét nghiệm qua các lần xét nghiệm đã lưu.</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link href="/patient/history" className="secondary-button px-3 py-2.5">Lịch sử</Link>
            <Link href="/patient" className="secondary-button px-3 py-2.5">Dashboard</Link>
          </div>
        </header>

        <section className="patient-card mt-6 p-5 sm:p-7">
          <div className="section-heading">
            <span className="eyebrow">Indicator Trend</span>
            <h2>Xu hướng chỉ số xét nghiệm</h2>
            <p>Chọn một chỉ số đã có trong Laboratory History và phạm vi dữ liệu cần xem.</p>
          </div>

          {catalogLoading ? (
            <div className="loading-message mt-5" role="status">
              <span className="loading-dot" aria-hidden="true" />
              Đang tải danh sách chỉ số...
            </div>
          ) : catalogError ? (
            <div role="alert" className="error-message">{catalogError}</div>
          ) : analytes.length === 0 ? (
            <div className="empty-metrics mt-5">
              <p className="font-medium text-slate-700">Bạn chưa có dữ liệu xét nghiệm để theo dõi xu hướng.</p>
              <Link href="/patient" className="text-button mt-2">Thêm kết quả xét nghiệm</Link>
            </div>
          ) : (
            <>
              <div className="trend-controls mt-6">
                <label className="field-label" htmlFor="trend-analyte">
                  Chỉ số
                  <select
                    id="trend-analyte"
                    className="form-control mt-2"
                    value={selectedAnalyte}
                    onChange={(event) => setSelectedAnalyte(event.target.value)}
                    disabled={eligibleCount === 0}
                  >
                    {analytes.map((item) => (
                      <option
                        key={item.analyte_canonical}
                        value={item.analyte_canonical}
                        disabled={!item.trend_available}
                      >
                        {item.display_name} - {item.result_count} kết quả{item.trend_available ? "" : " (chưa đủ)"}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="field-label">
                  Phạm vi dữ liệu
                  <div className="trend-filter-tabs mt-2" role="tablist" aria-label="Phạm vi dữ liệu xu hướng">
                    {FILTERS.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        role="tab"
                        aria-selected={filter === item.value}
                        className={filter === item.value ? "active" : ""}
                        onClick={() => setFilter(item.value)}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {eligibleCount === 0 ? (
                <div className="empty-metrics mt-5">
                  <p className="font-medium text-slate-700">Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên.</p>
                </div>
              ) : trendLoading ? (
                <div className="loading-message mt-5" role="status">
                  <span className="loading-dot" aria-hidden="true" />
                  Đang tải dữ liệu xu hướng...
                </div>
              ) : trendError ? (
                <div role="alert" className="error-message">{trendError}</div>
              ) : trend && !canRenderTrendChart(trend) ? (
                <div className="empty-metrics mt-5">
                  <p className="font-medium text-slate-700">{trendReasonMessage(trend.reason)}</p>
                  {trend.reason === "INSUFFICIENT_DATA" && (
                    <p className="mt-2 text-sm text-slate-500">Khoảng thời gian đã chọn chưa có đủ dữ liệu.</p>
                  )}
                </div>
              ) : trend ? (
                <div className="mt-6">
                  <div className="trend-chart-header">
                    <div>
                      <h3>{trend.display_name}</h3>
                      <p>Đơn vị: {trend.canonical_unit}</p>
                    </div>
                    <span className="status-badge status-normal">{trend.result_count} điểm</span>
                  </div>
                  <TrendChart analyte={trend.display_name} unit={trend.canonical_unit} points={trend.points} />

                  <section className="trend-explanation" aria-labelledby="trend-explanation-title">
                    <h3 id="trend-explanation-title">Giải thích xu hướng</h3>
                    {explanationLoading ? (
                      <div className="loading-message mt-3" role="status">
                        <span className="loading-dot" aria-hidden="true" />
                        Đang tạo giải thích xu hướng...
                      </div>
                    ) : explanation ? (
                      <p className="mt-3 text-sm leading-6 text-slate-600">{explanation}</p>
                    ) : explanationError ? (
                      <div role="status" className="info-message mt-3">{explanationError}</div>
                    ) : null}
                  </section>
                </div>
              ) : null}
            </>
          )}

          <div className="disclaimer-box mt-6">
            <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
            <p className="mt-1">{TREND_DISCLAIMER}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
