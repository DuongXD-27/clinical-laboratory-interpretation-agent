Corpus provenance report — Phase 1 (App Help Knowledge Base). Mỗi block dưới đây tương ứng với một file trong `data/app_how_to_use/`.

```
APP_HELP_FILE=upload-lab-report.md
PRODUCT_SOURCE_FILES=frontend/src/app/patient/analysis/page.tsx,frontend/src/components/OcrReviewPanel.tsx,frontend/src/components/patient/PatientSidebar.tsx,frontend/src/components/patient/dashboard/QuickActions.tsx
ROUTES_VERIFIED=/patient/analysis
UI_TEXT_VERIFIED="Tải phiếu xét nghiệm hoặc nhập các chỉ số để hệ thống giải thích kết quả.", "Nhập tay", "Tải ảnh phiếu", "Dữ liệu tham chiếu hiện hỗ trợ người từ 18 đến 60 tuổi.", "Xóa dữ liệu đang nhập"
INVENTED_FEATURES=NONE
```

```
APP_HELP_FILE=ocr-review.md
PRODUCT_SOURCE_FILES=frontend/src/components/OcrReviewPanel.tsx,frontend/src/app/patient/analysis/page.tsx,src/api/ocr_routes.py
ROUTES_VERIFIED=/patient/analysis?mode=ocr
UI_TEXT_VERIFIED="Tải phiếu · Kiểm tra dữ liệu · Phân tích · Xem kết quả", "Tôi đã kiểm tra tên, giá trị và đơn vị với ảnh gốc.", "Tôi xác nhận giá trị trên đã đúng với phiếu xét nghiệm.", "Đọc phiếu xét nghiệm", "Không tìm thấy chỉ số xét nghiệm trong ảnh. Hãy chụp rõ toàn bộ phiếu và thử lại.", "Tải ảnh cá nhân hiện chưa được bật trong môi trường này."
INVENTED_FEATURES=NONE
```

```
APP_HELP_FILE=analysis-results.md
PRODUCT_SOURCE_FILES=frontend/src/components/patient/AnalysisResultView.tsx,frontend/src/app/patient/reports/[reportId]/page.tsx,frontend/src/components/patient/PatientReportDetail.tsx
ROUTES_VERIFIED=/patient/analysis,/patient/reports/{reportId}
UI_TEXT_VERIFIED="Kết quả xét nghiệm", "Cảnh báo sức khỏe nghiêm trọng", "Tôi sẽ liên hệ bác sĩ", "Kết quả do AI tạo ra chỉ nhằm mục đích tham khảo, không thay thế chẩn đoán y khoa.", "Mở trang chi tiết", "Kết quả đã được lưu vào lịch sử xét nghiệm.", "Xóa phiếu", "Bạn có chắc muốn xóa kết quả xét nghiệm này?"
INVENTED_FEATURES=NONE
NOTES=PatientReportDetail.tsx nay đã đọc toàn bộ (186 dòng). Phát hiện quan trọng ban đầu bị bỏ sót: file này có nút "Xóa phiếu" (deleteReport(), gọi DELETE /api/v1/patient/me/lab-reports/{reportId}) — corpus đã được bổ sung claim này (trước đó chỉ nói chung chung "hiển thị lại chi tiết phiếu", có nguy cơ để sót tính năng xóa).
```

