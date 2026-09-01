"use client";

import Link from "next/link";
import { ListTodo, LogOut, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandLockup } from "@/components/common/BrandSignature";

export const doctorNavigation = [
  { href: "/doctor", label: "Hàng đợi đánh giá", icon: ListTodo },
  { href: "/doctor/trend-reviews", label: "Đánh giá xu hướng", icon: TrendingUp },
];

export function isNavActive(pathname: string, item: (typeof doctorNavigation)[number]) {
  if (item.href === "/doctor") {
    return pathname === "/doctor" || pathname.startsWith("/doctor/reports/");
  }
  return pathname.startsWith(item.href);
}

interface DoctorSidebarProps {
  pathname: string;
  username: string | null;
  onLogout: () => void;
}

export default function DoctorSidebar({ pathname, username, onLogout }: DoctorSidebarProps) {
  return (
    <aside className="role-sidebar doctor-navigation-rail hidden lg:flex">
      {/* Brand */}
      <div className="doctor-navigation-rail__brand">
        <BrandLockup context="Không gian bác sĩ" />
      </div>

      {/* Navigation */}
      <nav className="doctor-navigation-rail__nav" aria-label="Điều hướng lâm sàng">
        {doctorNavigation.map((item) => {
          const active = isNavActive(pathname, item);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              transitionTypes={["nav-route"]}
              aria-current={active ? "page" : undefined}
              className={cn(
                "doctor-navigation-link group",
                active 
                  ? "bg-[var(--brand-soft)] text-[var(--brand-strong)]" 
                  : "text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)] hover:text-foreground"
              )}
            >
              {active && (
                <span className="doctor-navigation-link__indicator" aria-hidden="true" />
              )}
              <Icon data-icon="inline-start" className="size-5 shrink-0" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer / User */}
      <div className="doctor-navigation-rail__footer">
        <div className="doctor-navigation-user">
          <div className="doctor-navigation-user__avatar" aria-hidden="true">
            {(username || "D").slice(0, 1).toUpperCase()}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate text-foreground">
              {username || "Bác sĩ"}
            </span>
            <span className="text-xs text-muted-foreground truncate">
              Tài khoản bác sĩ
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="doctor-navigation-logout"
        >
          <LogOut data-icon="inline-start" className="size-4 shrink-0" aria-hidden="true" />
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}
