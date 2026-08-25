"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QueueRow from "@/components/doctor/QueueRow";
import QueueTabs from "@/components/doctor/QueueTabs";
import DoctorQueueOverview from "@/components/doctor/DoctorQueueOverview";
import { Skeleton } from "@/components/ui/skeleton";
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
        <header className="page-section-heading doctor-worklist-heading">
          <div>
            <span className="doctor-worklist-heading__eyebrow">Không gian lâm sàng</span>
            <h1>Hàng đợi đánh giá</h1>
            <p>Ưu tiên tín hiệu cần chú ý, theo dõi tiến độ và mở phiếu để kiểm chứng.</p>
          </div>
        </header>

        <DoctorQueueOverview counts={counts} />

        <section className="doctor-worklist-surface" aria-labelledby="doctor-worklist-title">
          <h2 id="doctor-worklist-title" className="sr-only">Danh sách phiếu cần đánh giá</h2>
          <div className="doctor-worklist-surface__filters">
            <QueueTabs active={tab} counts={counts} onChange={changeTab} />
          </div>

          <div className="doctor-worklist-toolbar">
            <div>
              <strong>{total} phiếu</strong>
              <span>trong bộ lọc hiện tại</span>
            </div>
            <p>Sắp xếp theo mức ưu tiên</p>
          </div>

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
              <div className="doctor-worklist-message doctor-worklist-message--error" role="alert">
                <strong>Không tải được dữ liệu hàng đợi.</strong>
                <p>{error}</p>
                <button type="button" onClick={() => void load(tab, page)}>Thử lại</button>
              </div>
            )}

            {!error && !loading && items.length === 0 && (
              <div className="doctor-worklist-message doctor-worklist-message--empty">
                <span aria-hidden="true">✓</span>
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
                  <button type="button" onClick={() => changeTab("pending")}>
                    Xem tất cả phiếu đang chờ
                  </button>
                )}
              </div>
            )}

            {!error && !loading && items.length > 0 && (
              <ul className="doctor-worklist-rows">
                {items.map((item) => (
                  <li key={item.report_id}>
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
