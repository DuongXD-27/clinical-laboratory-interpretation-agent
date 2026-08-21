"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchGoogleStatus, loginWithGoogle } from "@/lib/api";
import type { Role } from "@/lib/api";

const GSI_SRC = "https://accounts.google.com/gsi/client";

type GoogleCredentialResponse = { credential?: string };

type GoogleAccountsId = {
  initialize: (config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
    auto_select?: boolean;
    cancel_on_tap_outside?: boolean;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
};

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleAccountsId } };
  }
}

/** Nạp script Google Identity Services đúng một lần cho cả trang.
 *
 * Gắn nhiều thẻ script cùng src thì `window.google.accounts.id` bị khởi tạo lại
 * và nút đã vẽ trước đó ngừng phản hồi — hỏng theo kiểu bấm không ăn mà không
 * có lỗi nào trong console.
 */
let gsiPromise: Promise<void> | null = null;

function loadGsi(): Promise<void> {
  if (gsiPromise) return gsiPromise;

  gsiPromise = new Promise<void>((resolve, reject) => {
    if (window.google?.accounts?.id) {
      resolve();
      return;
    }
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("gsi")));
      return;
    }
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("gsi"));
    document.head.appendChild(script);
  });

  return gsiPromise;
}

type Props = {
  onSuccess: (role: Role) => void;
  onError: (message: string) => void;
};

/** Nút "Đăng nhập bằng Google".
 *
 * Tự ẩn hoàn toàn khi server chưa cấu hình `GOOGLE_OAUTH_CLIENT_ID`. Vẽ một nút
 * bấm vào là báo lỗi thì tệ hơn là không có nút nào: người dùng sẽ tưởng tài
 * khoản Google của họ có vấn đề.
 */
export default function GoogleSignInButton({ onSuccess, onError }: Props) {
  const holder = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);

  const handleCredential = useCallback(
    async (response: GoogleCredentialResponse) => {
      if (!response.credential) {
        onError("Không nhận được thông tin từ Google, vui lòng thử lại.");
        return;
      }
      try {
        const session = await loginWithGoogle(response.credential);
        onSuccess(session.role);
      } catch (err) {
        onError(err instanceof Error ? err.message : "Không đăng nhập được bằng Google");
      }
    },
    [onError, onSuccess],
  );

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      const status = await fetchGoogleStatus().catch(() => ({ enabled: false, client_id: null }));
      if (cancelled) return;

      if (!status.enabled || !status.client_id) {
        setEnabled(false);
        return;
      }
      setEnabled(true);

      try {
        await loadGsi();
      } catch {
        if (!cancelled) onError("Không tải được Google Sign-In. Kiểm tra kết nối mạng.");
        return;
      }
      if (cancelled || !holder.current) return;

      const gsi = window.google?.accounts?.id;
      if (!gsi) return;

      gsi.initialize({
        client_id: status.client_id,
        callback: (response) => void handleCredential(response),
        // Tắt tự chọn tài khoản: đây là ứng dụng y tế, đăng nhập phải là hành
        // động chủ động. Máy dùng chung mà tự đăng nhập lại là mở bệnh án của
        // người trước cho người sau.
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      holder.current.innerHTML = "";
      gsi.renderButton(holder.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "signin_with",
        locale: "vi",
        width: 320,
      });
      setReady(true);
    }

    void setup();
    return () => {
      cancelled = true;
    };
  }, [handleCredential, onError]);

  if (enabled === false) return null;

  return (
    <div className="flex flex-col items-center gap-1">
      <div ref={holder} />
      {!ready ? <span className="text-xs text-slate-500">Đang tải Google Sign-In...</span> : null}
    </div>
  );
}
