"use client";

import { useRouter } from "next/navigation";

type Role = "patient" | "doctor";

export default function LoginPage() {
  const router = useRouter();

  function handleLogin(role: Role) {
    // Mock login — chưa có auth thật, chỉ lưu role đã chọn để demo luồng UI.
    window.localStorage.setItem("vmec05_role", role);
    router.push(role === "patient" ? "/patient" : "/doctor");
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 bg-zinc-50 px-6 dark:bg-black">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          VMEC-05 — Giải thích kết quả xét nghiệm
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Đăng nhập mô phỏng — chọn vai trò để tiếp tục
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row">
        <button
          type="button"
          onClick={() => handleLogin("patient")}
          className="h-12 min-w-[180px] rounded-full bg-blue-600 px-6 font-medium text-white transition-colors hover:bg-blue-700"
        >
          Bệnh nhân
        </button>
        <button
          type="button"
          onClick={() => handleLogin("doctor")}
          className="h-12 min-w-[180px] rounded-full border border-zinc-300 px-6 font-medium text-zinc-900 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-50 dark:hover:bg-zinc-900"
        >
          Bác sĩ
        </button>
      </div>
    </div>
  );
}
