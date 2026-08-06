"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { label: "Bệnh nhân demo", username: "benhnhan", password: "benhnhan123" },
  { label: "Bác sĩ demo", username: "bacsi", password: "bacsi123" },
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const session = await login(username, password);
      router.push(session.role === "patient" ? "/patient" : "/doctor");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  }

  function fillDemo(account: (typeof DEMO_ACCOUNTS)[number]) {
    setUsername(account.username);
    setPassword(account.password);
    setError(null);
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 bg-zinc-50 px-6 dark:bg-black">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          VMEC-05 — Giải thích kết quả xét nghiệm
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Đăng nhập để tiếp tục
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="username" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Tên đăng nhập
          </label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
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
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="mt-1 h-11 rounded-full bg-blue-600 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>

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
