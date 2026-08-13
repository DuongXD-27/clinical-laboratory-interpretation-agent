import type { LabReportDetail, LabReportListResponse } from "@/types/history";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Role = "patient" | "doctor" | "guest";

const TOKEN_KEY = "vmec05_token";
const ROLE_KEY = "vmec05_role";
const USERNAME_KEY = "vmec05_username";

export function saveSession(token: string, role: Role, username: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(ROLE_KEY, role);
  window.localStorage.setItem(USERNAME_KEY, username);
}

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRole(): Role | null {
  return window.localStorage.getItem(ROLE_KEY) as Role | null;
}

export function getUsername(): string | null {
  return window.localStorage.getItem(USERNAME_KEY);
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ROLE_KEY);
  window.localStorage.removeItem(USERNAME_KEY);
}

/** Đọc thông điệp lỗi từ backend.
 *
 * FastAPI trả `detail` là chuỗi cho HTTPException nhưng là MẢNG object cho lỗi
 * validation (422) — hiển thị thẳng mảng đó ra sẽ thành "[object Object]".
 */
export async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first?.msg === "string") return first.msg;
  }
  return fallback;
}

export async function login(username: string, password: string) {
  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    throw new Error("Sai tên đăng nhập hoặc mật khẩu");
  }

  const data = await response.json();
  saveSession(data.access_token, data.role, data.username);
  return data as { access_token: string; role: Role; username: string };
}

/** Đăng ký tài khoản bệnh nhân rồi đăng nhập luôn.
 *
 * Không có tham số `role`: backend luôn tạo role `patient`, tài khoản bác sĩ do
 * admin cấp bằng script. Gửi kèm role ở đây cũng vô nghĩa.
 */
export async function register(username: string, password: string) {
  const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Đăng ký không thành công"));
  }

  return login(username, password);
}

/** Mở phiên khách: dùng thử ngay, không tạo tài khoản, không lưu lịch sử. */
export async function startGuestSession() {
  const response = await fetch(`${API_BASE}/api/v1/auth/guest`, { method: "POST" });

  if (!response.ok) {
    throw new Error("Không mở được phiên dùng thử, vui lòng thử lại");
  }

  const data = await response.json();
  saveSession(data.access_token, "guest", data.username);
  return data as { access_token: string; username: string; expires_in_seconds: number };
}

/** fetch có gắn sẵn Authorization header từ token đang lưu (nếu có). */
export async function authFetch(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

/** Token hết hạn/không hợp lệ — người gọi nên xoá phiên và quay về màn đăng nhập. */
export class UnauthorizedError extends Error {
  constructor() {
    super("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
    this.name = "UnauthorizedError";
  }
}

export type HistoryQuery = {
  from?: string;
  to?: string;
  patientUsername?: string;
};

export async function fetchHistory(query: HistoryQuery = {}): Promise<LabReportListResponse> {
  const params = new URLSearchParams();
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  if (query.patientUsername) params.set("patient_username", query.patientUsername);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await authFetch(`/api/v1/history${suffix}`);

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không tải được lịch sử xét nghiệm"));
  }
  return response.json();
}

export async function fetchHistoryDetail(reportId: number): Promise<LabReportDetail> {
  const response = await authFetch(`/api/v1/history/${reportId}`);

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không mở được phiếu xét nghiệm"));
  }
  return response.json();
}
