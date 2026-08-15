"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getRole, getToken, getUsername, type Role } from "@/lib/api";

const navigation = [
  { href: "/patient", label: "Tổng quan", icon: "⌂", exact: true, patientOnly: false },
  { href: "/patient/analysis", label: "Phân tích xét nghiệm", icon: "+", exact: false, patientOnly: false },
  { href: "/patient/history", label: "Lịch sử kết quả", icon: "↶", exact: false, patientOnly: true },
  { href: "/patient/trends", label: "Xu hướng chỉ số", icon: "↗", exact: false, patientOnly: true },
  { href: "/patient/profile", label: "Thông tin cá nhân", icon: "○", exact: false, patientOnly: true },
] as const;

function isActive(pathname: string, item: (typeof navigation)[number]) {
  if (item.exact) return pathname === item.href;
  if (item.href === "/patient/history") {
    return pathname.startsWith(item.href) || pathname.startsWith("/patient/reports/");
  }
  return pathname.startsWith(item.href);
}

function pageTitle(pathname: string) {
  if (pathname.startsWith("/patient/analysis")) return "Phân tích xét nghiệm";
  if (pathname.startsWith("/patient/reports/") || pathname.startsWith("/patient/history/")) return "Kết quả xét nghiệm";
  if (pathname.startsWith("/patient/history")) return "Lịch sử kết quả";
  if (pathname.startsWith("/patient/trends")) return "Xu hướng chỉ số";
  if (pathname.startsWith("/patient/profile")) return "Thông tin cá nhân";
  return "Tổng quan";
}

export default function PatientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [session, setSession] = useState<{ role: Role; username: string | null } | null>(null);

  useEffect(() => {
    const role = getRole();
    if (!getToken() || (role !== "patient" && role !== "guest")) {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- session storage is client-only and gates the shell.
    setSession({ role, username: getUsername() });
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/login");
  }

  if (!session) {
    return (
      <main className="patient-app-loading">
        <div className="loading-message" role="status">Đang mở khu vực bệnh nhân...</div>
      </main>
    );
  }

  const isGuest = session.role === "guest";
  const visibleNavigation = navigation.filter((item) => !item.patientOnly || !isGuest);

  return (
    <div className="patient-app-shell">
      <a href="#patient-main-content" className="skip-link">Bỏ qua điều hướng</a>
      <button
        type="button"
        className="patient-mobile-menu"
        aria-label="Mở điều hướng"
        aria-expanded={menuOpen}
        aria-controls="patient-sidebar"
        onClick={() => setMenuOpen(true)}
      >
        <span aria-hidden="true">☰</span>
        <span>Menu</span>
      </button>

      {menuOpen && (
        <button
          type="button"
          className="patient-sidebar-backdrop"
          aria-label="Đóng điều hướng"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside id="patient-sidebar" className={`patient-sidebar${menuOpen ? " is-open" : ""}`}>
        <div className="patient-sidebar-brand">
          <div className="brand-mark" aria-hidden="true">+</div>
          <div>
            <strong>Phân Tích Sức Khỏe AI</strong>
            <span>Không gian bệnh nhân</span>
          </div>
          <button type="button" className="patient-sidebar-close" aria-label="Đóng điều hướng" onClick={() => setMenuOpen(false)}>×</button>
        </div>

        <nav className="patient-navigation" aria-label="Điều hướng khu vực bệnh nhân">
          {visibleNavigation.map((item) => {
            const active = isActive(pathname, item);
            return (
              <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
                <span className="patient-nav-icon" aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
                {active && <span className="patient-nav-current" aria-hidden="true">•</span>}
              </Link>
            );
          })}
        </nav>

        <div className="patient-sidebar-footer">
          <div className="patient-user-summary">
            <span className="patient-avatar" aria-hidden="true">{(session.username || "B").slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{isGuest ? "Phiên dùng thử" : session.username || "Bệnh nhân"}</strong>
              <small>{isGuest ? "Dữ liệu không được lưu" : "Tài khoản bệnh nhân"}</small>
            </span>
          </div>
          <button type="button" className="patient-logout-button" onClick={logout}>
            <span aria-hidden="true">↪</span>
            {isGuest ? "Thoát phiên khách" : "Đăng xuất"}
          </button>
        </div>
      </aside>

      <div className="patient-app-content">
        <header className="patient-page-header">
          <div>
            <span className="patient-page-kicker">Khu vực bệnh nhân</span>
            <h1>{pageTitle(pathname)}</h1>
          </div>
          <p>Xin chào, <strong>{isGuest ? "bạn đang dùng thử" : session.username || "bạn"}</strong></p>
        </header>
        <main id="patient-main-content" className="patient-main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
