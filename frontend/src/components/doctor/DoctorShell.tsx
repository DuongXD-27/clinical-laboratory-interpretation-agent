"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getRole, getToken, getUsername } from "@/lib/api";
import DoctorSidebar from "./DoctorSidebar";
import DoctorTopbar from "./DoctorTopbar";

export default function DoctorShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<{ username: string | null } | null>(null);

  useEffect(() => {
    const role = getRole();
    if (!getToken() || role !== "doctor") {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- session storage is client-only.
    setSession({ username: getUsername() });
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/");
  }

  if (!session) {
    return (
      <main className="flex items-center justify-center min-h-dvh bg-[var(--background)]">
        <div className="text-muted-foreground animate-pulse" role="status">Đang mở khu vực bác sĩ...</div>
      </main>
    );
  }

  return (
    <div className="doctor-app-shell flex flex-col lg:flex-row min-h-dvh bg-[var(--background)] text-foreground relative">
      <div className="doctor-atmosphere fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="doctor-atmosphere__cyan" />
        <div className="doctor-atmosphere__blue" />
        <div className="doctor-atmosphere__violet" />
      </div>
      <a href="#doctor-main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 z-50 bg-background p-4 rounded-md shadow-md">
        Bỏ qua điều hướng
      </a>

      <DoctorSidebar 
        pathname={pathname}
        username={session.username}
        onLogout={logout}
      />

      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <DoctorTopbar 
          pathname={pathname}
          username={session.username}
          onLogout={logout}
        />
        
        <main id="doctor-main-content" className="flex-1 p-4 lg:p-8 w-full max-w-full" tabIndex={-1}>
          <div className="doctor-shell-content mx-auto w-full max-w-7xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
