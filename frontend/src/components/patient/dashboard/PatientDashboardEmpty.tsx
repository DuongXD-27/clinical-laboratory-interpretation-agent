import Link from "next/link";
import { PATIENT_ROUTES } from "@/lib/patientRoutes.mjs";
import { SystemState } from "@/components/common/SystemState";

export default function PatientDashboardEmpty() {
  return (
    <section aria-label="Bắt đầu với LumiLab">
      <SystemState
        kind="empty"
        title="Bạn chưa có kết quả xét nghiệm nào"
        description="Phân tích phiếu xét nghiệm đầu tiên để bắt đầu theo dõi sức khỏe và xem lịch sử chỉ số của bạn."
        action={<Link href={PATIENT_ROUTES.ANALYSIS} transitionTypes={["nav-route"]} className="system-state__button">Phân tích xét nghiệm</Link>}
      />
    </section>
  );
}
