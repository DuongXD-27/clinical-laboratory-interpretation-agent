"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import AssistantWidget from "@/components/patient/AssistantWidget";
import { clearSession, getRole, getToken, getUsername, type Role } from "@/lib/api";
import PatientSidebar from "./PatientSidebar";
import PatientTopbar from "./PatientTopbar";

/**
 * WIDE pages (analysis / history / reports / trends) get a broader content
 * column; everything else stays on the calm STANDARD reading width. Pages must
 * not set their own max-width — the shell is the single source of truth.
 */
const WIDE_CONTENT_ROUTES = [
  "/patient/analysis",
  "/patient/history",
  "/patient/reports/",
  "/patient/trends",
];

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
      <main className="flex items-center justify-center min-h-dvh bg-[var(--background)]">
        <div className="text-muted-foreground animate-pulse" role="status">Đang mở khu vực bệnh nhân...</div>
      </main>
    );
  }

  const isGuest = session.role === "guest";

  return (
    <div className="flex flex-col lg:flex-row min-h-dvh bg-[var(--background)] text-foreground relative">
      {/* Decorative Atmospheric Background */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" aria-hidden="true">
        <div className="absolute top-[-15%] left-[-5%] w-[50vw] h-[50vh] rounded-full bg-[var(--holo-cyan)]/40 blur-[120px] opacity-60" />
        <div className="absolute top-[10%] right-[-10%] w-[40vw] h-[60vh] rounded-full bg-[var(--holo-blue)]/30 blur-[120px] opacity-50" />
        <div className="absolute bottom-[-10%] left-[10%] w-[60vw] h-[40vh] rounded-full bg-[var(--holo-violet)]/20 blur-[120px] opacity-40" />
      </div>

      <a href="#patient-main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 z-50 bg-background p-4 rounded-md shadow-md relative">
        Bỏ qua điều hướng
      </a>

      <PatientSidebar 
        pathname={pathname}
        isGuest={isGuest}
        username={session.username}
        onLogout={logout}
      />

      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <PatientTopbar 
          pathname={pathname}
          isGuest={isGuest}
          username={session.username}
          onLogout={logout}
        />
        
        <main id="patient-main-content" className="min-w-0 w-full flex-1 p-4 lg:p-8" tabIndex={-1}>
          <div
            key={pathname}
            className={`min-w-0 w-full page-transition-enter ${
              isWideContentRoute(pathname) ? "max-w-7xl" : "max-w-6xl"
            }`}
          >
            {children}
          </div>
        </main>
      </div>
      <AssistantWidget role={session.role} />
    </div>
  );
}
