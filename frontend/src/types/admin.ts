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
  /** TTFT — độ trễ PHÍA NHÀ CUNG CẤP, không phải TTFT người dùng cảm nhận:
   * hệ thống không stream ra client vì guardrail phải là lớp cuối (ADR-004).
   * `null` khi chưa bật streaming. */
  ttft_p50_ms: number | null;
  ttft_p95_ms: number | null;
  /** Khác 0 = có lượt gọi báo 0 token, gần như chắc chắn lỗi đo lường. */
  missing_usage_count: number;
};

export type LatencyGroups = {
  ai: LatencyGroup;
  api: LatencyGroup;
  window_hours: number;
  window_minutes: number | null;
  /** Streaming nội bộ có đang bật không — TTFT rỗng khi tắt là ĐÚNG. */
  streaming_enabled: boolean;
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

/** Một mốc thời gian. `null` = không đo được, KHÔNG phải 0. */
export type TimeseriesPoint = {
  start: string;
  count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  error_count: number;
  error_rate_pct: number | null;
  errors_by_type: Record<string, number>;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  llm_call_count: number;
  llm_error_count: number;
  guardrail_fallback_count: number;
  guardrail_rewrite_count: number;
  /** Tỉ lệ lượt phải thay bằng văn bản dựng sẵn — đo được, không phải groundedness. */
  guardrail_fallback_rate_pct: number | null;
  chat_degraded_count?: number;
  chat_blocked_count?: number;
  chat_blocked_reasons?: Record<string, number>;
  chat_blocked_rate_pct: number | null;
  chat_degraded_rate_pct: number | null;
  success_rate_pct: number | null;
  judge_sample_count: number;
  groundedness_pct: number | null;
  faithfulness_pct: number | null;
  relevance_pct: number | null;
  safety_final_escape_count: number;
  rag_retrieval_count: number;
  rag_retrieval_ms: number;
  rag_source_count: number;
  rag_top_k: number;
};

export type Timeseries = {
  group: string;
  bucket_minutes: number;
  since: string;
  until: string;
  points: TimeseriesPoint[];
  error_types: string[];
  rag_status?: string;
  rag_required?: boolean;
};

export type Slo = {
  name: string;
  target_pct: number;
  actual_pct: number | null;
  status: string;
  sample_count: number;
  budget_used_pct: number | null;
  budget_remaining: number | null;
  detail: string;
};

export type ErrorBreakdown = {
  error_type: string;
  count: number;
  example_exception: string | null;
};

export type SloReport = {
  overall_status: string;
  slos: Slo[];
  errors: ErrorBreakdown[];
  window_hours: number;
  /** Ngưỡng hiện tại là ĐỀ XUẤT, nhóm phải chốt lại — màn hình phải nói ra. */
  thresholds_provisional: boolean;
};
