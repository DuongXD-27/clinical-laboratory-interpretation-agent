export const OCR_ERROR_MESSAGES = Object.freeze({
  UNSUPPORTED_FILE: "Định dạng tệp này chưa được hỗ trợ. Hãy dùng ảnh PNG, JPG hoặc JPEG.",
  FILE_TOO_LARGE: "Tệp vượt quá dung lượng cho phép. Hãy chọn ảnh nhỏ hơn.",
  IMAGE_UNREADABLE: "Không thể đọc rõ ảnh này. Hãy chụp thẳng, đủ sáng và thử lại.",
  NO_INDICATORS_FOUND: "Không tìm thấy chỉ số xét nghiệm trong ảnh. Hãy chụp rõ toàn bộ phiếu.",
  PROVIDER_UNAVAILABLE: "Tính năng đọc phiếu tạm thời chưa sẵn sàng. Bạn có thể nhập kết quả thủ công.",
  OCR_EXTRACTION_FAILED: "Chưa thể trích xuất dữ liệu từ phiếu. Hãy thử ảnh rõ hơn hoặc nhập thủ công.",
  REVIEW_REQUIRED: "Dữ liệu OCR cần được đối chiếu lại với phiếu gốc trước khi phân tích.",
  NO_SUPPORTED_ANALYTES: "Phiếu không có chỉ số nào thuộc danh sách LumiLab hỗ trợ phân tích.",
});

export function friendlyOcrError(status, detail, reasonCode) {
  if (reasonCode && OCR_ERROR_MESSAGES[reasonCode]) return OCR_ERROR_MESSAGES[reasonCode];
  if (status < 500 && typeof detail === "string" && detail.trim()) return detail;
  return "Không thể đọc rõ phiếu xét nghiệm này. Hãy thử ảnh rõ hơn hoặc nhập kết quả thủ công.";
}
