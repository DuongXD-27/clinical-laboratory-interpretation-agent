"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QueueRow from "@/components/doctor/QueueRow";
import QueueTabs from "@/components/doctor/QueueTabs";
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
    <div className="doctor-portal">
      <section className="doctor-queue-shell">
        <header className="doctor-queue-header">
          <div>
            <h1>Hàng đợi kiểm chứng</h1>
            <p>{counts?.pending ?? 0} phiếu đang chờ</p>
          </div>
        </header>

        <QueueTabs active={tab} counts={counts} onChange={changeTab} />
        <p className="doctor-sort-note">Sắp xếp theo mức ưu tiên</p>

        <section className="doctor-queue-list" aria-live="polite">
          {loading && (
            <div className="doctor-skeleton-list" role="status">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="skeleton-row" />
              ))}
            </div>
          )}

          {error && !loading && (
            <div className="doctor-error-state" role="alert">
              <p>Không tải được hàng đợi.</p>
              <button type="button" onClick={() => void load(tab, page)}>Thử lại</button>
            </div>
          )}

          {!error && !loading && items.length === 0 && (
            <div className="doctor-empty-state">
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
            <ul className="doctor-queue-items">
              {items.map((item) => (
                <li key={item.report_id}>
                  <QueueRow item={item} activeTab={tab} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {total > 0 && (
          <nav className="doctor-queue-pagination" aria-label="Phân trang hàng đợi">
            <button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
              ‹ Trước
            </button>
            <span>{rangeStart}-{rangeEnd} của {total}</span>
            <button type="button" disabled={rangeEnd >= total} onClick={() => setPage((current) => current + 1)}>
              Sau ›
            </button>
          </nav>
        )}
      </section>
    </div>
  );
}
