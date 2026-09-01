import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { BrandLockup } from "@/components/common/BrandSignature";
import { SystemState } from "@/components/common/SystemState";
import MotionBoundary from "@/components/common/MotionBoundary";

export default function NotFound() {
  return (
    <MotionBoundary variant="system">
    <main className="route-state-page motion-system-page">
      <div className="route-state-page__brand"><BrandLockup context="Quiet medical intelligence" /></div>
      <SystemState
        kind="not-found"
        title="Không tìm thấy trang này"
        description="Đường dẫn có thể đã thay đổi hoặc nội dung không còn khả dụng."
        action={(
          <Link href="/" className="system-state__button" transitionTypes={["nav-back"]}>
            <ArrowLeft data-icon="inline-start" aria-hidden="true" />
            Về trang giới thiệu
          </Link>
        )}
      />
    </main>
    </MotionBoundary>
  );
}
