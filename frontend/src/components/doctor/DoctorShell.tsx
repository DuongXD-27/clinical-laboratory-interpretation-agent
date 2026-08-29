"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell } from "@/components/common/LayoutPrimitives";
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
      <main className="flex min-h-dvh items-center justify-center bg-[var(--background)]">
        <div className="text-muted-foreground animate-pulse" role="status">Đang mở khu vực bác sĩ...</div>
      </main>
    );
  }

  return (
    <>
      <a href="#doctor-main-content" className="skip-link">Bỏ qua điều hướng</a>
      <AppShell
        role="doctor"
        tier="wide"
        sidebar={<DoctorSidebar pathname={pathname} username={session.username} onLogout={logout} />}
        topbar={<DoctorTopbar pathname={pathname} username={session.username} onLogout={logout} />}
      >
        {children}
      </AppShell>
    </>
  );
}
