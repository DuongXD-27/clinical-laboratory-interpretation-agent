"use client";

import { RotateCcw } from "lucide-react";
import { BrandLockup } from "@/components/common/BrandSignature";
import { SystemState } from "@/components/common/SystemState";
import { Button } from "@/components/ui/button";
import MotionBoundary from "@/components/common/MotionBoundary";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <MotionBoundary variant="system">
    <main className="route-state-page motion-system-page">
      <div className="route-state-page__brand"><BrandLockup context="Quiet medical intelligence" /></div>
      <SystemState
        kind="error"
        title="Màn hình chưa thể hiển thị"
        description="Dữ liệu của bạn không bị thay đổi. Hãy thử tải lại phần này."
        action={(
          <Button type="button" onClick={reset}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Thử lại
          </Button>
        )}
      />
    </main>
    </MotionBoundary>
  );
}
