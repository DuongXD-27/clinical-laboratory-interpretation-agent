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
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <section className="flex flex-col">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-foreground">Đánh giá biểu đồ xu hướng</h1>
          <p className="text-muted-foreground mt-1">
            Xem các yêu cầu bệnh nhân gửi để bác sĩ kiểm chứng nhận xét xu hướng của AI.
          </p>
        </header>

        <div className="flex flex-wrap items-center gap-2 mb-6" aria-label="Lọc yêu cầu review xu hướng">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={status === item.key}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors border ${
                status === item.key
                  ? "bg-[var(--glass-surface)] border-[var(--holo-cyan)]/30 text-foreground shadow-sm"
                  : "bg-[var(--surface)] border-[var(--border)] text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)]"
              }`}
              onClick={() => setStatus(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {loading && (
          <div className="space-y-3" role="status">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-[104px] bg-muted/50 rounded-2xl border border-border animate-pulse" />
            ))}
          </div>
        )}

        {error && !loading && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive p-8 rounded-2xl text-center" role="alert">
            <p className="font-medium mb-4">{error}</p>
            <button type="button" className="doctor-primary-button" onClick={() => void load()}>
              Thử lại
            </button>
          </div>
        )}

        {!error && !loading && items.length === 0 && (
          <div className="bg-[var(--surface)] border border-[var(--border)] p-12 rounded-2xl flex flex-col items-center justify-center text-center shadow-sm">
            <h2 className="text-lg font-semibold text-foreground mb-2">Không có yêu cầu review xu hướng.</h2>
            <p className="text-muted-foreground max-w-sm">
              {status === "PENDING" ? "Hiện chưa có yêu cầu nào đang chờ xử lý." : "Bộ lọc hiện tại đang rỗng."}
            </p>
          </div>
        )}

        {!error && !loading && items.length > 0 && (
          <ul className="flex flex-col gap-3" aria-label={`Danh sách ${total} yêu cầu review xu hướng`}>
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/doctor/trend-reviews/${item.id}`}
                  className="group flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-sm hover:shadow-md hover:border-[var(--brand-soft)] transition-all duration-200 hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-base font-semibold text-foreground">{item.patient_name}</strong>
                      <span className="text-sm text-muted-foreground">· #{item.patient_id}</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {item.display_name} · {item.point_count} mốc xét nghiệm · {item.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"}
                    </div>
                    <div className="text-xs text-muted-foreground">Gửi lúc {formatMoment(item.requested_at)}</div>
                  </div>
                  <div className="flex items-center justify-between md:justify-end gap-3 border-t border-[var(--border)] md:border-t-0 pt-3 md:pt-0">
                    <span className="inline-flex items-center rounded-full bg-[var(--surface-subtle)] px-2.5 py-1 text-xs font-semibold text-[var(--foreground-secondary)]">
                      {statusText(item.status)}
                    </span>
                    <span className="text-sm font-medium text-[var(--brand)] opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                      Mở review ›
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
