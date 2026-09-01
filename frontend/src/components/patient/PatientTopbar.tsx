"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandLockup } from "@/components/common/BrandSignature";
import { patientNavigation, isNavActive } from "./PatientSidebar";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";

interface PatientTopbarProps {
  pathname: string;
  isGuest: boolean;
  username: string | null;
  onLogout: () => void;
}

import { getPatientPageTitle } from "@/lib/patientRoutes.mjs";

const pageTitle = getPatientPageTitle;

export default function PatientTopbar({ pathname, isGuest, username, onLogout }: PatientTopbarProps) {
  const [open, setOpen] = useState(false);
  const visibleNavigation = patientNavigation.filter((item) => !item.patientOnly || !isGuest);

  return (
    <header className="role-topbar">
      {/* Subtle background refraction / edge highlight */}
      <div className="absolute inset-0 pointer-events-none shadow-[inset_1px_1px_0_rgba(255,255,255,0.4)] mix-blend-overlay" aria-hidden="true" />
      
      <div className="flex items-center gap-3 relative z-10">
        {/* Mobile Hamburger Menu */}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger className="lg:hidden p-2 -ml-2 text-[var(--foreground)] hover:bg-[var(--surface-subtle)] rounded-md transition-colors" aria-label="Mở menu">
            <Menu className="size-5" aria-hidden="true" />
          </SheetTrigger>
          <SheetContent side="left" className="w-[280px] p-0 flex flex-col bg-[var(--surface)]">
            <SheetHeader className="h-16 flex items-center justify-center border-b border-[var(--border)] px-4">
              <SheetTitle className="w-full text-left">
                <BrandLockup context="Không gian bệnh nhân" />
              </SheetTitle>
              <SheetDescription className="sr-only">Menu điều hướng bệnh nhân</SheetDescription>
            </SheetHeader>
            <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-1" aria-label="Điều hướng trên di động">
              {visibleNavigation.map((item) => {
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
                      "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors relative",
                      "outline-none focus-visible:ring-2 focus-visible:ring-[var(--holo-cyan)]/60",
                      active
                        ? "bg-[var(--brand-soft)] text-[var(--brand-strong)]" 
                        : "text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)] hover:text-foreground"
                    )}
                  >
                    {active && (
                      <div className="absolute left-0 top-2 bottom-2 w-1 bg-[var(--brand)] rounded-r-md shadow-[0_0_8px_var(--holo-cyan)]" aria-hidden="true" />
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
                onClick={() => {
                  setOpen(false);
                  onLogout();
                }}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-[var(--status-critical-fg)] hover:bg-[var(--status-critical-bg)] rounded-lg transition-colors font-medium"
              >
                <LogOut data-icon="inline-start" className="size-4 shrink-0" aria-hidden="true" />
                {isGuest ? "Thoát phiên khách" : "Đăng xuất"}
              </button>
            </div>
          </SheetContent>
        </Sheet>
        
        {/* Contextual location label — the page's own <h1> remains the document heading */}
        <div className="flex flex-col min-w-0">
          <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Khu vực bệnh nhân</span>
          <p className="font-semibold text-sm lg:text-base truncate m-0 leading-none">{pageTitle(pathname)}</p>
        </div>
      </div>
      
      {/* Desktop Greeting & Mobile Avatar */}
      <div className="flex items-center gap-3">
        <p className="hidden lg:block text-sm text-muted-foreground m-0">
          Xin chào, <strong className="text-foreground font-medium">{isGuest ? "bạn đang dùng thử" : username || "bạn"}</strong>
        </p>
        <div className="lg:hidden w-8 h-8 rounded-full bg-[var(--brand-soft)] text-[var(--brand-strong)] flex items-center justify-center font-bold text-sm shrink-0" aria-hidden="true">
          {(username || "B").slice(0, 1).toUpperCase()}
        </div>
      </div>
    </header>
  );
}
