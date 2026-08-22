"use client";

import Link from "next/link";
import { LayoutDashboard, FileSearch, History, TrendingUp, UserRound, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

export const patientNavigation = [
  { href: "/patient", label: "Tổng quan", icon: LayoutDashboard, exact: true, patientOnly: false },
  { href: "/patient/analysis", label: "Phân tích xét nghiệm", icon: FileSearch, exact: false, patientOnly: false },
  { href: "/patient/history", label: "Lịch sử kết quả", icon: History, exact: false, patientOnly: true },
  { href: "/patient/trends", label: "Xu hướng chỉ số", icon: TrendingUp, exact: false, patientOnly: true },
  { href: "/patient/profile", label: "Thông tin cá nhân", icon: UserRound, exact: false, patientOnly: true },
];

export function isNavActive(pathname: string, item: (typeof patientNavigation)[number]) {
  if (item.exact) return pathname === item.href;
  if (item.href === "/patient/history") {
    return pathname.startsWith(item.href) || pathname.startsWith("/patient/reports/");
  }
  return pathname.startsWith(item.href);
}

interface PatientSidebarProps {
  pathname: string;
  isGuest: boolean;
  username: string | null;
  onLogout: () => void;
}

export default function PatientSidebar({ pathname, isGuest, username, onLogout }: PatientSidebarProps) {
  const visibleNavigation = patientNavigation.filter((item) => !item.patientOnly || !isGuest);

  return (
    <aside className="hidden lg:flex flex-col w-64 shrink-0 bg-[var(--glass-surface)] backdrop-blur-xl border-r border-[var(--glass-border)] shadow-[4px_0_24px_rgba(0,0,0,0.02),inset_0_1px_1px_rgba(255,255,255,0.7)] sticky top-0 h-dvh z-40 relative">
      {/* Subtle background refraction / edge highlight */}
      <div className="absolute inset-0 pointer-events-none shadow-[inset_1px_1px_0_rgba(255,255,255,0.4)] mix-blend-overlay" aria-hidden="true" />
      {/* Brand */}
      <div className="h-16 flex items-center px-6 border-b border-[var(--glass-border)]/50 shrink-0">
        <div className="flex flex-col">
          <span className="font-semibold text-base text-[var(--brand-strong)]">VMEC</span>
          <span className="text-xs text-muted-foreground">Không gian bệnh nhân</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-1" aria-label="Điều hướng chính">
        {visibleNavigation.map((item) => {
          const active = isNavActive(pathname, item);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex items-center gap-3 px-3 py-2 rounded-2xl text-sm font-medium transition-colors relative",
                active 
                  ? "bg-[var(--glass-surface)] backdrop-blur-md text-[var(--brand-strong)] shadow-[0_4px_16px_rgba(0,0,0,0.04),inset_0_1px_1px_rgba(255,255,255,0.8)] border border-[var(--holo-cyan)]/30" 
                  : "text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)] hover:text-foreground"
              )}
            >
              {active && (
                <div 
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-[var(--brand)] rounded-r-full shadow-[0_0_12px_var(--holo-cyan)]" 
                  aria-hidden="true" 
                />
              )}
              <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer / User */}
      <div className="p-4 border-t border-[var(--glass-border)]/50 shrink-0">
        <div className="flex items-center gap-3 px-2 mb-4">
          <div className="w-8 h-8 rounded-full bg-[var(--brand-soft)] text-[var(--brand-strong)] flex items-center justify-center font-bold text-sm shrink-0" aria-hidden="true">
            {(username || "B").slice(0, 1).toUpperCase()}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate text-foreground">
              {isGuest ? "Phiên dùng thử" : username || "Bệnh nhân"}
            </span>
            <span className="text-xs text-muted-foreground truncate">
              {isGuest ? "Dữ liệu không được lưu" : "Tài khoản bệnh nhân"}
            </span>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-[var(--status-critical-fg)] hover:bg-[var(--status-critical-bg)] rounded-lg transition-colors font-medium"
        >
          <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
          {isGuest ? "Thoát phiên khách" : "Đăng xuất"}
        </button>
      </div>
    </aside>
  );
}
