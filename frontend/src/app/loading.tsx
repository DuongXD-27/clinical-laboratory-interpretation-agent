import { SystemState } from "@/components/common/SystemState";
import MotionBoundary from "@/components/common/MotionBoundary";

export default function Loading() {
  return (
    <MotionBoundary variant="system">
    <main className="route-state-page motion-system-page">
      <SystemState
        kind="loading"
        title="Đang chuẩn bị nội dung…"
        description="LumiLab đang kết nối dữ liệu và sắp xếp màn hình cho bạn."
      />
    </main>
    </MotionBoundary>
  );
}
