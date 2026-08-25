"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import HistoryPanel from "@/components/HistoryPanel";
import { clearSession, getRole, getToken } from "@/lib/api";
import PatientPageHeader from "@/components/patient/PatientPageHeader";

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
    <div className="patient-page-layout">
      <PatientPageHeader
        eyebrow="Hồ sơ xét nghiệm"
        title="Lịch sử xét nghiệm"
        description="Theo dõi và tìm lại các phiếu xét nghiệm đã lưu."
      />
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
