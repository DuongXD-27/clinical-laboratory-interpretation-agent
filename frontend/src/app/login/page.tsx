"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { BrandLockup } from "@/components/common/BrandSignature";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import SegmentedControl from "@/components/common/SegmentedControl";
import { Separator } from "@/components/ui/separator";
import { homeForRole } from "@/lib/roleHome.mjs";
import { login, register, startGuestSession } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { label: "Điền tài khoản bệnh nhân", username: "benhnhan", password: "benhnhan123" },
  { label: "Điền tài khoản bác sĩ", username: "bacsi", password: "bacsi123" },
];

type Mode = "login" | "register";

const AUTH_MODES = [
  { value: "login", label: "Đăng nhập", id: "auth-login-tab", controls: "auth-access-panel" },
  { value: "register", label: "Đăng ký", id: "auth-register-tab", controls: "auth-access-panel" },
] as const;

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- đọc query string client-only để mở đúng tab ban đầu.
    if (params.get("tab") === "register") setMode("register");
  }, []);

  function switchMode(next: Mode) {
    setMode(next);
    window.history.replaceState(null, "", next === "register" ? "/login?tab=register" : "/login");
    setError(null);
    setPassword("");
    setConfirmPassword("");
    setEmail("");
  }

  /** Kiểm tra trước những ràng buộc backend cũng kiểm.
   *
   * Không phải để thay cho backend (server vẫn là nơi chốt), mà để người dùng
   * nhận thông báo tiếng Việt thay vì chuỗi lỗi tiếng Anh của pydantic.
   */
  function validateRegistration(): string | null {
    if (username.length < 3) return "Tên đăng nhập phải có ít nhất 3 ký tự.";
    if (!/^[a-zA-Z0-9_.-]+$/.test(username)) {
      return "Tên đăng nhập chỉ được dùng chữ, số và các ký tự _ . -";
    }
    if (password.length < 8) return "Mật khẩu phải có ít nhất 8 ký tự.";
    if (password !== confirmPassword) return "Hai lần nhập mật khẩu chưa khớp.";
    // Bỏ trống thì bỏ qua — email không bắt buộc. Điền thì kiểm sơ bộ, backend
    // vẫn là nơi chốt (`normalise_email`); ở đây chỉ để người dùng nhận thông
    // báo tiếng Việt thay vì lỗi 422 của pydantic.
    const typedEmail = email.trim();
    if (typedEmail && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(typedEmail)) {
      return "Email chưa hợp lệ.";
    }
    return null;
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (mode === "register") {
      const problem = validateRegistration();
      if (problem) {
        setError(problem);
        return;
      }
    }

    setLoading(true);
    try {
      // Đăng ký xong đăng nhập luôn, để người dùng không phải nhập lại.
      const session = mode === "login" ? await login(username, password) : await register(username, password, email);
      router.push(homeForRole(session.role), { transitionTypes: ["nav-forward"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thực hiện được, vui lòng thử lại");
    } finally {
      setLoading(false);
    }
  }

  async function handleGuest() {
    setError(null);
    setLoading(true);
    try {
      await startGuestSession();
      router.push("/patient", { transitionTypes: ["nav-forward"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không mở được phiên dùng thử");
    } finally {
      setLoading(false);
    }
  }

  function fillDemo(account: (typeof DEMO_ACCOUNTS)[number]) {
    switchMode("login");
    setUsername(account.username);
    setPassword(account.password);
  }

  return (
    <main className="auth-page motion-auth-page">
      <section className="auth-intro" aria-labelledby="auth-title">
        <BrandLockup context="Quiet medical intelligence" />
        <div>
          <p className="type-eyebrow">Không gian riêng tư của bạn</p>
          <h1 id="auth-title" className="text-2xl font-semibold text-foreground">
            Hiểu kết quả xét nghiệm, rõ ràng hơn
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Đăng nhập, đăng ký, hoặc dùng thử ngay không cần tài khoản.
          </p>
        </div>
        <ul className="auth-intro__trust" aria-label="Cam kết của LumiLab">
          <li>Diễn giải bằng tiếng Việt dễ hiểu</li>
          <li>Hiển thị nguồn và khoảng tham chiếu</li>
          <li>Không thay thế chẩn đoán của bác sĩ</li>
        </ul>
        <Link href="/" className="auth-back-link" transitionTypes={["nav-back"]}>
          <ArrowLeft data-icon="inline-start" aria-hidden="true" />
          Về trang giới thiệu
        </Link>
      </section>

      <section className="auth-panel" aria-label="Khu vực truy cập tài khoản">
      <section className="auth-card" aria-label="Đăng nhập hoặc đăng ký">
        <div className="auth-card__mobile-brand">
          <BrandLockup compact />
        </div>
        <SegmentedControl
          value={mode}
          options={AUTH_MODES}
          onValueChange={switchMode}
          ariaLabel="Chọn hình thức truy cập"
          semantics="tabs"
          className="auth-mode-tabs"
        />

        <div
          key={mode}
          id="auth-access-panel"
          className="motion-auth-form"
          role="tabpanel"
          aria-labelledby={mode === "login" ? "auth-login-tab" : "auth-register-tab"}
        >
        <div className="auth-card__heading">
          <h2>{mode === "login" ? "Chào mừng bạn trở lại" : "Tạo tài khoản bệnh nhân"}</h2>
          <p>{mode === "login" ? "Tiếp tục vào không gian LumiLab của bạn." : "Lưu lịch sử và theo dõi xu hướng theo thời gian."}</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <FieldGroup className="auth-fields">
          <Field className="auth-field">
            <FieldLabel htmlFor="username">
              {mode === "login" ? "Tên đăng nhập hoặc email" : "Tên đăng nhập"}
            </FieldLabel>
            <Input
              id="username"
              name="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              spellCheck={false}
              aria-describedby={mode === "register" ? "username-description" : undefined}
            />
            {mode === "register" && (
              <FieldDescription id="username-description">
                Từ 3 ký tự, chỉ dùng chữ, số và các ký tự _ . -
              </FieldDescription>
            )}
          </Field>

          {mode === "register" && (
            <Field className="auth-field">
              <FieldLabel htmlFor="email">
                Email <span>(không bắt buộc)</span>
              </FieldLabel>
              <Input
                id="email"
                name="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                spellCheck={false}
                placeholder="Ví dụ: ban@example.com"
                aria-describedby="email-description"
              />
              <FieldDescription id="email-description">
                Điền email thì lần sau đăng nhập được bằng cả tên lẫn email.
              </FieldDescription>
            </Field>
          )}

          <Field className="auth-field">
            <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
            <Input
              id="password"
              name="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              aria-describedby={mode === "register" ? "password-description" : undefined}
            />
            {mode === "register" && (
              <FieldDescription id="password-description">Ít nhất 8 ký tự.</FieldDescription>
            )}
          </Field>

          {mode === "register" && (
            <Field className="auth-field">
              <FieldLabel htmlFor="confirm">Nhập lại mật khẩu</FieldLabel>
              <Input
                id="confirm"
                name="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
              />
            </Field>
          )}
          </FieldGroup>

          {error ? (
            <Alert variant="destructive" role="alert">
              <AlertTriangle aria-hidden="true" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Đăng ký tài khoản bệnh nhân"}
          </Button>
        </form>

        <div className="auth-divider"><Separator /><span>hoặc</span><Separator /></div>

        <GoogleSignInButton
          onSuccess={(role) => router.push(homeForRole(role), { transitionTypes: ["nav-forward"] })}
          onError={(message) => setError(message)}
        />

        <Button type="button" variant="outline" onClick={handleGuest} disabled={loading} className="w-full">
          Dùng thử với tư cách khách
        </Button>
        <p className="auth-guest-note">Chế độ khách dùng thử được ngay, nhưng không lưu lịch sử xét nghiệm.</p>

        <div className="auth-demo">
          <p>Tài khoản demo — chỉ điền nhanh vào form:</p>
          <div>
            {DEMO_ACCOUNTS.map((account) => (
              <Button key={account.username} type="button" variant="ghost" size="sm" onClick={() => fillDemo(account)}>
                {account.label}
              </Button>
            ))}
          </div>
        </div>
        </div>
      </section>
      </section>
    </main>
  );
}
