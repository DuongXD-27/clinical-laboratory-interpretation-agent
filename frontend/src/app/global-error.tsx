"use client";

import { RotateCcw } from "lucide-react";
import { SystemState } from "@/components/common/SystemState";
import MotionBoundary from "@/components/common/MotionBoundary";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="vi">
      <body>
        <MotionBoundary variant="system">
        <main className="route-state-page route-state-page--global">
          <SystemState
            kind="error"
            title="LumiLab đang tạm gián đoạn"
            description="Phiên của bạn vẫn được giữ nguyên. Hãy thử mở lại ứng dụng."
            action={(
              <button type="button" className="system-state__button" onClick={reset}>
                <RotateCcw data-icon="inline-start" aria-hidden="true" />
                Mở lại LumiLab
              </button>
            )}
          />
        </main>
        </MotionBoundary>
      </body>
    </html>
  );
}
