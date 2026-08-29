"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell } from "@/components/common/LayoutPrimitives";
import AssistantWidget from "@/components/patient/AssistantWidget";
import { clearSession, getRole, getToken, getUsername, type Role } from "@/lib/api";
import PatientSidebar from "./PatientSidebar";
import PatientTopbar from "./PatientTopbar";

const WIDE_CONTENT_ROUTES = ["/patient/analysis", "/patient/history", "/patient/reports/", "/patient/trends"];

function isWideContentRoute(pathname: string): boolean {
  return WIDE_CONTENT_ROUTES.some(
    (route) => pathname.startsWith(route) || pathname === route.replace(/\/$/, ""),
  );
}

export default function PatientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
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
      <main className="flex min-h-dvh items-center justify-center bg-[var(--background)]">
        <div className="text-muted-foreground animate-pulse" role="status">Đang mở khu vực bệnh nhân...</div>
      </main>
    );
  }

  const isGuest = session.role === "guest";

  return (
    <>
      <a href="#patient-main-content" className="skip-link">Bỏ qua điều hướng</a>
      <AppShell
        role="patient"
        tier={isWideContentRoute(pathname) ? "wide" : "standard"}
        sidebar={<PatientSidebar pathname={pathname} isGuest={isGuest} username={session.username} onLogout={logout} />}
        topbar={<PatientTopbar pathname={pathname} isGuest={isGuest} username={session.username} onLogout={logout} />}
        floating={<AssistantWidget role={session.role} />}
      >
        <div key={pathname} className="page-transition-enter">{children}</div>
      </AppShell>
    </>
  );
}
