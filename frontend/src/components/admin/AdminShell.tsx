"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getRole, getToken, getUsername } from "@/lib/api";
import { AppShell } from "@/components/common/LayoutPrimitives";
import { ShellLoadingState } from "@/components/common/SystemState";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";
import RouteTransition from "@/components/common/RouteTransition";

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
    return <ShellLoadingState label="Đang mở khu vực vận hành…" />;
  }

  return (
    <>
      <a href="#admin-main-content" className="skip-link">Bỏ qua điều hướng</a>
      <AppShell
        role="admin"
        tier="wide"
        sidebar={<AdminSidebar pathname={pathname} username={session.username} onLogout={logout} />}
        topbar={<AdminTopbar pathname={pathname} username={session.username} onLogout={logout} />}
        motionKey={pathname}
      >
        <RouteTransition variant="admin">{children}</RouteTransition>
      </AppShell>
    </>
  );
}
