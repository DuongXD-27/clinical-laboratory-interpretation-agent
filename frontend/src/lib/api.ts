import type {
  DoctorQueueResponse,
  DoctorReportDetail,
  FindingReviewResponse,
  ReviewOutcome,
} from "@/types/doctor";
import type {
  DoctorNote,
  LabReportDetail,
  LabReportListResponse,
  ReportQuestion,
} from "@/types/history";
import type { OrchestratorResponse, OrchestratorUiContext } from "@/types/orchestrator";

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
  limit?: number;
  offset?: number;
};

export async function fetchHistory(query: HistoryQuery = {}): Promise<LabReportListResponse> {
  const params = new URLSearchParams();
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  if (query.patientUsername) params.set("patient_username", query.patientUsername);
  if (query.limit) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));

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

/** Bệnh nhân chốt danh sách câu hỏi muốn mang đi khám. */
export async function selectReportQuestions(
  reportId: number,
  questionIds: number[],
): Promise<ReportQuestion[]> {
  const response = await authFetch(`/api/v1/history/${reportId}/questions/selection`, {
    method: "POST",
    body: JSON.stringify({ question_ids: questionIds }),
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không lưu được lựa chọn câu hỏi"));
  }
  return response.json();
}

/** Bác sĩ trả lời một câu hỏi của phiếu. Nội dung không qua guardrail. */
export async function answerReportQuestion(
  reportId: number,
  questionId: number,
  answerText: string,
): Promise<ReportQuestion> {
  const response = await authFetch(
    `/api/v1/history/${reportId}/questions/${questionId}/answer`,
    { method: "POST", body: JSON.stringify({ answer_text: answerText }) },
  );

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không lưu được câu trả lời"));
  }
  return response.json();
}

/** Bác sĩ ghi nhận xét lên một phiếu. Chỉ thêm mới, không sửa, không xoá. */
export async function createDoctorNote(
  reportId: number,
  noteText: string,
): Promise<DoctorNote> {
  const response = await authFetch(`/api/v1/history/${reportId}/notes`, {
    method: "POST",
    body: JSON.stringify({ note_text: noteText }),
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không lưu được ghi chú"));
  }
  return response.json();
}

/** Bác sĩ đánh dấu đã xem phiếu mà không kèm ghi chú. Bấm nhiều lần vô hại. */
export async function markReportReviewed(reportId: number): Promise<LabReportDetail> {
  const response = await authFetch(`/api/v1/history/${reportId}/review`, {
    method: "POST",
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không đánh dấu được đã xem"));
  }
  return response.json();
}

export type DoctorQueueTab = "pending" | "critical" | "ocr" | "questions" | "verified";

export async function fetchDoctorQueue(
  tab: DoctorQueueTab,
  page = 1,
  pageSize = 20,
): Promise<DoctorQueueResponse> {
  const params = new URLSearchParams({
    tab,
    page: String(page),
    pageSize: String(pageSize),
  });
  const response = await authFetch(`/api/v1/doctor/queue?${params.toString()}`);

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không tải được hàng đợi kiểm chứng"));
  }
  return response.json();
}

export async function fetchDoctorReport(reportId: number): Promise<DoctorReportDetail> {
  const response = await authFetch(`/api/v1/doctor/reports/${reportId}`);

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không mở được phiếu kiểm chứng"));
  }
  return response.json();
}

export async function reviewDoctorFinding(
  findingId: number,
  outcome: Exclude<ReviewOutcome, "pending">,
  doctorNote?: string,
): Promise<FindingReviewResponse> {
  const response = await authFetch(`/api/v1/doctor/findings/${findingId}/review`, {
    method: "PATCH",
    body: JSON.stringify({ outcome, doctor_note: doctorNote }),
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không lưu được kiểm chứng luận điểm"));
  }
  return response.json();
}

export async function answerDoctorQuestion(
  questionId: number,
  answerText: string,
): Promise<ReportQuestion> {
  const response = await authFetch(`/api/v1/doctor/questions/${questionId}/answer`, {
    method: "POST",
    body: JSON.stringify({ answer_text: answerText }),
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không lưu được câu trả lời"));
  }
  return response.json();
}

export async function completeDoctorReport(reportId: number) {
  const response = await authFetch(`/api/v1/doctor/reports/${reportId}/complete`, {
    method: "POST",
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Không hoàn tất được phiếu"));
  }
  return response.json();
}

export async function sendOrchestratorMessage(
  message: string,
  uiContext?: OrchestratorUiContext,
): Promise<OrchestratorResponse> {
  const response = await authFetch("/api/v1/orchestrator/message", {
    method: "POST",
    body: JSON.stringify({
      message,
      ...(uiContext ? { ui_context: uiContext } : {}),
    }),
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Trợ lý chưa thể phản hồi lúc này"));
  }
  return response.json();
}

export async function acknowledgeOrchestratorOnboarding(): Promise<OrchestratorResponse> {
  const response = await authFetch("/api/v1/orchestrator/onboarding/acknowledge", {
    method: "POST",
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Chưa ghi nhận được xác nhận sử dụng trợ lý"));
  }
  return response.json();
}