```
APP_HELP_FILE=history.md
PRODUCT_SOURCE_FILES=frontend/src/app/patient/history/page.tsx,frontend/src/app/patient/history/[reportId]/page.tsx,frontend/src/components/patient/PatientSidebar.tsx,frontend/src/components/patient/dashboard/QuickActions.tsx,frontend/src/components/HistoryPanel.tsx,frontend/src/components/patient/PatientReportDetail.tsx
ROUTES_VERIFIED=/patient/history,/patient/history/{reportId}
UI_TEXT_VERIFIED="Lịch sử xét nghiệm", "Theo dõi và tìm lại các phiếu xét nghiệm đã lưu.", "Xem lịch sử", "Tra cứu kết quả cũ", "Xóa lọc", "Ghi chú chỉ thêm mới, không sửa và không xoá.", "Xóa phiếu", "Bạn có chắc muốn xóa kết quả xét nghiệm này?"
INVENTED_FEATURES=NONE
NOTES=HistoryPanel.tsx đã đọc toàn bộ (677 dòng): không có nút xóa ở danh sách, chỉ "Xóa lọc" (xóa bộ lọc tìm kiếm). Vòng review đầu tiên dừng lại ở đó và (sai) kết luận "không có chức năng xóa lịch sử" — sau đó đọc thêm PatientReportDetail.tsx (component thật sự render trang chi tiết phiếu) mới phát hiện có nút "Xóa phiếu" thật, gọi DELETE /api/v1/patient/me/lab-reports/{reportId}. Đây là bài học trực tiếp cho AH-10/AH-12: một claim "tính năng không tồn tại" phải xác minh trên MỌI file liên quan (danh sách + chi tiết), không dừng ở file đầu tiên đọc được. Corpus đã sửa lại đúng: xóa có tồn tại, nhưng thực hiện ở trang chi tiết chứ không phải trang danh sách.
```

```
APP_HELP_FILE=trends.md
PRODUCT_SOURCE_FILES=frontend/src/app/patient/trends/page.tsx,frontend/src/components/patient/PatientSidebar.tsx,frontend/src/components/patient/dashboard/QuickActions.tsx
ROUTES_VERIFIED=/patient/trends,/patient/trends?mode=group
UI_TEXT_VERIFIED="Chọn một chỉ số để xem biến động qua các lần xét nghiệm đã lưu.", "Từng chỉ số", "Cả nhóm chức năng", "5 kết quả gần nhất", "3 tháng gần nhất", "Giải thích xu hướng", "Giải thích cả nhóm", "Biểu đồ đường", "Ma trận nhiệt", "Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên.", "Biểu đồ và phần giải thích xu hướng chỉ hỗ trợ theo dõi dữ liệu xét nghiệm theo thời gian, không phải chẩn đoán và không thay thế đánh giá của bác sĩ."
INVENTED_FEATURES=NONE
```

```
APP_HELP_FILE=critical-alerts.md
PRODUCT_SOURCE_FILES=frontend/src/components/patient/AnalysisResultView.tsx,frontend/src/components/patient/dashboard/NeedsAttention.tsx,frontend/src/app/patient/trends/page.tsx
ROUTES_VERIFIED=/patient/analysis,/patient,/patient/trends
UI_TEXT_VERIFIED="Cảnh báo sức khỏe nghiêm trọng", "Tôi sẽ liên hệ bác sĩ", "Chỉ số cần lưu ý", "Cần chú ý khẩn cấp", "Cần lưu ý", "Cần chú ý ngay"
INVENTED_FEATURES=NONE
NOTES=Đây không có route riêng — corpus nói rõ ràng đây là component lồng trong 3 màn hình khác, không phải trang độc lập, đúng theo yêu cầu "không tưởng tượng route chưa có".
```

```
APP_HELP_FILE=doctor-questions.md
PRODUCT_SOURCE_FILES=frontend/src/components/QuestionsForDoctorPanel.tsx,frontend/src/components/doctor/DoctorReportSidebar.tsx,frontend/src/app/doctor/trend-reviews/page.tsx,frontend/src/components/patient/TrendDoctorReviewPanel.tsx,frontend/src/app/doctor/page.tsx
ROUTES_VERIFIED=/patient/analysis,/patient/reports/{reportId},/doctor/reports/{reportId},/doctor/trend-reviews,/doctor/trend-reviews/{requestId}
UI_TEXT_VERIFIED="Câu hỏi mang đi hỏi bác sĩ", "Sao chép", "In", "Không có câu hỏi bổ sung được đề xuất cho phiếu này.", "Bạn đang dùng thử với tư cách khách nên lựa chọn này không được lưu lại.", "Câu hỏi của bệnh nhân (N)", "Trả lời câu hỏi này cho bệnh nhân", "Lưu câu trả lời", "Sửa", "Đánh giá biểu đồ xu hướng", "Đang chờ", "Đã review", "Tất cả", "Xác nhận nhận xét AI phù hợp", "Đính chính hoặc bổ sung nhận xét AI", "Cần theo dõi hoặc trao đổi thêm", "Gửi review"
INVENTED_FEATURES=NONE
NOTES=/doctor/trend-reviews/[requestId]/page.tsx nay đã đọc toàn bộ (320 dòng). Bổ sung vào corpus: 3 mức đánh giá cụ thể (confirmed/corrected/needs_follow_up), ô nhận xét bắt buộc, và hành vi form chuyển read-only sau khi đã gửi review (readOnly = review.status !== "PENDING").
```

