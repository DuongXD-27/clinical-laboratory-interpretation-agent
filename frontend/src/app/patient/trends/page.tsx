"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import TrendChart from "@/components/TrendChart";
import TrendDoctorReviewPanel from "@/components/patient/TrendDoctorReviewPanel";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import {
  canRenderTrendChart,
  defaultTrendAnalyte,
  groupBySection,
  groupableSections,
  sectionFallbackReason,
  trendReasonMessage,
  dedupeTrendPoints,
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

const CHART_COLORS = [
  "#1769e0",
  "#dc2626",
  "#16a34a",
  "#ea580c",
  "#9333ea",
  "#0891b2",
  "#db2777",
  "#65a30d",
];

export default function PatientTrendsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [analytes, setAnalytes] = useState<TrendAnalyteSummary[]>([]);
  const [selectedAnalyte, setSelectedAnalyte] = useState("");
  const [filter, setFilter] = useState<TrendFilter>("latest5");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [trendLoading, setTrendLoading] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState("");
  const queryMode = searchParams.get("mode");
  const queryAnalyte = searchParams.get("analyte");
  const viewMode = queryMode === "group" ? "group" : "single";
  const [groupExplanationLoading, setGroupExplanationLoading] = useState(false);
  const [groupExplanation, setGroupExplanation] = useState<TrendExplanationResponse | null>(null);
  const [groupExplanationError, setGroupExplanationError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [groupTrends, setGroupTrends] = useState<TrendResponse[] | null>(null);
  const [groupTrendsLoading, setGroupTrendsLoading] = useState(false);
  const [groupTrendsError, setGroupTrendsError] = useState<string | null>(null);
  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/login");
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
          router.replace("/login");
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
          router.replace("/login");
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

  const loadExplanation = useCallback(async () => {
    if (!trend?.trend_available) return;
    setExplanationLoading(true);
    setExplanationError(null);
    try {
      const response = await authFetch(
        `/api/v1/patient/me/trends/${encodeURIComponent(trend.analyte_canonical)}/explain?filter=${trend.filter}`,
        { method: "POST" },
      );
      if (response.status === 401) {
        clearSession();
        router.replace("/login");
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
  }, [trend, router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear explanation when trend changes
    setExplanation(null);
    setExplanationError(null);
  }, [trend]);

  const eligibleCount = useMemo(
    () => analytes.filter((item) => item.trend_available).length,
    [analytes],
  );

  const analyteGroups = useMemo(() => groupBySection(analytes), [analytes]);
  const groupSections = useMemo(() => groupableSections(analytes), [analytes]);
  const groupAnalyteItems = useMemo(
    () => analytes.filter((item) => item.section === selectedSection && item.trend_available),
    [analytes, selectedSection],
  );
  const trendEscalated = Boolean(trend?.critical_status || trend?.approaching_critical);

  // Group trends by canonical_unit for hybrid rendering (same unit → 1 chart)
  const unitGroups = useMemo(() => {
    if (!groupTrends) return [];
    const map = new Map<string, TrendResponse[]>();
    for (const trend of groupTrends) {
      const key = trend.canonical_unit;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(trend);
    }
    return Array.from(map.entries()).map(([unit, trends]) => ({ unit, trends }));
  }, [groupTrends]);

  useEffect(() => {
    if (groupSections.length === 0) return;
    if (!groupSections.some((group) => group.key === selectedSection)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- keep the section selector aligned with the catalog.
      setSelectedSection(groupSections[0].key);
    }
  }, [groupSections, selectedSection]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale group result when the data scope changes.
    setGroupExplanation(null);
    setGroupExplanationError(null);
  }, [filter]);

  useEffect(() => {
    if (viewMode !== "group" || !selectedSection) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale group trends when scope changes
      setGroupTrends(null);
      setGroupTrendsError(null);
      return;
    }
    const loadGroupTrends = async () => {
      setGroupTrendsLoading(true);
      setGroupTrendsError(null);
      setGroupTrends(null);
      try {
        const response = await authFetch(
          `/api/v1/patient/me/trends/sections/${encodeURIComponent(selectedSection)}/trends?filter=${filter}`,
        );
        if (response.status === 401) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (!response.ok) throw new Error("Chưa tải được dữ liệu biểu đồ nhóm.");
        const data = await response.json();
        setGroupTrends((data.trends ?? []) as TrendResponse[]);
      } catch (caught: unknown) {
        setGroupTrendsError(
          caught instanceof Error ? caught.message : "Chưa tải được dữ liệu biểu đồ nhóm.",
        );
      } finally {
        setGroupTrendsLoading(false);
      }
    };
    void loadGroupTrends();
  }, [viewMode, selectedSection, filter, router]);

  useEffect(() => {
    if (analytes.length === 0) return;
    if (viewMode === "single" && queryAnalyte) {
      const matched = analytes.find((a) => a.analyte_canonical === queryAnalyte);
      if (matched?.trend_available) {
        if (selectedAnalyte !== queryAnalyte) {
          // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronize deep link state
          setSelectedAnalyte(queryAnalyte);
        }
      } else {
        router.replace(pathname);
      }
    }
  }, [queryAnalyte, analytes, selectedAnalyte, viewMode, pathname, router]);

  const handleModeChange = (mode: "single" | "group") => {
    if (mode === "single") {
      if (selectedAnalyte) {
        router.replace(`${pathname}?analyte=${encodeURIComponent(selectedAnalyte)}`);
      } else {
        router.replace(pathname);
      }
    } else {
      router.replace(`${pathname}?mode=group`);
    }
  };

  const handleAnalyteChange = (value: string) => {
    setSelectedAnalyte(value);
    router.replace(`${pathname}?analyte=${encodeURIComponent(value)}`);
  };

  const loadGroupExplanation = async () => {
    if (!selectedSection) return;
    setGroupExplanationLoading(true);
    setGroupExplanationError(null);
    setGroupExplanation(null);
    try {
      const response = await authFetch(
        `/api/v1/patient/me/trends/sections/${encodeURIComponent(selectedSection)}/explain?filter=${filter}`,
        { method: "POST" },
      );
      if (response.status === 401) {
        clearSession();
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Phần giải thích theo nhóm hiện chưa khả dụng.");
      setGroupExplanation(await response.json() as TrendExplanationResponse);
    } catch (caught: unknown) {
      setGroupExplanationError(
        caught instanceof Error ? caught.message : "Phần giải thích theo nhóm hiện chưa khả dụng.",
      );
    } finally {
      setGroupExplanationLoading(false);
    }
  };

  if (checkingAuth) return null;

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-12 px-4 sm:px-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">Xu hướng chỉ số</h1>
        <p className="text-muted-foreground">
          Chọn một chỉ số để xem biến động qua các lần xét nghiệm đã lưu.
        </p>
      </section>

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
              <Link href="/patient/analysis" className="text-button mt-2">Thêm kết quả xét nghiệm</Link>
            </div>
          ) : (
            <>
              <div className="patient-glass-focal p-1.5 inline-grid grid-cols-2 w-full max-w-sm mb-6" role="tablist" aria-label="Chế độ xem xu hướng">
                <button
                  type="button"
                  role="tab"
                  id="single-tab"
                  aria-selected={viewMode === "single"}
                  aria-controls="single-panel"
                  tabIndex={viewMode === "single" ? 0 : -1}
                  onClick={() => handleModeChange("single")}
                  className={`flex items-center justify-center min-h-[38px] rounded-xl text-sm font-semibold transition-all duration-150 ${viewMode === "single" ? "bg-white text-[var(--brand-strong)] shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                >
                  Từng chỉ số
                </button>
                <button
                  type="button"
                  role="tab"
                  id="group-tab"
                  aria-selected={viewMode === "group"}
                  aria-controls="group-panel"
                  tabIndex={viewMode === "group" ? 0 : -1}
                  onClick={() => handleModeChange("group")}
                  className={`flex items-center justify-center min-h-[38px] rounded-xl text-sm font-semibold transition-all duration-150 ${viewMode === "group" ? "bg-white text-[var(--brand-strong)] shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                >
                  Cả nhóm chức năng
                </button>
              </div>

              <div className="field-label mb-2">
                Phạm vi dữ liệu
                <div className="trend-filter-tabs mt-2" aria-label="Phạm vi dữ liệu xu hướng">
                  {FILTERS.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      aria-pressed={filter === item.value}
                      className={filter === item.value ? "active" : ""}
                      onClick={() => setFilter(item.value)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div id="single-panel" role="tabpanel" aria-labelledby="single-tab" className="min-w-0" hidden={viewMode !== "single"}>
                {viewMode === "single" && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end mt-2">
                      <label className="field-label" htmlFor="trend-analyte">
                        Chỉ số
                        <select
                          id="trend-analyte"
                          className="patient-control-clinical w-full min-h-[46px] px-3 py-2 mt-2"
                          value={selectedAnalyte}
                          onChange={(event) => handleAnalyteChange(event.target.value)}
                          disabled={eligibleCount === 0}
                        >
                          {analyteGroups.map((group) => (
                            <optgroup key={group.label} label={group.label}>
                              {group.items.map((item) => (
                                <option
                                  key={item.analyte_canonical}
                                  value={item.analyte_canonical}
                                  disabled={!item.trend_available}
                                >
                                  {item.display_name}{item.trend_available ? "" : " (chưa đủ)"}
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                      </label>
                    </div>

                    {eligibleCount === 0 ? (
                      <div className="patient-glass-clinical p-6 mt-6">
                        <p className="font-medium text-slate-700">Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên.</p>
                        <p className="mt-2 text-sm text-slate-500">
                          Hãy lưu ít nhất 3 phiếu khác nhau cho cùng một chỉ số; các phiếu trùng ngày và cùng bộ kết quả có thể được nhận diện là trùng lặp.
                        </p>
                      </div>
                    ) : trendLoading ? (
                      <div className="patient-glass-clinical p-6 mt-6 flex items-center justify-center text-sm text-slate-600" role="status">
                        <span className="loading-dot mr-2" aria-hidden="true" />
                        Đang tải dữ liệu xu hướng...
                      </div>
                    ) : trendError ? (
                      <div role="alert" className="patient-glass-clinical p-6 mt-6 text-red-700">{trendError}</div>
                    ) : trend && !canRenderTrendChart(trend) ? (
                      <div className="patient-glass-clinical p-6 mt-6">
                        <p className="font-medium text-slate-700">{trendReasonMessage(trend.reason)}</p>
                        {trend.reason === "INSUFFICIENT_DATA" && (
                          <p className="mt-2 text-sm text-slate-500">Khoảng thời gian đã chọn chưa có đủ dữ liệu.</p>
                        )}
                      </div>
                    ) : trend ? (
                      <div className="mt-8 space-y-6">
                        {trendEscalated && (
                          <div className="bg-red-50 text-red-800 p-4 rounded-xl border border-red-200 mb-6" role="alert">
                            <strong className="block mb-1">Cần chú ý ngay</strong>
                            Chỉ số này {trend.critical_status ? "đã đạt" : "đang tiến gần"} ngưỡng nguy kịch — vui lòng liên hệ bác sĩ sớm để được tư vấn kịp thời.
                          </div>
                        )}
                        
                        <div className="mb-2">
                          <h3 className="text-xl font-bold text-slate-900">{trend.display_name}</h3>
                          <p className="text-sm text-slate-500 mt-1">
                            {trend.section_label ? `${trend.section_label} · ` : ""}
                            Đơn vị: {trend.canonical_unit} · {dedupeTrendPoints(trend.points).length} lần đo
                          </p>
                        </div>

                        <div className="patient-glass-clinical p-4 sm:p-6">
                          <TrendChart
                            analyte={trend.display_name}
                            unit={trend.canonical_unit}
                            points={trend.points}
                            referenceLow={trend.reference_low}
                            referenceHigh={trend.reference_high}
                            criticalLow={trend.critical_low}
                            criticalHigh={trend.critical_high}
                          />
                          <p className="mt-4 text-xs text-slate-500 text-center">
                            Mỗi điểm là một lần xét nghiệm đã ghi nhận. Đường nối chỉ giúp theo dõi sự thay đổi giữa các lần đo, không thể hiện dữ liệu trong khoảng thời gian giữa hai lần xét nghiệm.
                          </p>
                          <div className="sr-only">
                            <h4>Dữ liệu các lần đo cho biểu đồ {trend.display_name}</h4>
                            <ul>
                              {trend.points.map((p, i) => (
                                <li key={i}>
                                  Ngày {p.test_date}: {p.value} {trend.canonical_unit}, trạng thái: {p.assessment || "Không có"}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>

                        <div className="flex justify-start">
                          <button
                            type="button"
                            className="patient-btn-secondary"
                            onClick={() => void loadExplanation()}
                            disabled={explanationLoading || Boolean(explanation)}
                          >
                            {explanationLoading ? "Đang tạo..." : "Giải thích xu hướng"}
                          </button>
                        </div>

                        {explanation || explanationError ? (
                          <section className="patient-glass-clinical p-5 sm:p-6" aria-labelledby="trend-explanation-title">
                            <div className="flex items-center justify-between mb-3">
                              <h3 id="trend-explanation-title" className="text-sm font-semibold text-slate-800">Giải thích của AI</h3>
                              <span className="text-xs text-slate-400">LumiLab</span>
                            </div>
                            {explanation ? (
                              <p className="text-sm leading-relaxed text-slate-700">{explanation}</p>
                            ) : (
                              <div role="status" className="text-sm text-slate-600">{explanationError}</div>
                            )}
                          </section>
                        ) : null}

                        <TrendDoctorReviewPanel
                          trend={trend}
                          explanation={explanation}
                          onUnauthorized={() => {
                            clearSession();
                            router.replace("/login");
                          }}
                        />
                      </div>
                    ) : null}
                  </>
                )}
              </div>

              <div id="group-panel" role="tabpanel" aria-labelledby="group-tab" className="min-w-0" hidden={viewMode !== "group"}>
                {viewMode === "group" &&
                  (groupSections.length === 0 ? (
                    <div className="patient-glass-clinical p-6 mt-6">
                      <p className="font-medium text-slate-700">Chưa có nhóm chức năng nào đủ điều kiện để giải thích cùng nhau.</p>
                      <p className="mt-2 text-sm text-slate-500">
                        Hãy lưu thêm kết quả xét nghiệm cho các chỉ số trong cùng một nhóm (ví dụ HbA1c và LDL-C) để sử dụng chế độ này.
                      </p>
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end mt-2">
                        <label className="field-label" htmlFor="trend-section">
                          Nhóm chức năng
                          <select
                            id="trend-section"
                            className="patient-control-clinical w-full min-h-[46px] px-3 py-2 mt-2"
                            value={selectedSection}
                            onChange={(event) => {
                              setSelectedSection(event.target.value);
                              setGroupExplanation(null);
                              setGroupExplanationError(null);
                            }}
                          >
                            {groupSections.map((group) => (
                              <option key={group.key} value={group.key}>
                                {group.label} ({group.eligible} chỉ số đủ điểm)
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>

                      <div className="mt-8">
                        <h3 className="text-sm font-semibold text-slate-800 mb-3">Chỉ số tham gia</h3>
                        <div className="flex flex-wrap gap-2" aria-label="Chỉ số tham gia trong nhóm">
                          {groupAnalyteItems.map((item) => (
                            <span key={item.analyte_canonical} className="inline-flex items-center rounded-md bg-[rgba(255,255,255,0.7)] backdrop-blur-md px-2.5 py-1 text-sm font-medium text-slate-700 border border-[rgba(203,213,225,0.5)]">
                              {item.display_name} · {item.canonical_unit}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="mt-6 flex flex-col gap-4 w-full">
{/* Small Multiples Grid (Hybrid: same-unit analytes → 1 multi-line chart) */}
                        {groupTrendsLoading ? (
                          <div className="patient-glass-clinical p-6 mt-6 flex items-center justify-center text-sm text-slate-600" role="status" aria-label="Đang tải biểu đồ nhóm">
                            <span className="loading-dot mr-2" aria-hidden="true" />
                            Đang tải biểu đồ nhóm...
                          </div>
                        ) : groupTrendsError ? (
                          <div role="alert" className="patient-glass-clinical p-6 mt-6 text-red-700">
                            {groupTrendsError}
                          </div>
                        ) : unitGroups.length > 0 ? (
                          <>
                            {/* Mobile Accordion — triggered when >5 unit-groups */}
                            <div className="lg:hidden space-y-3">
                              {unitGroups.map(({ unit, trends }, idx) => (
                                <details key={unit} className="patient-glass-clinical p-4" open={idx < 2}>
                                  <summary className="flex items-center justify-between cursor-pointer list-none select-none">
                                    <div className="flex-1 min-w-0">
                                      <h4 className="font-medium text-slate-900 truncate">{unit}</h4>
                                      <p className="text-xs text-slate-500 truncate">
                                        {trends.map((t) => t.display_name).join(", ")} · {trends.length} chỉ số
                                      </p>
                                    </div>
                                    {trends.some((t) => t.critical_status || t.approaching_critical) && (
                                      <span className="text-xs ml-2 text-red-600">⚠ Nguy kịch</span>
                                    )}
                                  </summary>
                                  <div className="mt-3">
                                    {trends.length === 1 ? (
                                      <TrendChart
                                        analyte={trends[0].display_name}
                                        unit={unit}
                                        points={trends[0].points}
                                        height={320}
                                        referenceLow={trends[0].reference_low}
                                        referenceHigh={trends[0].reference_high}
                                        criticalLow={trends[0].critical_low}
                                        criticalHigh={trends[0].critical_high}
                                      />
                                    ) : (
                                      <TrendChart
                                        analytes={trends.map((t, i) => ({
                                          analyte: t.display_name,
                                          display_name: t.display_name,
                                          unit,
                                          points: t.points,
                                          color: CHART_COLORS[i % CHART_COLORS.length],
                                        }))}
                                        height={320}
                                      />
                                    )}
                                  </div>
                                </details>
                              ))}
                            </div>

                            {/* Desktop/Tablet Grid — same-unit analytes → 1 multi-line chart */}
                            <div
                              className="hidden lg:grid gap-4"
                              style={{
                                gridTemplateColumns: `repeat(${Math.min(unitGroups.length, 3)}, minmax(0, 1fr))`,
                              }}
                            >
                              {unitGroups.map(({ unit, trends }) => {
                                const anyCritical = trends.some((t) => t.critical_status);
                                const anyApproaching = trends.some((t) => t.approaching_critical);
                                return (
                                  <div key={unit} className="patient-glass-clinical p-4">
                                    <div className="trend-mini-header mb-2">
                                      <h4 className="font-medium text-slate-900">{unit}</h4>
                                      <p className="text-xs text-slate-500">
                                        {trends.map((t) => t.display_name).join(", ")} · {trends.length} chỉ số
                                      </p>
                                    </div>
                                    {(anyCritical || anyApproaching) && (
                                      <div className={`trend-critical-badge mb-2 text-xs ${anyCritical ? "" : "approaching"}`}>
                                        {anyCritical ? "⚠ Đã vượt ngưỡng nguy kịch" : "⚠ Đang tiến gần ngưỡng"}
                                      </div>
                                    )}
                                    {trends.length === 1 ? (
                                      <TrendChart
                                        analyte={trends[0].display_name}
                                        unit={unit}
                                        points={trends[0].points}
                                        height={320}
                                        referenceLow={trends[0].reference_low}
                                        referenceHigh={trends[0].reference_high}
                                        criticalLow={trends[0].critical_low}
                                        criticalHigh={trends[0].critical_high}
                                      />
                                    ) : (
                                      <TrendChart
                                        analytes={trends.map((t, i) => ({
                                          analyte: t.display_name,
                                          display_name: t.display_name,
                                          unit,
                                          points: t.points,
                                          color: CHART_COLORS[i % CHART_COLORS.length],
                                        }))}
                                        height={320}
                                      />
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </>
                        ) : (
                          <div className="patient-glass-clinical p-6 mt-6 text-center text-slate-600">
                            Chưa có chỉ số nào đủ dữ liệu (≥3 lần) trong nhóm này để hiển thị biểu đồ.
                          </div>
                        )}

                        <button
                          type="button"
                          className="patient-btn-secondary self-start"
                          onClick={() => void loadGroupExplanation()}
                          disabled={groupExplanationLoading || !selectedSection || Boolean(groupExplanation)}
                        >
                          {groupExplanationLoading ? "Đang tạo..." : "Giải thích cả nhóm"}
                        </button>
                      </div>

                      {(groupExplanation || groupExplanationError) ? (
                        <section className="patient-glass-clinical p-5 sm:p-6 mt-6" aria-labelledby="trend-group-explanation-title">
                          <div className="flex items-center justify-between mb-3">
                            <h3 id="trend-group-explanation-title" className="text-sm font-semibold text-slate-800">Giải thích của AI</h3>
                            <span className="text-xs text-slate-400">LumiLab</span>
                          </div>
                          {groupExplanation ? (
                            groupExplanation.fallback ? (
                              <div role="status" className="text-sm text-slate-600">
                                {sectionFallbackReason(groupExplanation.reason)}
                              </div>
                            ) : (
                              <p className="text-sm leading-relaxed text-slate-700">{groupExplanation.explanation}</p>
                            )
                          ) : (
                            <div role="status" className="text-sm text-slate-600">{groupExplanationError}</div>
                          )}
                        </section>
                      ) : null}
                    </>
                  ))}
              </div>
            </>
          )}

          <div className="disclaimer-box mt-6">
            <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
            <p className="mt-1">{TREND_DISCLAIMER}</p>
          </div>
    </div>
  );
}
