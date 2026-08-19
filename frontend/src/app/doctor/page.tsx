"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QueueRow from "@/components/doctor/QueueRow";
import QueueTabs from "@/components/doctor/QueueTabs";
import DoctorQueueOverview from "@/components/doctor/DoctorQueueOverview";
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
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <section className="flex flex-col">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-foreground">Hàng đợi đánh giá</h1>
          <p className="text-muted-foreground mt-1">Xem và xử lý các báo cáo cần đánh giá.</p>
        </header>

        <DoctorQueueOverview counts={counts} />

        <QueueTabs active={tab} counts={counts} onChange={changeTab} />
        
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm font-medium text-muted-foreground">Sắp xếp theo mức ưu tiên</p>
        </div>

        <section aria-live="polite">
          {loading && (
            <div className="space-y-3" role="status">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="h-[120px] bg-muted/50 rounded-2xl border border-border animate-pulse motion-reduce:animate-none" />
              ))}
            </div>
          )}

          {error && !loading && (
            <div className="bg-destructive/10 border border-destructive/20 text-destructive p-8 rounded-2xl flex flex-col items-center justify-center text-center" role="alert">
              <p className="font-medium mb-4">Không tải được dữ liệu hàng đợi.</p>
              <button 
                type="button" 
                className="px-4 py-2 bg-destructive text-destructive-foreground rounded-xl text-sm font-medium hover:bg-destructive/90 transition-colors"
                onClick={() => void load(tab, page)}
              >
                Thử lại
              </button>
            </div>
          )}

          {!error && !loading && items.length === 0 && (
            <div className="bg-[var(--surface)] border border-[var(--border)] p-12 rounded-2xl flex flex-col items-center justify-center text-center shadow-sm">
              <div className="w-12 h-12 bg-[var(--surface-subtle)] border border-[var(--border)] rounded-full flex items-center justify-center mb-4 text-muted-foreground" aria-hidden="true">
                ✓
              </div>
              <h2 className="text-lg font-semibold text-foreground mb-2">
                {isPendingDefault
                  ? hasVerified
                    ? "Không có phiếu nào đang chờ kiểm chứng."
                    : "Chưa có phiếu nào cần kiểm chứng."
                  : "Không có phiếu nào khớp bộ lọc này."}
              </h2>
              <p className="text-muted-foreground max-w-sm mb-6">
                {isPendingDefault
                  ? hasVerified
                    ? "Tất cả phiếu đã đi qua hàng đợi hiện đã được xử lý."
                    : "Hệ thống chưa tìm thấy phiếu có cờ cần bác sĩ xem."
                  : "Bộ lọc hiện tại đang rỗng."}
              </p>
              {!isPendingDefault && (
                <button 
                  type="button" 
                  className="px-4 py-2 bg-[var(--brand)] text-primary-foreground rounded-xl text-sm font-medium hover:bg-[var(--brand-strong)] transition-colors"
                  onClick={() => changeTab("pending")}
                >
                  Xem tất cả phiếu đang chờ
                </button>
              )}
            </div>
          )}

          {!error && !loading && items.length > 0 && (
            <ul className="flex flex-col gap-3">
              {items.map((item) => (
                <li key={item.report_id}>
                  <QueueRow item={item} activeTab={tab} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {total > 0 && (
          <nav className="flex items-center justify-between mt-6 bg-[var(--surface)] border border-[var(--border)] p-2 rounded-xl shadow-sm" aria-label="Phân trang hàng đợi">
            <button 
              type="button" 
              className="px-4 py-2 text-sm font-medium rounded-lg text-foreground hover:bg-[var(--surface-subtle)] transition-colors disabled:opacity-50 disabled:hover:bg-transparent"
              disabled={page <= 1} 
              onClick={() => setPage((current) => current - 1)}
            >
              ‹ Trước
            </button>
            <span className="text-sm text-muted-foreground font-medium">{rangeStart}-{rangeEnd} của {total}</span>
            <button 
              type="button" 
              className="px-4 py-2 text-sm font-medium rounded-lg text-foreground hover:bg-[var(--surface-subtle)] transition-colors disabled:opacity-50 disabled:hover:bg-transparent"
              disabled={rangeEnd >= total} 
              onClick={() => setPage((current) => current + 1)}
            >
              Sau ›
            </button>
          </nav>
        )}
      </section>
    </div>
  );
}