```
APP_HELP_FILE=provenance-sources.md
PRODUCT_SOURCE_FILES=frontend/src/components/patient/SourcesDisclosure.tsx,frontend/src/components/patient/IndicatorResultCard.tsx,frontend/src/components/patient/assistant/AssistantTurn.tsx
ROUTES_VERIFIED=/patient/analysis,/patient/reports/{reportId},/patient/history/{reportId}
UI_TEXT_VERIFIED="Nguồn tham khảo · N nguồn", "Xem nguồn", "Nguồn tham khảo (N)"
INVENTED_FEATURES=NONE
```

```
APP_HELP_FILE=profile.md
PRODUCT_SOURCE_FILES=frontend/src/app/patient/profile/page.tsx,frontend/src/components/patient/PatientSidebar.tsx
ROUTES_VERIFIED=/patient/profile
UI_TEXT_VERIFIED="Thông tin cá nhân", "Chỉnh sửa", "Lưu thay đổi", "Hủy", "Email chưa hợp lệ.", "Quản lý thông tin dùng để đối chiếu khi xem các phiếu đã lưu."
INVENTED_FEATURES=NONE
```

```
APP_HELP_FILE=chat-assistant.md
PRODUCT_SOURCE_FILES=frontend/src/components/patient/AssistantWidget.tsx,frontend/src/components/patient/assistant/ChatPanel.tsx,frontend/src/components/patient/assistant/AssistantTurn.tsx,frontend/src/components/patient/PatientShell.tsx,frontend/src/components/doctor/DoctorShell.tsx
ROUTES_VERIFIED=/patient/*(widget mounted in PatientShell, not a standalone route)
UI_TEXT_VERIFIED="Hỏi trợ lý", "Mở trợ lý AI", "Đóng trợ lý AI"
INVENTED_FEATURES=NONE
NOTES=Đã đọc DoctorShell.tsx và xác nhận nó KHÔNG render AssistantWidget (chỉ có DoctorSidebar/DoctorTopbar) — vì vậy corpus nói rõ trợ lý này chỉ xác nhận có ở khu vực bệnh nhân, chưa xác nhận có ở khu vực bác sĩ, thay vì suy đoán nó dùng chung cho cả hai vai trò.
```

## Ghi chú tổng quát

- Tất cả 10 file trong `data/app_how_to_use/` đều có `INVENTED_FEATURES=NONE` — không route, nút, hay khả năng nào được bịa ra; mọi claim về "không làm được gì" phản ánh đúng những gì chưa tìm thấy bằng chứng trong repo tại thời điểm review (2026-08-25), không phải khẳng định tuyệt đối tính năng không tồn tại ở đâu đó khác trong codebase.
- Cập nhật (verify pass thứ 2): HistoryPanel.tsx, PatientReportDetail.tsx và doctor/trend-reviews/[requestId]/page.tsx nay đã được đọc toàn bộ. Quá trình này phát hiện một lỗi thật đã lọt vào corpus ở vòng đầu: agent kết luận sai "không có chức năng xóa lịch sử" chỉ vì mới đọc HistoryPanel.tsx (trang danh sách) mà chưa đọc PatientReportDetail.tsx (trang chi tiết) — nơi thực sự có nút "Xóa phiếu". Đã sửa lại history.md và analysis-results.md cho đúng. Bài học: một claim "tính năng KHÔNG tồn tại" (dùng cho AH-10) chỉ an toàn khi đã đọc hết mọi file liên quan tới feature đó, không chỉ file đầu tiên tìm thấy.
