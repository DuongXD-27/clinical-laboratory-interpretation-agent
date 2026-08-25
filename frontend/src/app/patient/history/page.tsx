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
    <div className="space-y-8 pb-12">
      <div className="page-section-heading">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Lịch sử xét nghiệm</h1>
          <p className="mt-1 text-muted-foreground">Theo dõi và tìm lại các phiếu xét nghiệm đã lưu.</p>
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
