"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QueueRow from "@/components/doctor/QueueRow";
import QueueTabs from "@/components/doctor/QueueTabs";
import DoctorQueueOverview from "@/components/doctor/DoctorQueueOverview";
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, ChevronLeft, ChevronRight, SlidersHorizontal } from "lucide-react";
import {
  fetchDoctorQueue,
  getRole,
  getToken,
  type DoctorQueueTab,
} from "@/lib/api";
import type { DoctorQueueCounts, DoctorQueueItem } from "@/types/doctor";

const PAGE_SIZE = 20;
const VALID_TABS = new Set<DoctorQueueTab>(["pending", "critical", "ocr", "questions", "verified"]);

export default function DoctorPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [tab, setTab] = useState<DoctorQueueTab>("pending");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<DoctorQueueItem[]>([]);
  const [counts, setCounts] = useState<DoctorQueueCounts | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "doctor") {
      router.replace("/");
      return;
    }
    const queryTab = new URLSearchParams(window.location.search).get("tab") as DoctorQueueTab | null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- URL/localStorage only exist after mount in this client page.
    if (queryTab && VALID_TABS.has(queryTab)) setTab(queryTab);
    setCheckingAuth(false);
  }, [router]);

  const load = useCallback(async (nextTab = tab, nextPage = page) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDoctorQueue(nextTab, nextPage, PAGE_SIZE);
      setItems(data.items);
      setCounts(data.counts);
      setTotal(data.total);
      setPage(data.page);
    } catch (caught) {
      setItems([]);
      setTotal(0);
      setError(caught instanceof Error ? caught.message : "Không tải được hàng đợi.");
    } finally {
      setLoading(false);
    }
  }, [page, tab]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on active tab/page change.
    if (!checkingAuth) void load(tab, page);
  }, [checkingAuth, load, page, tab]);

  function changeTab(nextTab: DoctorQueueTab) {
    setTab(nextTab);
    setPage(1);
    window.history.replaceState(null, "", `/doctor?tab=${nextTab}`);
  }

  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(total, page * PAGE_SIZE);
  const isPendingDefault = tab === "pending";
  const hasVerified = (counts?.verified ?? 0) > 0;

  if (checkingAuth) return null;

  return (
    <div className="doctor-page doctor-queue-page">
      <DoctorPageHeader
        eyebrow="Không gian bác sĩ"
        title="Hàng đợi đánh giá"
        description="Ưu tiên các phiếu cần xác minh lâm sàng, kiểm tra OCR và phản hồi bệnh nhân."
      />

      <section className="doctor-page-section" aria-label="Tổng quan hàng đợi">

        <DoctorQueueOverview counts={counts} />
      </section>

      <section className="doctor-page-section doctor-queue-workspace" aria-label="Danh sách phiếu cần đánh giá">
        <QueueTabs active={tab} counts={counts} onChange={changeTab} />

        <div className="doctor-list-toolbar">
          <p><SlidersHorizontal aria-hidden="true" /> Sắp xếp theo mức ưu tiên lâm sàng</p>
          {!loading && total > 0 && <span>{total} phiếu</span>}
        </div>

        <section aria-live="polite">
          {loading && (
            <div className="doctor-skeleton-stack" role="status" aria-label="Đang tải hàng đợi">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="doctor-queue-skeleton" />
              ))}
            </div>
          )}

          {error && !loading && (
            <div className="doctor-state-card doctor-state-card--error" role="alert">
              <p>Không tải được dữ liệu hàng đợi.</p>
              <Button type="button" variant="outline" onClick={() => void load(tab, page)}>
                Thử lại
              </Button>
            </div>
          )}

          {!error && !loading && items.length === 0 && (
            <div className="doctor-state-card">
              <span className="doctor-state-card__icon" aria-hidden="true"><CheckCircle2 /></span>
              <h2>
                {isPendingDefault
                  ? hasVerified
                    ? "Không có phiếu nào đang chờ kiểm chứng."
                    : "Chưa có phiếu nào cần kiểm chứng."
                  : "Không có phiếu nào khớp bộ lọc này."}
              </h2>
              <p>
                {isPendingDefault
                  ? hasVerified
                    ? "Tất cả phiếu đã đi qua hàng đợi hiện đã được xử lý."
                    : "Hệ thống chưa tìm thấy phiếu có cờ cần bác sĩ xem."
                  : "Bộ lọc hiện tại đang rỗng."}
              </p>
              {!isPendingDefault && (
                <Button type="button" onClick={() => changeTab("pending")}>
                  Xem tất cả phiếu đang chờ
                </Button>
              )}
            </div>
          )}

          {!error && !loading && items.length > 0 && (
            <ul className="doctor-queue-cards">
              {items.map((item) => (
                <li key={item.report_id}>
                  <QueueRow item={item} activeTab={tab} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {total > 0 && (
          <nav className="doctor-pagination" aria-label="Phân trang hàng đợi">
            <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
              <ChevronLeft data-icon="inline-start" aria-hidden="true" /> Trước
            </Button>
            <span>{rangeStart}-{rangeEnd} của {total}</span>
            <Button type="button" variant="ghost" disabled={rangeEnd >= total} onClick={() => setPage((current) => current + 1)}>
              Sau <ChevronRight data-icon="inline-end" aria-hidden="true" />
            </Button>
          </nav>
        )}
      </section>
    </div>
  );
}
