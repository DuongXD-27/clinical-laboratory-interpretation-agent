"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getRole, getToken, getUsername, type Role } from "@/lib/api";
import PatientSidebar from "./PatientSidebar";
import PatientTopbar from "./PatientTopbar";

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
    <div className="flex flex-col lg:flex-row min-h-dvh bg-[var(--background)] text-foreground">
      <a href="#patient-main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 z-50 bg-background p-4 rounded-md shadow-md">
        Bỏ qua điều hướng
      </a>

      <PatientSidebar 
        pathname={pathname}
        isGuest={isGuest}
        username={session.username}
        onLogout={logout}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <PatientTopbar 
          pathname={pathname}
          isGuest={isGuest}
          username={session.username}
          onLogout={logout}
        />
        
        <main id="patient-main-content" className="flex-1 p-4 lg:p-8" tabIndex={-1}>
          <div className="mx-auto max-w-6xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
