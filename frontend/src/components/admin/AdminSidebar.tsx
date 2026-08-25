"use client";

import Link from "next/link";
import { Activity, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

export const adminNavigation = [{ href: "/admin", label: "Trace hệ thống", icon: Activity }];

export function isNavActive(pathname: string, item: (typeof adminNavigation)[number]) {
  if (item.href === "/admin") return pathname === "/admin";
  return pathname.startsWith(item.href);
}

interface AdminSidebarProps {
  pathname: string;
  username: string | null;
  onLogout: () => void;
}

/** Điều hướng khu vực vận hành.
 *
 * Chỉ có đúng một mục, và vẫn giữ nguyên khung sidebar thay vì bỏ đi: người
 * dùng nhận ra mình vẫn ở trong LumiLab nhờ bố cục giống hai khu vực kia. Bỏ
 * sidebar để "đỡ thừa" là làm màn admin trông như một công cụ rời.
 */
export default function AdminSidebar({ pathname, username, onLogout }: AdminSidebarProps) {
  return (
    <aside className="hidden lg:flex flex-col w-64 shrink-0 bg-[var(--glass-surface)] backdrop-blur-md border-r border-[var(--glass-border)] sticky top-0 h-dvh z-40">
      <div className="h-16 flex items-center px-6 border-b border-[var(--glass-border)]/50 shrink-0">
        <div className="flex flex-col">
          <span className="font-semibold text-base text-[var(--brand-strong)]">LumiLab Operations</span>
          <span className="text-xs text-muted-foreground">Không gian vận hành</span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-1" aria-label="Điều hướng vận hành">
        {adminNavigation.map((item) => {
          const active = isNavActive(pathname, item);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors relative",
                active
                  ? "bg-[var(--brand-soft)] text-[var(--brand-strong)]"
                  : "text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)] hover:text-foreground",
              )}
            >
              {active && (
                <div
                  className="absolute left-0 top-2 bottom-2 w-1 bg-[var(--brand)] rounded-r-md shadow-[0_0_8px_var(--holo-cyan)]"
                  aria-hidden="true"
                />
              )}
              <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-[var(--glass-border)]/50 shrink-0">
        <div className="flex items-center gap-3 px-2 mb-4">
          <div
            className="w-8 h-8 rounded-full bg-[var(--brand-soft)] text-[var(--brand-strong)] flex items-center justify-center font-bold text-sm shrink-0"
            aria-hidden="true"
          >
            {(username || "A").slice(0, 1).toUpperCase()}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate text-foreground">{username || "Quản trị"}</span>
            <span className="text-xs text-muted-foreground truncate">Tài khoản quản trị</span>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-[var(--status-critical-fg)] hover:bg-[var(--status-critical-bg)] rounded-lg transition-colors font-medium"
        >
          <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}
