"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
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
import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRight, CheckCircle2, Clock3, ListFilter } from "lucide-react";

const FILTERS: { key: TrendReviewStatus | "all"; label: string }[] = [
  { key: "PENDING", label: "Đang chờ" },
  { key: "REVIEWED", label: "Đã review" },
  { key: "all", label: "Tất cả" },
];

function statusText(value: TrendReviewStatus) {
  if (value === "PENDING") return "Đang chờ";
  if (value === "REVIEWED") return "Đã review";
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- auth state is read from localStorage after client mount.
    setCheckingAuth(false);
  }, [router]);

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
      setError(caught instanceof Error ? caught.message : "Không tải được yêu cầu review xu hướng.");
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
        title="Đánh giá biểu đồ xu hướng"
        description="Kiểm chứng các nhận xét xu hướng do AI tạo trước khi phản hồi cho bệnh nhân."
      />

      <section className="doctor-page-section doctor-queue-workspace">
        <div className="doctor-filter-heading"><ListFilter aria-hidden="true" /> Trạng thái yêu cầu</div>

        <Tabs value={status} onValueChange={(value) => setStatus(value as TrendReviewStatus | "all")} className="doctor-queue-tabs doctor-trend-tabs">
          <TabsList aria-label="Lọc yêu cầu review xu hướng">
            {FILTERS.map((item) => <TabsTrigger key={item.key} value={item.key}>{item.label}</TabsTrigger>)}
          </TabsList>
        </Tabs>

        {loading && (
          <div className="doctor-skeleton-stack" role="status" aria-label="Đang tải yêu cầu review xu hướng">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="doctor-queue-skeleton" />
            ))}
          </div>
        )}

        {error && !loading && (
          <div className="doctor-state-card doctor-state-card--error" role="alert">
            <p>{error}</p>
            <Button type="button" variant="outline" onClick={() => void load()}>Thử lại</Button>
          </div>
        )}

        {!error && !loading && items.length === 0 && (
          <div className="doctor-state-card">
            <span className="doctor-state-card__icon" aria-hidden="true"><CheckCircle2 /></span>
            <h2>Không có yêu cầu review xu hướng.</h2>
            <p>
              {status === "PENDING" ? "Hiện chưa có yêu cầu nào đang chờ xử lý." : "Bộ lọc hiện tại đang rỗng."}
            </p>
          </div>
        )}

        {!error && !loading && items.length > 0 && (
          <ul className="doctor-queue-cards" aria-label={`Danh sách ${total} yêu cầu review xu hướng`}>
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/doctor/trend-reviews/${item.id}`}
                  className="doctor-trend-card"
                >
                  <div className="doctor-trend-card__main">
                    <div className="doctor-queue-card__identity">
                      <strong>{item.patient_name}</strong>
                      <span>Hồ sơ #{item.patient_id}</span>
                    </div>
                    <div className="doctor-trend-card__metric">
                      {item.display_name} · {item.point_count} mốc xét nghiệm · {item.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"}
                    </div>
                    <div className="doctor-trend-card__time"><Clock3 aria-hidden="true" /> Gửi lúc {formatMoment(item.requested_at)}</div>
                  </div>
                  <div className="doctor-trend-card__status">
                    <StatusIndicator state={statusState(item.status)} label={statusText(item.status)} />
                    <span className="doctor-queue-card__action">
                      Mở review <ArrowRight aria-hidden="true" />
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
