"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, ViewTransition } from "react";
import { useRouter } from "next/navigation";
import {
  clearSession,
  fetchDoctorTrendReviewQueue,
  getRole,
  getToken,
  UnauthorizedError,
} from "@/lib/api";
import { formatMoment } from "@/lib/patientUi.mjs";
import type { DoctorTrendReviewSummary, TrendReviewStatus } from "@/types/analysis";
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import DoctorQueueToolbar from "@/components/doctor/DoctorQueueToolbar";
import DoctorStatePanel from "@/components/doctor/DoctorStatePanel";
import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import { Button } from "@/components/ui/button";
import { motionElementName } from "@/lib/motion";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRight, Clock3 } from "lucide-react";

const FILTERS: { key: TrendReviewStatus | "all"; label: string }[] = [
  { key: "PENDING", label: "Đang chờ" },
  { key: "REVIEWED", label: "Đã đánh giá" },
  { key: "all", label: "Tất cả" },
];
const VALID_FILTERS = new Set<TrendReviewStatus | "all">(FILTERS.map((item) => item.key));

function statusText(value: TrendReviewStatus) {
  if (value === "PENDING") return "Đang chờ";
  if (value === "REVIEWED") return "Đã đánh giá";
  if (value === "CANCELLED") return "Đã huỷ";
  return "Từ chối";
}

function statusState(value: TrendReviewStatus): StatusState {
  if (value === "PENDING") return "pending";
  if (value === "REVIEWED") return "completed";
  if (value === "CANCELLED") return "cancelled";
  return "rejected";
}

export default function DoctorTrendReviewsPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [status, setStatus] = useState<TrendReviewStatus | "all">("PENDING");
  const [items, setItems] = useState<DoctorTrendReviewSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "doctor") {
      router.replace("/");
      return;
    }
    const queryStatus = new URLSearchParams(window.location.search).get("status") as TrendReviewStatus | "all" | null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- auth/query state is read after client mount.
    if (queryStatus && VALID_FILTERS.has(queryStatus)) setStatus(queryStatus);
    setCheckingAuth(false);
  }, [router]);

  function changeStatus(nextStatus: TrendReviewStatus | "all") {
    setStatus(nextStatus);
    window.history.replaceState(null, "", `/doctor/trend-reviews?status=${nextStatus}`);
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDoctorTrendReviewQueue(status);
      setItems(data.items);
      setTotal(data.total);
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        clearSession();
        router.replace("/");
        return;
      }
      setItems([]);
      setTotal(0);
      setError(caught instanceof Error ? caught.message : "Không tải được yêu cầu đánh giá xu hướng.");
    } finally {
      setLoading(false);
    }
  }, [router, status]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() owns async request state for this client-only page.
    if (!checkingAuth) void load();
  }, [checkingAuth, load]);

  if (checkingAuth) return null;

  return (
    <div className="doctor-page doctor-trend-page">
      <DoctorPageHeader
        eyebrow="Không gian bác sĩ"
        title="Đánh giá xu hướng"
        description="Kiểm chứng nhận xét xu hướng do AI tạo trước khi phản hồi cho bệnh nhân."
      />

      <section className="doctor-page-section doctor-queue-workspace">
        <DoctorQueueToolbar
          total={total}
          itemLabel="yêu cầu trong bộ lọc"
          contextLabel="Mới gửi trước"
          filters={(
            <Tabs value={status} onValueChange={(value) => changeStatus(value as TrendReviewStatus | "all")} className="doctor-queue-tabs doctor-trend-tabs">
              <TabsList variant="line" aria-label="Lọc yêu cầu đánh giá xu hướng">
                {FILTERS.map((item) => <TabsTrigger key={item.key} value={item.key}>{item.label}</TabsTrigger>)}
              </TabsList>
            </Tabs>
          )}
        />

        {loading && (
          <div className="doctor-skeleton-stack" role="status" aria-label="Đang tải yêu cầu đánh giá xu hướng">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="doctor-queue-skeleton" />
            ))}
          </div>
        )}

        {error && !loading && (
          <DoctorStatePanel
            kind="error"
            title="Không tải được yêu cầu đánh giá xu hướng"
            description={error}
            action={<Button type="button" variant="outline" onClick={() => void load()}>Thử lại</Button>}
          />
        )}

        {!error && !loading && items.length === 0 && (
          <DoctorStatePanel
            kind="empty"
            title="Không có yêu cầu đánh giá xu hướng"
            description={status === "PENDING" ? "Hiện chưa có yêu cầu nào đang chờ xử lý." : "Bộ lọc hiện tại đang rỗng."}
          />
        )}

        {!error && !loading && items.length > 0 && (
          <ul className="doctor-queue-cards" aria-label={`Danh sách ${total} yêu cầu đánh giá xu hướng`}>
            {items.map((item, index) => (
              <li key={item.id}>
                <Link
                  href={`/doctor/trend-reviews/${item.id}`}
                  transitionTypes={["nav-forward"]}
                  className="doctor-trend-card doctor-trend-row motion-row-stagger"
                  style={{ "--stagger-index": index } as React.CSSProperties}
                >
                  <ViewTransition name={motionElementName("doctor-trend-review", item.id)} default="none" share="lumilens-shared-detail">
                  <div className="doctor-trend-card__main">
                    <div className="doctor-queue-card__identity">
                      <strong>{item.patient_name}</strong>
                      <span>Hồ sơ #{item.patient_id}</span>
                    </div>
                    <div className="doctor-trend-card__metric">
                      <strong>{item.display_name}</strong>
                      <span>{item.point_count} mốc · {item.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"}</span>
                    </div>
                    <div className="doctor-trend-card__time"><Clock3 aria-hidden="true" /> Gửi lúc {formatMoment(item.requested_at)}</div>
                  </div>
                  </ViewTransition>
                  <div className="doctor-trend-card__status">
                    <StatusIndicator state={statusState(item.status)} label={statusText(item.status)} />
                    <span className="doctor-queue-card__action">
                      Mở đánh giá <ArrowRight aria-hidden="true" />
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
