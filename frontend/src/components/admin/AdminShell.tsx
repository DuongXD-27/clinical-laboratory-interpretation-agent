"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getRole, getToken, getUsername } from "@/lib/api";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";

/** Khung khu vực vận hành, đối xứng với PatientShell và DoctorShell.
 *
 * Trước đây `/admin` không có layout nào nên nó trơ trọi giữa một sản phẩm mà
 * mọi khu vực khác đều có sidebar và topbar — nhìn vào không thấy đó là LumiLab.
 *
 * Guard ở đây CHỈ là điều hướng cho đỡ lạc, không phải phân quyền: `getRole()`
 * đọc localStorage, thứ ai cũng sửa được. Ranh giới thật là `require_roles()`
 * ở backend, và trang trace bên trong xoá phiên khi nhận 403.
 */
export default function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<{ username: string | null } | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "admin") {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- session storage is client-only.
    setSession({ username: getUsername() });
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/login");
  }

  if (!session) {
    return (
      <main className="flex items-center justify-center min-h-dvh bg-[var(--background)]">
        <div className="text-muted-foreground animate-pulse" role="status">
          Đang mở khu vực vận hành...
        </div>
      </main>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row min-h-dvh bg-[var(--background)] text-foreground">
      <a
        href="#admin-main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 z-50 bg-background p-4 rounded-md shadow-md"
      >
        Bỏ qua điều hướng
      </a>

      <AdminSidebar pathname={pathname} username={session.username} onLogout={logout} />

      <div className="flex-1 flex flex-col min-w-0">
        <AdminTopbar pathname={pathname} username={session.username} onLogout={logout} />

        <main id="admin-main-content" className="flex-1 p-4 lg:p-6 w-full max-w-full" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
