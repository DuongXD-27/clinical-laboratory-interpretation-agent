"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, register, startGuestSession } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { label: "Bệnh nhân demo", username: "benhnhan", password: "benhnhan123" },
  { label: "Bác sĩ demo", username: "bacsi", password: "bacsi123" },
];

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setPassword("");
    setConfirmPassword("");
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
    if (password.length < 6) return "Mật khẩu phải có ít nhất 6 ký tự.";
    if (password !== confirmPassword) return "Hai lần nhập mật khẩu chưa khớp.";
    return null;
  }

  async function handleSubmit(e: React.SubmitEvent<HTMLFormElement>) {
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
      const session = mode === "login" ? await login(username, password) : await register(username, password);
      router.push(session.role === "doctor" ? "/doctor" : "/patient");
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
    <div className="flex flex-1 flex-col items-center justify-center gap-8 bg-zinc-50 px-6 py-12 dark:bg-black">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          VMEC-05 — Giải thích kết quả xét nghiệm
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Đăng nhập, đăng ký, hoặc dùng thử ngay không cần tài khoản
        </p>
      </div>

      <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="grid grid-cols-2 gap-1 rounded-full bg-zinc-100 p-1 dark:bg-zinc-900">
          {(["login", "register"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => switchMode(value)}
              className={`h-9 rounded-full text-sm font-medium transition-colors ${
                mode === value
                  ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-50"
                  : "text-zinc-600 dark:text-zinc-400"
              }`}
            >
              {value === "login" ? "Đăng nhập" : "Đăng ký"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="username" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Tên đăng nhập
            </label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
            />
            {mode === "register" && (
              <p className="text-xs text-zinc-500">
                Từ 3 ký tự, chỉ dùng chữ, số và các ký tự _ . -
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Mật khẩu
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
            />
            {mode === "register" && <p className="text-xs text-zinc-500">Ít nhất 6 ký tự.</p>}
          </div>

          {mode === "register" && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="confirm" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Nhập lại mật khẩu
              </label>
              <input
                id="confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
              />
            </div>
          )}

          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 h-11 rounded-full bg-blue-600 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Đang xử lý..." : mode === "login" ? "Đăng nhập" : "Đăng ký tài khoản bệnh nhân"}
          </button>
        </form>

        <div className="flex items-center gap-3">
          <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
          <span className="text-xs text-zinc-500">hoặc</span>
          <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
        </div>

        <button
          type="button"
          onClick={handleGuest}
          disabled={loading}
          className="h-11 rounded-full border border-zinc-300 font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          Dùng thử với tư cách khách
        </button>
        <p className="text-center text-xs text-zinc-500">
          Chế độ khách dùng thử được ngay, nhưng không lưu lịch sử xét nghiệm.
        </p>
      </div>

      <div className="flex flex-col items-center gap-2">
        <p className="text-xs text-zinc-500 dark:text-zinc-500">Tài khoản demo (điền nhanh để thử):</p>
        <div className="flex gap-3">
          {DEMO_ACCOUNTS.map((account) => (
            <button
              key={account.username}
              type="button"
              onClick={() => fillDemo(account)}
              className="rounded-full border border-zinc-300 px-4 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              {account.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
