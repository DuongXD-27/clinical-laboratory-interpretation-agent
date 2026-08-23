/** Phân tích header Server-Timing thành các chặng đo được.
 *
 * Chuỗi lưu trong `request_traces.server_timing` có dạng:
 *
 *   analysis-analyzer;dur=9426.725, db-query;dur=4.6, http-total;dur=9451.9
 *
 * Đây là thứ trả lời câu hỏi thật sự đáng hỏi: request 9.4 giây thì 9.4 giây
 * đó tiêu ở đâu. Bảng danh sách chỉ nói tổng thời lượng; không tách được chặng
 * thì `request_id` chỉ tra ra một dòng chứ không tra ra nguyên nhân.
 *
 * Tách khỏi component và để ở `.mjs` theo quy ước của thư mục: logic thuần thì
 * `node --test` chạy được.
 */

/** Các chặng là TỔNG của chặng khác, không cộng vào biểu đồ phân rã.
 *
 * `http-total` bao trọn cả request, `analysis-graph-total` bao trọn các node
 * của graph. Vẽ chúng cạnh những chặng con sẽ thành đếm hai lần và mọi tỉ lệ
 * đều sai.
 */
const AGGREGATE_METRICS = new Set(["http-total", "analysis-graph-total"]);

/** Chặng lặp lại nhiều lần trong một request, con số là tổng cộng dồn. */
const ACCUMULATED_METRICS = new Set(["db-query"]);

export function parseServerTiming(raw) {
  if (!raw || typeof raw !== "string") return [];

  const entries = [];
  for (const chunk of raw.split(",")) {
    const part = chunk.trim();
    if (!part) continue;

    const [name, ...params] = part.split(";");
    const durParam = params.find((p) => p.trim().startsWith("dur="));
    if (!durParam) continue;

    const duration = Number(durParam.trim().slice(4));
    if (!Number.isFinite(duration)) continue;

    const metric = name.trim();
    entries.push({
      name: metric,
      durationMs: duration,
      isAggregate: AGGREGATE_METRICS.has(metric),
      isAccumulated: ACCUMULATED_METRICS.has(metric),
    });
  }
  return entries;
}

/** Chia thành phần tổng và phần chi tiết, sắp chậm nhất lên trước.
 *
 * Sắp theo thời lượng chứ không theo thứ tự xuất hiện: người mở màn này đang
 * đi tìm chỗ tốn thời gian, không đi đọc trình tự thực thi.
 */
export function splitTimings(raw) {
  const all = parseServerTiming(raw);
  const totals = all.filter((e) => e.isAggregate);
  const stages = all.filter((e) => !e.isAggregate).sort((a, b) => b.durationMs - a.durationMs);
  const slowest = stages.reduce((max, e) => Math.max(max, e.durationMs), 0);
  return { totals, stages, slowest };
}

/** Nhãn tiếng Việt cho các chặng đã biết; chặng lạ thì giữ nguyên tên gốc. */
const LABELS = {
  "http-total": "Toàn bộ request",
  "db-query": "Truy vấn CSDL",
  "analysis-graph-total": "Toàn bộ graph phân tích",
  "analysis-reference-range": "Đối chiếu khoảng tham chiếu",
  "analysis-critical-detector": "Phát hiện giá trị nguy kịch",
  "analysis-analyzer": "Sinh giải thích (LLM)",
  "analysis-generate-questions": "Sinh câu hỏi gợi ý",
  "analysis-guardrail": "Kiểm duyệt guardrail",
  "analysis-response-map": "Dựng response",
  "image-processor-init": "Khởi tạo xử lý ảnh",
  "vision-client-init": "Khởi tạo client OCR",
  "ocr-file-read": "Đọc file ảnh",
  "ocr-preprocess": "Tiền xử lý ảnh",
  "ocr-vision-extract": "Trích xuất bằng Vision LLM",
};

export function timingLabel(name) {
  return LABELS[name] || name;
}
