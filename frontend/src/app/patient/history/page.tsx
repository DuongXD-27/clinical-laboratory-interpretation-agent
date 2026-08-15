"use client";

import { useEffect, useState } from "react";
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage auth is available only after mount.
    setCheckingAuth(false);
  }, [router]);

  if (checkingAuth) return <div className="loading-message" role="status">Đang mở lịch sử...</div>;

  return (
    <div className="history-page-layout">
      <div className="page-section-heading">
        <div>
          <span className="eyebrow">Phiếu đã lưu</span>
          <h2>Lịch sử xét nghiệm</h2>
          <p>Theo dõi và tìm lại các phiếu xét nghiệm đã lưu.</p>
        </div>
      </div>
      <HistoryPanel
        mode="patient"
        pageSize={10}
        onUnauthorized={() => {
          clearSession();
          router.replace("/login");
        }}
      />
    </div>
  );
}
