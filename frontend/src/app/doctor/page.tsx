"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QueueRow from "@/components/doctor/QueueRow";
import QueueTabs from "@/components/doctor/QueueTabs";
import DoctorQueueOverview from "@/components/doctor/DoctorQueueOverview";
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import DoctorQueueToolbar from "@/components/doctor/DoctorQueueToolbar";
import DoctorStatePanel from "@/components/doctor/DoctorStatePanel";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
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
    <div className="doctor-worklist-page">
      <section className="doctor-worklist-page__content">
        <DoctorPageHeader
          eyebrow="Không gian lâm sàng"
          title="Hàng đợi đánh giá"
          description="Ưu tiên tín hiệu cần chú ý, theo dõi tiến độ và mở phiếu để kiểm chứng."
        />

        <DoctorQueueOverview counts={counts} />

        <section className="doctor-worklist-surface" aria-labelledby="doctor-worklist-title">
          <h2 id="doctor-worklist-title" className="sr-only">Danh sách phiếu cần đánh giá</h2>
          <DoctorQueueToolbar
            filters={<QueueTabs active={tab} counts={counts} onChange={changeTab} />}
            total={total}
            itemLabel="phiếu trong bộ lọc"
            contextLabel="Ưu tiên lâm sàng trước"
          />

          <div className="doctor-worklist-body" aria-live="polite">
            {loading && (
              <div className="doctor-worklist-skeleton" role="status" aria-label="Đang tải hàng đợi">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="doctor-worklist-skeleton__row">
                    <Skeleton className="doctor-worklist-skeleton__identity" />
                    <Skeleton className="doctor-worklist-skeleton__reason" />
                    <Skeleton className="doctor-worklist-skeleton__workflow" />
                  </div>
                ))}
              </div>
            )}

            {error && !loading && (
              <DoctorStatePanel
                kind="error"
                title="Không tải được dữ liệu hàng đợi"
                description={error}
                action={<Button type="button" variant="outline" onClick={() => void load(tab, page)}>Thử lại</Button>}
              />
            )}

            {!error && !loading && items.length === 0 && (
              <DoctorStatePanel
                kind="empty"
                title={isPendingDefault
                  ? hasVerified
                    ? "Không có phiếu nào đang chờ kiểm chứng"
                    : "Chưa có phiếu nào cần kiểm chứng"
                  : "Không có phiếu nào khớp bộ lọc này"}
                description={isPendingDefault
                  ? hasVerified
                    ? "Tất cả phiếu đã đi qua hàng đợi hiện đã được xử lý."
                    : "Hệ thống chưa tìm thấy phiếu có cờ cần bác sĩ xem."
                  : "Bộ lọc hiện tại đang rỗng."}
                action={!isPendingDefault
                  ? <Button type="button" variant="outline" onClick={() => changeTab("pending")}>Xem phiếu đang chờ</Button>
                  : undefined}
              />
            )}

            {!error && !loading && items.length > 0 && (
              <ul className="doctor-worklist-rows">
                {items.map((item, index) => (
                  <li
                    key={item.report_id}
                    className="motion-row-stagger"
                    style={{ "--stagger-index": index } as React.CSSProperties}
                  >
                    <QueueRow item={item} activeTab={tab} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {total > 0 && (
            <nav className="doctor-worklist-pagination" aria-label="Phân trang hàng đợi">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((current) => current - 1)}
              >
                ‹ Trước
              </button>
              <span>{rangeStart}-{rangeEnd} của {total}</span>
              <button
                type="button"
                disabled={rangeEnd >= total}
                onClick={() => setPage((current) => current + 1)}
              >
                Sau ›
              </button>
            </nav>
          )}
        </section>
      </section>
    </div>
  );
}
