export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Role = "patient" | "doctor";

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
