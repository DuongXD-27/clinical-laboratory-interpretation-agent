"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { homeForRole } from "@/lib/roleHome.mjs";
import { login, register, startGuestSession } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { label: "Điền tài khoản bệnh nhân", username: "benhnhan", password: "benhnhan123" },
  { label: "Điền tài khoản bác sĩ", username: "bacsi", password: "bacsi123" },
];

type Mode = "login" | "register";

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
      router.push(homeForRole(session.role));
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
      router.push("/patient");
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
    <div className="flex flex-1 flex-col items-center justify-center gap-7 bg-[linear-gradient(180deg,#f8fbff_0%,#f3f7fc_100%)] px-6 py-10">
      <div className="text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-blue-600 text-3xl font-light text-white shadow-lg shadow-blue-600/20" aria-hidden="true">
          +
        </div>
        <h1 className="text-2xl font-semibold text-slate-950">
          VMEC-05 - Giải thích kết quả xét nghiệm
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Đăng nhập, đăng ký, hoặc dùng thử ngay không cần tài khoản
        </p>
        <Link href="/" className="mt-3 inline-flex text-sm font-medium text-blue-700 hover:underline">
          ← Về trang giới thiệu
        </Link>
      </div>

      <div className="flex min-h-[438px] w-full max-w-sm flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(28,55,91,0.08)]">
        <div className="grid grid-cols-2 gap-1 rounded-full bg-slate-100 p-1">
          {(["login", "register"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => switchMode(value)}
              className={`h-9 rounded-full text-sm font-medium transition-colors ${
                mode === value
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {value === "login" ? "Đăng nhập" : "Đăng ký"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="username" className="text-sm font-medium text-slate-700">
              {mode === "login" ? "Tên đăng nhập hoặc email" : "Tên đăng nhập"}
            </label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none placeholder:text-slate-500 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
            />
            {mode === "register" && (
              <p className="text-xs leading-5 text-slate-600">
                Từ 3 ký tự, chỉ dùng chữ, số và các ký tự _ . -
              </p>
            )}
          </div>

          {mode === "register" && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium text-slate-700">
                Email <span className="font-normal text-slate-500">(không bắt buộc)</span>
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="ban@example.com"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none placeholder:text-slate-500 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
              />
              <p className="text-xs leading-5 text-slate-600">
                Điền email thì lần sau đăng nhập được bằng cả tên lẫn email.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-slate-700">
              Mật khẩu
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none placeholder:text-slate-500 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
            />
            {mode === "register" && <p className="text-xs leading-5 text-slate-600">Ít nhất 8 ký tự.</p>}
          </div>

          {mode === "register" && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="confirm" className="text-sm font-medium text-slate-700">
                Nhập lại mật khẩu
              </label>
              <input
                id="confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none placeholder:text-slate-500 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
              />
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 h-11 rounded-full bg-blue-600 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Đang xử lý..." : mode === "login" ? "Đăng nhập" : "Đăng ký tài khoản bệnh nhân"}
          </button>
        </form>

        <div className="flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-200" />
          <span className="text-xs text-slate-500">hoặc</span>
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        {/* Tự ẩn khi máy chủ chưa cấu hình GOOGLE_OAUTH_CLIENT_ID. */}
        <GoogleSignInButton
          onSuccess={(role) => router.push(homeForRole(role))}
          onError={(message) => setError(message)}
        />

        <button
          type="button"
          onClick={handleGuest}
          disabled={loading}
          className="h-11 rounded-full border border-slate-300 font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          Dùng thử với tư cách khách
        </button>
        <p className="text-center text-xs leading-5 text-slate-600">
          Chế độ khách dùng thử được ngay, nhưng không lưu lịch sử xét nghiệm.
        </p>
      </div>

      <div className="flex flex-col items-center gap-2 pt-1">
        <p className="text-xs text-slate-600">Tài khoản demo (chỉ điền nhanh vào form):</p>
        <div className="flex flex-wrap justify-center gap-3">
          {DEMO_ACCOUNTS.map((account) => (
            <button
              key={account.username}
              type="button"
              onClick={() => fillDemo(account)}
              className="rounded-full border border-slate-300 bg-white px-4 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              {account.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
