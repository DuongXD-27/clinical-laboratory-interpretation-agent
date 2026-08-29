"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import TrendChart from "@/components/TrendChart";
import TrendDoctorReviewPanel from "@/components/patient/TrendDoctorReviewPanel";
import TrendHeatmap from "@/components/TrendHeatmap";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { PATIENT_ROUTES } from "@/lib/patientRoutes.mjs";
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
  SectionHeatmapResponse,
  TrendAnalyteSummary,
  TrendExplanationResponse,
  TrendFilter,
  TrendResponse,
} from "@/types/analysis";
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import StatusIndicator from "@/components/common/StatusIndicator";
import SegmentedControl from "@/components/common/SegmentedControl";

const TREND_DISCLAIMER =
  "Biểu đồ và phần giải thích xu hướng chỉ hỗ trợ theo dõi dữ liệu xét nghiệm theo thời gian, không phải chẩn đoán và không thay thế đánh giá của bác sĩ.";

const FILTERS: { value: TrendFilter; label: string }[] = [
  { value: "latest5", label: "5 kết quả gần nhất" },
  { value: "three_months", label: "3 tháng gần nhất" },
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
  const [groupViewMode, setGroupViewMode] = useState<"chart" | "heatmap">("chart");
  const [sectionHeatmap, setSectionHeatmap] = useState<SectionHeatmapResponse | null>(null);
  const [sectionHeatmapLoading, setSectionHeatmapLoading] = useState(false);
  const [sectionHeatmapError, setSectionHeatmapError] = useState<string | null>(null);
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
    if (viewMode !== "group" || groupViewMode !== "heatmap" || !selectedSection) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale heatmap when scope changes
      setSectionHeatmap(null);
      setSectionHeatmapError(null);
      return;
    }
    const loadSectionHeatmap = async () => {
      setSectionHeatmapLoading(true);
      setSectionHeatmapError(null);
      setSectionHeatmap(null);
      try {
        const response = await authFetch(
          `/api/v1/patient/me/trends/sections/${encodeURIComponent(selectedSection)}/heatmap?filter=${filter}`,
        );
        if (response.status === 401) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (!response.ok) throw new Error("Chưa tải được dữ liệu ma trận nhiệt.");
        setSectionHeatmap((await response.json()) as SectionHeatmapResponse);
      } catch (caught: unknown) {
        setSectionHeatmapError(
          caught instanceof Error ? caught.message : "Chưa tải được dữ liệu ma trận nhiệt.",
        );
      } finally {
        setSectionHeatmapLoading(false);
      }
    };
    void loadSectionHeatmap();
  }, [viewMode, groupViewMode, selectedSection, filter, router]);

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
    <div className="patient-page-layout patient-trends-page">
      <PatientPageHeader
        eyebrow="Theo dõi dài hạn"
        title="Xu hướng chỉ số"
        description="Chọn một chỉ số để xem biến động qua các lần xét nghiệm đã lưu."
      />

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
              <Link href={PATIENT_ROUTES.ANALYSIS} className="text-button mt-2">Thêm kết quả xét nghiệm</Link>
            </div>
          ) : (
            <>
              <section className="trend-control-surface" aria-label="Điều khiển biểu đồ xu hướng">
                <div className={`trend-control-grid ${viewMode === "single" ? "trend-control-grid--single" : "trend-control-grid--group-primary"}`}>
                  <div className="trend-control-field-shell" data-trend-field="mode">
                    <p className="trend-control-label">Chế độ xem</p>
                    <SegmentedControl
                      value={viewMode}
                      options={[
                        { value: "single", label: "Từng chỉ số", id: "single-tab", controls: "single-panel" },
                        { value: "group", label: "Cả nhóm chức năng", id: "group-tab", controls: "group-panel" },
                      ]}
                      onValueChange={handleModeChange}
                      ariaLabel="Chế độ xem xu hướng"
                      semantics="tabs"
                    />
                  </div>
                  <div className="trend-control-field-shell" data-trend-field="range">
                    <p className="trend-control-label">Phạm vi dữ liệu</p>
                    <SegmentedControl
                      value={filter}
                      options={FILTERS}
                      onValueChange={setFilter}
                      ariaLabel="Phạm vi dữ liệu xu hướng"
                    />
                  </div>

                  {viewMode === "single" ? (
                    <label className="trend-control-field-shell" data-trend-field="analyte" htmlFor="trend-analyte">
                      <span className="trend-control-label">Chỉ số</span>
                      <select id="trend-analyte" className="patient-control-clinical trend-control-select" value={selectedAnalyte} onChange={(event) => handleAnalyteChange(event.target.value)} disabled={eligibleCount === 0}>
                        {analyteGroups.map((group) => (
                          <optgroup key={group.label} label={group.label}>
                            {group.items.map((item) => (
                              <option key={item.analyte_canonical} value={item.analyte_canonical} disabled={!item.trend_available}>
                                {item.display_name}{item.trend_available ? "" : " (chưa đủ)"}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </label>
                  ) : groupSections.length > 0 ? (
                    <label className="trend-control-field-shell" data-trend-field="section" htmlFor="trend-section">
                      <span className="trend-control-label">Nhóm chức năng</span>
                      <select id="trend-section" className="patient-control-clinical trend-control-select" value={selectedSection} onChange={(event) => { setSelectedSection(event.target.value); setGroupExplanation(null); setGroupExplanationError(null); }}>
                          {groupSections.map((group) => <option key={group.key} value={group.key}>{group.label} ({group.eligible} chỉ số đủ điểm)</option>)}
                      </select>
                    </label>
                  ) : null}
                </div>

                {viewMode === "group" && groupSections.length > 0 ? (
                  <div className="trend-control-grid trend-control-grid--group-secondary">
                    <div className="trend-control-field-shell trend-control-participants" data-trend-field="participants">
                      <p className="trend-control-label">Chỉ số tham gia</p>
                      <div className="trend-participant-chips" aria-label="Chỉ số tham gia trong nhóm">
                        {groupAnalyteItems.map((item) => <span key={item.analyte_canonical}>{item.display_name} · {item.canonical_unit}</span>)}
                      </div>
                    </div>
                    <div className="trend-control-field-shell" data-trend-field="display">
                      <p className="trend-control-label">Kiểu hiển thị</p>
                      <div className="trend-display-actions">
                        <SegmentedControl
                          value={groupViewMode}
                          options={[
                            { value: "chart", label: "Biểu đồ đường" },
                            { value: "heatmap", label: "Ma trận nhiệt" },
                          ]}
                          onValueChange={setGroupViewMode}
                          ariaLabel="Kiểu hiển thị nhóm chức năng"
                        />
                        <button type="button" className="patient-btn-secondary" onClick={() => void loadGroupExplanation()} disabled={groupExplanationLoading || !selectedSection || Boolean(groupExplanation)}>
                          {groupExplanationLoading ? "Đang tạo..." : "Giải thích cả nhóm"}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}
              </section>

              <div id="single-panel" role="tabpanel" aria-labelledby="single-tab" className="min-w-0" hidden={viewMode !== "single"}>
                {viewMode === "single" && (
                  <>
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
                      <div role="alert" className="patient-glass-clinical p-6 mt-6 text-[var(--status-critical-fg)]">{trendError}</div>
                    ) : trend && !canRenderTrendChart(trend) ? (
                      <div className="patient-glass-clinical p-6 mt-6">
                        <p className="font-medium text-slate-700">{trendReasonMessage(trend.reason)}</p>
                        {trend.reason === "INSUFFICIENT_DATA" && (
                          <p className="mt-2 text-sm text-slate-500">Khoảng thời gian đã chọn chưa có đủ dữ liệu.</p>
                        )}
                      </div>
                    ) : trend ? (
                      <div className="trend-result-stack">
                        {trendEscalated && (
                          <div className="mb-6 rounded-xl border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] p-4 text-[var(--status-critical-fg)]" role="alert">
                            <strong className="block mb-1">Cần chú ý ngay</strong>
                            Chỉ số này {trend.critical_status ? "đã đạt" : "đang tiến gần"} ngưỡng nguy kịch — vui lòng liên hệ bác sĩ sớm để được tư vấn kịp thời.
                          </div>
                        )}
                        
                        <div className="trend-result-heading">
                          <h3>{trend.display_name}</h3>
                          <p>
                            {trend.section_label ? `${trend.section_label} · ` : ""}
                            Đơn vị: {trend.canonical_unit} · {dedupeTrendPoints(trend.points).length} lần đo
                          </p>
                        </div>

                        <div className="patient-glass-clinical trend-chart-card p-4 sm:p-6">
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
                      <div className="trend-group-results">
{/* Small Multiples Grid (Hybrid: same-unit analytes → 1 multi-line chart) */}
                        {groupViewMode === "heatmap" ? (
                          sectionHeatmapLoading ? (
                            <div className="patient-glass-clinical p-6 flex items-center justify-center text-sm text-slate-600" role="status" aria-label="Đang tải ma trận nhiệt">
                              <span className="loading-dot mr-2" aria-hidden="true" />
                              Đang tải ma trận nhiệt...
                            </div>
                          ) : sectionHeatmapError ? (
                            <div role="alert" className="patient-glass-clinical p-6 text-[var(--status-critical-fg)]">
                              {sectionHeatmapError}
                            </div>
                          ) : sectionHeatmap ? (
                            <TrendHeatmap data={sectionHeatmap} />
                          ) : null
                        ) : groupTrendsLoading ? (
                          <div className="patient-glass-clinical p-6 mt-6 flex items-center justify-center text-sm text-slate-600" role="status" aria-label="Đang tải biểu đồ nhóm">
                            <span className="loading-dot mr-2" aria-hidden="true" />
                            Đang tải biểu đồ nhóm...
                          </div>
                        ) : groupTrendsError ? (
                          <div role="alert" className="patient-glass-clinical p-6 mt-6 text-[var(--status-critical-fg)]">
                            {groupTrendsError}
                          </div>
                        ) : groupTrends && groupTrends.length > 0 ? (
                          <div className="trend-small-multiples">
                            {groupTrends.map((item) => (
                              <article key={item.analyte_canonical} className="patient-glass-clinical p-4 trend-chart-card">
                                <div className="trend-mini-header mb-2">
                                  <h4>{item.display_name}</h4>
                                  <p>{item.canonical_unit}</p>
                                </div>
                                {(item.critical_status || item.approaching_critical) ? (
                                  <div className="mb-2">
                                    <StatusIndicator state={item.critical_status ? "critical" : "abnormal"} label={item.critical_status ? "Đã vượt ngưỡng nguy kịch" : "Đang tiến gần ngưỡng"} />
                                  </div>
                                ) : null}
                                <TrendChart
                                  analyte={item.display_name}
                                  unit={item.canonical_unit}
                                  points={item.points}
                                  height={280}
                                  referenceLow={item.reference_low}
                                  referenceHigh={item.reference_high}
                                  criticalLow={item.critical_low}
                                  criticalHigh={item.critical_high}
                                />
                              </article>
                            ))}
                          </div>
                        ) : (
                          <div className="patient-glass-clinical p-6 mt-6 text-center text-slate-600">
                            Chưa có chỉ số nào đủ dữ liệu (≥3 lần) trong nhóm này để hiển thị biểu đồ.
                          </div>
                        )}
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
