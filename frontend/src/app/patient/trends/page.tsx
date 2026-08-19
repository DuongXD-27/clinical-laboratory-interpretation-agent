"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TrendChart from "@/components/TrendChart";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import {
  canRenderTrendChart,
  defaultTrendAnalyte,
  groupBySection,
  groupableSections,
  sectionFallbackReason,
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
  const [selectedSection, setSelectedSection] = useState("");
  const [viewMode, setViewMode] = useState<"single" | "group">("single");
  const [groupExplanationLoading, setGroupExplanationLoading] = useState(false);
  const [groupExplanation, setGroupExplanation] = useState<TrendExplanationResponse | null>(null);
  const [groupExplanationError, setGroupExplanationError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);

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
    };
    void loadExplanation();
  }, [trend, router]);

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
    <div className="trend-page-layout">
      <div className="page-section-heading">
        <div>
          <span className="eyebrow">Theo dõi theo thời gian</span>
          <h2>Xu hướng chỉ số</h2>
          <p>Chọn một chỉ số để xem biến động qua các lần xét nghiệm đã lưu.</p>
        </div>
      </div>
      <section className="patient-card p-5 sm:p-7">
          <div className="section-heading">
            <span className="eyebrow">Phân tích xu hướng</span>
            <h2>Xu hướng chỉ số xét nghiệm</h2>
            <p>Chọn một chỉ số đã có trong lịch sử xét nghiệm và phạm vi dữ liệu cần xem.</p>
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
              <Link href="/patient/analysis" className="text-button mt-2">Thêm kết quả xét nghiệm</Link>
            </div>
          ) : (
            <>
              <div className="mode-tabs" role="tablist" aria-label="Chế độ xem xu hướng">
                <button
                  type="button"
                  role="tab"
                  id="single-tab"
                  aria-selected={viewMode === "single"}
                  aria-controls="single-panel"
                  tabIndex={viewMode === "single" ? 0 : -1}
                  onClick={() => setViewMode("single")}
                  className={viewMode === "single" ? "active" : ""}
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
                  onClick={() => setViewMode("group")}
                  className={viewMode === "group" ? "active" : ""}
                >
                  Cả nhóm chức năng
                </button>
              </div>

              <div className="field-label mt-5">
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

              <div id="single-panel" role="tabpanel" aria-labelledby="single-tab" className="trend-mode-panel" hidden={viewMode !== "single"}>
                {viewMode === "single" && (
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
                          {analyteGroups.map((group) => (
                            <optgroup key={group.label} label={group.label}>
                              {group.items.map((item) => (
                                <option
                                  key={item.analyte_canonical}
                                  value={item.analyte_canonical}
                                  disabled={!item.trend_available}
                                >
                                  {item.display_name} - {item.result_count} kết quả{item.trend_available ? "" : " (chưa đủ)"}
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                      </label>
                    </div>

                    {eligibleCount === 0 ? (
                      <div className="empty-metrics mt-5">
                        <p className="font-medium text-slate-700">Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên.</p>
                        <p className="mt-2 text-sm text-slate-500">
                          Hãy lưu ít nhất 3 phiếu khác nhau cho cùng một chỉ số; các phiếu trùng ngày và cùng bộ kết quả có thể được nhận diện là trùng lặp.
                        </p>
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
                        {trendEscalated && (
                          <div className="critical-report-notice mb-5" role="alert">
                            <strong>Cần chú ý ngay</strong>
                            Chỉ số này {trend.critical_status ? "đã đạt" : "đang tiến gần"} ngưỡng nguy kịch — vui lòng liên hệ bác sĩ sớm để được tư vấn kịp thời.
                          </div>
                        )}
                        <div className="trend-chart-header">
                          <div>
                            <h3>{trend.display_name}</h3>
                            <p>
                              {trend.section_label ? `${trend.section_label} · ` : ""}
                              Đơn vị: {trend.canonical_unit}
                            </p>
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
              </div>

              <div id="group-panel" role="tabpanel" aria-labelledby="group-tab" className="trend-mode-panel" hidden={viewMode !== "group"}>
                {viewMode === "group" &&
                  (groupSections.length === 0 ? (
                    <div className="empty-metrics mt-5">
                      <p className="font-medium text-slate-700">Chưa có nhóm chức năng nào đủ 2 chỉ số để giải thích cùng nhau.</p>
                      <p className="mt-2 text-sm text-slate-500">
                        Hãy lưu thêm kết quả xét nghiệm cho các chỉ số trong cùng một nhóm (ví dụ HbA1c và LDL-C) để sử dụng chế độ này.
                      </p>
                    </div>
                  ) : (
                    <>
                      <div className="trend-group-controls mt-6">
                        <label className="field-label" htmlFor="trend-section">
                          Nhóm chức năng
                          <select
                            id="trend-section"
                            className="form-control mt-2"
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
                        <button
                          type="button"
                          className="primary-button"
                          onClick={() => void loadGroupExplanation()}
                          disabled={groupExplanationLoading || !selectedSection}
                        >
                          {groupExplanationLoading ? "Đang tạo..." : "Giải thích cả nhóm"}
                        </button>
                      </div>

                      <div className="analyte-chip-list mt-4" aria-label="Chỉ số tham gia trong nhóm">
                        {groupAnalyteItems.map((item) => (
                          <span key={item.analyte_canonical} className="analyte-chip">
                            {item.display_name} · {item.canonical_unit}
                          </span>
                        ))}
                      </div>

                      <section className="trend-explanation" aria-labelledby="trend-group-explanation-title">
                        <h3 id="trend-group-explanation-title">Giải thích theo nhóm chức năng</h3>
                        <p className="mt-2 text-sm text-slate-500">
                          Đọc các chỉ số cùng nhóm với nhau — ví dụ HbA1c và LDL-C — để thấy mối liên hệ trong dữ liệu,
                          không phải chẩn đoán.
                        </p>
                        {groupExplanationLoading ? (
                          <div className="loading-message mt-3" role="status">
                            <span className="loading-dot" aria-hidden="true" />
                            Đang tạo giải thích theo nhóm...
                          </div>
                        ) : groupExplanation ? (
                          groupExplanation.fallback ? (
                            <div role="status" className="info-message mt-3">
                              {sectionFallbackReason(groupExplanation.reason)}
                            </div>
                          ) : (
                            <p className="mt-3 text-sm leading-6 text-slate-600">{groupExplanation.explanation}</p>
                          )
                        ) : groupExplanationError ? (
                          <div role="status" className="info-message mt-3">{groupExplanationError}</div>
                        ) : (
                          <p className="mt-3 text-sm text-slate-500">
                            Chọn nhóm chức năng bên trên rồi bấm &ldquo;Giải thích cả nhóm&rdquo;.
                          </p>
                        )}
                      </section>
                    </>
                  ))}
              </div>
            </>
          )}

          <div className="disclaimer-box mt-6">
            <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
            <p className="mt-1">{TREND_DISCLAIMER}</p>
          </div>
      </section>
    </div>
  );
}
