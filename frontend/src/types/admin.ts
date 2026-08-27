/** Kiểu dữ liệu cho màn hình trace của admin.
 *
 * Không kiểu nào ở đây mang dữ liệu bệnh nhân, và đó là chủ ý chứ không phải
 * chưa làm tới: bảng `request_traces` phía backend cố tình chỉ giữ số đo vận
 * hành. `userRole` lưu vai trò chứ không lưu người — đủ để biết "màn bác sĩ
 * đang chậm", không đủ để lần ra ai đã khám gì.
 */

export type RequestTrace = {
  request_id: string;
  created_at: string;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  db_query_count: number;
  db_ms: number;
  llm_call_count: number;
  llm_ms: number;
  /** LLM hỏng thì response vẫn 200 và nội dung âm thầm xuống cấp — chỉ con số
   *  này nhìn thấy được chuyện đó. */
  llm_error_count: number;
  user_role: string | null;
  server_timing: string | null;
};

export type RequestTraceListResponse = {
  total: number;
  items: RequestTrace[];
};

export type TraceSummary = {
  request_count: number;
  avg_duration_ms: number;
  max_duration_ms: number;
  llm_call_count: number;
  llm_error_count: number;
  server_error_count: number;
  window_hours: number;
};

export type TracingStatus = {
  langfuse_configured: boolean;
  langfuse_host: string;
  masked: boolean;
  trace_persistence_enabled: boolean;
  retention_days: number;
};

export type TraceQuery = {
  limit?: number;
  offset?: number;
  path?: string;
  minDurationMs?: number;
  statusCode?: number;
  onlyLlmErrors?: boolean;
  windowHours?: number;
};

/** Số liệu độ trễ của MỘT nhóm endpoint.
 *
 * Không có `avg`, và đó là quyết định chứ không phải bỏ sót: để trung bình ở
 * đây là mời người đọc quay lại đúng con số đã che mất long tail.
 *
 * `null` nghĩa là chưa có mẫu — phân biệt rõ với 0, vì trên màn hình vận hành
 * "0ms" đọc như nhanh tuyệt đối.
 */
export type LatencyGroup = {
  group: string;
  count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  error_count: number;
  error_rate_pct: number | null;
  requests_per_min: number | null;
  llm_call_count: number;
  llm_error_count: number;
  input_tokens: number;
  output_tokens: number;
  /** `null` = chưa tính được giá cho model nào trong nhóm. Không phải 0. */
  cost_usd: number | null;
  /** Khác 0 nghĩa là con số chi phí đang báo THẤP hơn thực tế. */
  unpriced_call_count: number;
  cost_per_call_usd: number | null;
};

export type LatencyGroups = {
  ai: LatencyGroup;
  api: LatencyGroup;
  window_hours: number;
  window_minutes: number | null;
  /** Ngày cập nhật bảng giá — chi phí là số cấu hình, không phải số đo được. */
  pricing_updated: string | null;
};

/** Một dòng trong cây span, đã phẳng hoá theo `depth`.
 *
 * Cấu trúc cây do backend dựng (`src/services/span_tree.py`). Bảng quan hệ
 * cha–con KHÔNG nhân đôi sang đây: nhân đôi một bảng phân cấp sang hai ngôn ngữ
 * là đúng loại trôi đã xảy ra với question_templates.json khi đổi analyte id.
 */
export type SpanRow = {
  name: string;
  duration_ms: number;
  depth: number;
  /** `null` ở lá — lá không có gì để khẳng định. `0` nghĩa là con giải thích hết. */
  unaccounted_ms: number | null;
  share_pct: number | null;
};

export type SpanTree = {
  request_id: string;
  rows: SpanRow[];
  aggregates: Array<{ name: string; duration_ms: number }>;
  total_ms: number | null;
};
