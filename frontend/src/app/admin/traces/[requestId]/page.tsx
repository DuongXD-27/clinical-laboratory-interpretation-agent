"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { ForbiddenError, UnauthorizedError, clearSession, fetchTrace } from "@/lib/api";
import { splitTimings, timingLabel } from "@/lib/serverTiming.mjs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RequestTrace } from "@/types/admin";

function formatMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  if (value < 1) return `${value.toFixed(2)}ms`;
  return `${Math.round(value)}ms`;
}

function formatMoment(iso: string): string {
  // Backend trả giờ UTC không kèm hậu tố Z; thiếu nó thì trình duyệt hiểu là
  // giờ địa phương và mốc lệch đi đúng bằng offset múi giờ.
  const parsed = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("vi-VN", { hour12: false });
}

function statusVariant(status: number): "success" | "warning" | "destructive" {
  if (status >= 500) return "destructive";
  if (status >= 400) return "warning";
  return "success";
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <span className="block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <strong className="mt-1 block text-lg font-semibold tabular-nums leading-none">{value}</strong>
      {hint ? <span className="mt-1 block text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

export default function AdminTraceDetailPage() {
  const params = useParams<{ requestId: string }>();
  const router = useRouter();
  const requestId = params.requestId;

  const [trace, setTrace] = useState<RequestTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTrace(await fetchTrace(requestId));
    } catch (err) {
      if (err instanceof UnauthorizedError || err instanceof ForbiddenError) {
        clearSession();
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Không mở được trace");
    } finally {
      setLoading(false);
    }
  }, [requestId, router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở trang, không phải đồng bộ state
    void load();
  }, [load]);

  const { totals, stages, slowest } = splitTimings(trace?.server_timing ?? null);
  const httpTotal = totals.find((t) => t.name === "http-total");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/admin"
            className="mb-1 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--brand-strong)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Về danh sách trace
          </Link>
          <h2 className="m-0 text-xl font-semibold tracking-tight lg:text-2xl">Chi tiết request</h2>
          <code className="mt-1 block truncate font-mono text-xs text-muted-foreground">{requestId}</code>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} aria-hidden="true" />
          {loading ? "Đang tải..." : "Làm mới"}
        </Button>
      </div>

      {error ? (
        <Card className="border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] py-3">
          <CardContent className="px-4 text-sm text-[var(--status-critical-fg)]" role="alert">
            {error}
          </CardContent>
        </Card>
      ) : null}

      {trace ? (
        <>
          <Card className="py-4">
            <CardContent className="grid grid-cols-2 gap-5 px-4 sm:grid-cols-3 xl:grid-cols-6">
              <div>
                <span className="block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Kết quả
                </span>
                <Badge variant={statusVariant(trace.status_code)} className="mt-1.5 tabular-nums">
                  {trace.status_code}
                </Badge>
              </div>
              <Stat label="Thời lượng" value={formatMs(trace.duration_ms)} hint="toàn bộ request" />
              <Stat
                label="Truy vấn CSDL"
                value={String(trace.db_query_count)}
                hint={`${formatMs(trace.db_ms)} cộng dồn`}
              />
              <Stat
                label="Gọi LLM"
                value={String(trace.llm_call_count)}
                hint={trace.llm_call_count > 0 ? `${formatMs(trace.llm_ms)} cộng dồn` : "không gọi"}
              />
              <Stat label="Vai trò" value={trace.user_role ?? "—"} hint="không lưu danh tính" />
              <Stat label="Thời điểm" value={formatMoment(trace.created_at).split(" ")[0]} hint={formatMoment(trace.created_at).split(" ").slice(1).join(" ")} />
            </CardContent>
          </Card>

          <Card className="py-4">
            <CardContent className="px-4">
              <span className="font-mono text-[11px] font-semibold tracking-wide text-muted-foreground">
                {trace.method}
              </span>
              <div className="break-all font-mono text-sm text-foreground">{trace.path}</div>
            </CardContent>
          </Card>

          {trace.llm_error_count > 0 ? (
            <Card className="border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] py-3">
              <CardContent className="px-4 text-sm text-[var(--status-critical-fg)]">
                <strong>{trace.llm_error_count} lời gọi LLM lỗi</strong> trong request này. Response vẫn trả{" "}
                {trace.status_code}, nhưng nội dung đã rơi về bản dựng sẵn — người dùng nhận được câu trả lời
                kém hơn mà không có dấu hiệu nào báo lỗi.
              </CardContent>
            </Card>
          ) : null}

          <Card className="py-4">
            <CardContent className="px-4">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="m-0 text-sm font-semibold">Thời gian tiêu ở đâu</h3>
                {httpTotal ? (
                  <span className="text-xs tabular-nums text-muted-foreground">
                    Tổng {formatMs(httpTotal.durationMs)}
                  </span>
                ) : null}
              </div>

              {stages.length === 0 ? (
                <p className="m-0 py-6 text-center text-sm text-muted-foreground">
                  Request này không ghi chặng nào. Các đường như <code className="font-mono">/auth/*</code> chỉ
                  có một bước nên không có gì để phân rã.
                </p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {stages.map((stage) => {
                    const share = slowest > 0 ? Math.max(2, Math.round((stage.durationMs / slowest) * 100)) : 0;
                    // Chặng chiếm quá nửa tổng thời gian là thủ phạm rõ ràng.
                    const dominant = httpTotal ? stage.durationMs / httpTotal.durationMs >= 0.5 : false;
                    return (
                      <li key={stage.name} className="flex items-center gap-3">
                        <span className="w-52 shrink-0 truncate text-sm" title={stage.name}>
                          {timingLabel(stage.name)}
                          {stage.isAccumulated ? (
                            <span className="ml-1 text-[11px] text-muted-foreground">(cộng dồn)</span>
                          ) : null}
                        </span>
                        <span className="relative h-6 flex-1 overflow-hidden rounded bg-[var(--surface-subtle)]">
                          <span
                            className={cn(
                              "absolute inset-y-0 left-0 rounded",
                              dominant ? "bg-[var(--status-abnormal-bg)]" : "bg-[var(--brand-soft)]",
                            )}
                            style={{ width: `${share}%` }}
                            aria-hidden="true"
                          />
                        </span>
                        <span
                          className={cn(
                            "w-20 shrink-0 text-right text-sm tabular-nums",
                            dominant ? "font-semibold text-[var(--status-abnormal-fg)]" : "text-foreground",
                          )}
                        >
                          {formatMs(stage.durationMs)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}

              {/* Vì sao không cộng các chặng lại thành tổng: `http-total` bao trọn
                  cả request kể cả phần ngoài graph, và `analysis-graph-total` bao
                  trọn các node. Cộng chúng vào là đếm hai lần. */}
              {totals.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-[var(--border)] pt-3 text-xs text-muted-foreground">
                  {totals.map((total) => (
                    <span key={total.name}>
                      {timingLabel(total.name)}{" "}
                      <strong className="font-medium tabular-nums text-foreground">
                        {formatMs(total.durationMs)}
                      </strong>
                    </span>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </>
      ) : !loading && !error ? (
        <Card className="py-10">
          <CardContent className="px-4 text-center text-sm text-muted-foreground">
            Không tìm thấy trace này. Trace chỉ được giữ trong một số ngày giới hạn.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
