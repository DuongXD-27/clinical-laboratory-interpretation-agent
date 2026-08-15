"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import { clearSession, getRole, getToken } from "@/lib/api";

export default function PatientHistoryPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- auth guard localStorage chỉ chạy được phía client.
    setCheckingAuth(false);
  }, [router]);

  if (checkingAuth) return null;

  return (
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div>
            <h1>Lịch sử xét nghiệm</h1>
            <p>Danh sách các phiếu xét nghiệm đã xác nhận và lưu thành công.</p>
          </div>
          <Link href="/patient" className="secondary-button px-3 py-2.5">Tổng quan</Link>
        </header>

        <div className="mt-6">
          <HistoryPanel
            mode="patient"
            pageSize={10}
            onUnauthorized={() => {
              clearSession();
              router.replace("/login");
            }}
          />
        </div>
      </div>
    </main>
  );
}
