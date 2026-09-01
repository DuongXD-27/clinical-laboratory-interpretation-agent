"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandLockup } from "@/components/common/BrandSignature";
import { doctorNavigation, isNavActive } from "./DoctorSidebar";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";

interface DoctorTopbarProps {
  pathname: string;
  username: string | null;
  onLogout: () => void;
}

function pageTitle(pathname: string) {
  if (pathname.startsWith("/doctor/trend-reviews")) return "Đánh giá xu hướng";
  if (pathname.startsWith("/doctor/reports/")) return "Chi tiết kết quả";
  return "Hàng đợi đánh giá";
}

export default function DoctorTopbar({ pathname, username, onLogout }: DoctorTopbarProps) {
  const [open, setOpen] = useState(false);

  return (
    <header className="role-topbar doctor-topbar">
      <div className="doctor-topbar__primary">
        {/* Mobile Hamburger Menu */}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger className="doctor-topbar__menu lg:hidden" aria-label="Mở menu">
            <Menu className="size-5" aria-hidden="true" />
          </SheetTrigger>
          <SheetContent side="left" className="w-[280px] p-0 flex flex-col bg-[var(--surface)]">
            <SheetHeader className="h-16 flex items-center justify-center border-b border-[var(--border)] px-4">
              <SheetTitle className="w-full text-left">
                <BrandLockup context="Không gian bác sĩ" />
              </SheetTitle>
              <SheetDescription className="sr-only">Menu điều hướng lâm sàng</SheetDescription>
            </SheetHeader>
            <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-4 py-6" aria-label="Điều hướng trên di động">
              {doctorNavigation.map((item) => {
                const active = isNavActive(pathname, item);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    transitionTypes={["nav-route"]}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setOpen(false)}
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
            <div className="p-4 border-t border-[var(--border)]">
              <div className="flex items-center gap-3 px-2 mb-4">
                <div className="w-8 h-8 rounded-full bg-[var(--brand-soft)] text-[var(--brand-strong)] flex items-center justify-center font-bold text-sm shrink-0" aria-hidden="true">
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
                onClick={() => {
                  setOpen(false);
                  onLogout();
                }}
                className="doctor-navigation-logout"
              >
                <LogOut data-icon="inline-start" className="size-4 shrink-0" aria-hidden="true" />
                Đăng xuất
              </button>
            </div>
          </SheetContent>
        </Sheet>
        
        {/* Page Title */}
        <div className="doctor-topbar__title">
          <span>Khu vực bác sĩ</span>
          <strong>{pageTitle(pathname)}</strong>
        </div>
      </div>
      
      {/* Desktop Greeting & Mobile Avatar */}
      <div className="doctor-topbar__account">
        <p className="hidden lg:block">
          BS. <strong>{username || "Đồng nghiệp"}</strong>
        </p>
        <div className="lg:hidden w-8 h-8 rounded-full bg-[var(--brand-soft)] text-[var(--brand-strong)] flex items-center justify-center font-bold text-sm shrink-0" aria-hidden="true">
          {(username || "D").slice(0, 1).toUpperCase()}
        </div>
      </div>
    </header>
  );
}
