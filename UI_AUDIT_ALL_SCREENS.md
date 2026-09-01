# LumiLab — UI Audit All Screens

Ngày audit: 01/09/2026  
Phạm vi: toàn bộ Next.js frontend tại `frontend/src/app` và `frontend/src/components`.

## 1. Tóm tắt điều hành

LumiLab đã có nền tảng lâm sàng tốt: ngôn ngữ tiếng Việt rõ, trạng thái y khoa có mapping tập trung, workflow patient/doctor tương đối đầy đủ, và các cảnh báo nguy kịch không bị hòa lẫn với trạng thái thông thường. Điểm yếu trước đợt refactor này không nằm ở số lượng tính năng mà ở tính hệ thống:

- ba khu vực patient, doctor, admin chưa thật sự dùng cùng một shell;
- public/login trông như một sản phẩm khác với ứng dụng sau đăng nhập;
- glass, radius, shadow và interaction được viết lặp, có nơi quá “holographic” so với bối cảnh y tế;
- thiếu route-level loading, error, 404 và global fallback;
- form controls có kích thước, focus và semantics không đồng đều;
- standard/wide content tier tồn tại về tên nhưng chưa có max-width thực;
- một số màn rỗng tạo khoảng trắng lớn, thiếu điểm neo thị giác và CTA rõ.

Hướng xử lý được chọn là **clinical glass có kiểm soát**: nền sáng dịu, typography tỉnh, dữ liệu lâm sàng nằm trên surface đặc, chỉ dùng kính cho shell, toolbar và vùng định hướng. Không thay đổi API, business logic, auth/RBAC, quyền truy cập dữ liệu, ngưỡng y khoa, toán tử, đơn vị hoặc ý nghĩa NORMAL / LOW / HIGH / CRITICAL.

## 2. Phương pháp audit

- Kiểm kê toàn bộ App Router pages, layouts, shared components và UI primitives.
- Đối chiếu `docs/ui/CLINICAL_LIQUID_GLASS_CONTRACT.md` và các contract test hiện có.
- Kiểm tra mã nguồn cho loading, empty, error, dialog, focus, responsive, reduced motion và mobile navigation.
- Xem lại bằng chứng ảnh chụp UI đã lưu trong repository cho patient dashboard, analysis, history, trends, doctor queue, doctor review và dialogs.
- Chạy lint, unit/contract tests và production build sau thay đổi.

In-app browser không có session khả dụng trong môi trường hiện tại, vì vậy không tạo được bộ screenshot mới. Đây là giới hạn kiểm chứng hình ảnh, không phải giới hạn triển khai.

## 3. Inventory route và trạng thái

| Khu vực | Route | Mục đích | Trạng thái chính đã audit | Kết luận |
|---|---|---|---|---|
| Public | `/` | Landing, giải thích giá trị sản phẩm | default, CTA, disclaimer | Giữ cấu trúc; hợp nhất brand mark, glass và hierarchy |
| Public | `/login` | Login, register, guest, Google, demo | validation, loading, auth error, tab switch | Refactor toàn bộ presentation bằng shared primitives |
| Public | `/privacy` | Chính sách quyền riêng tư | long-form content | Thêm branded reading surface, không đổi nội dung pháp lý |
| Patient | `/patient` | Dashboard | loading, error, empty, guest, verified notice, populated | Refactor state, latest report, quick action và recent rows |
| Patient | `/patient/analysis` | Nhập tay / OCR và xem kết quả | auth loading, empty metrics, validation error, submitting, OCR | Chuẩn hóa tabs, controls, empty/error/loading |
| Patient | `/patient/history` | Lịch sử phiếu và filter ngày | loading, empty, error, populated, pagination | Giữ ba vùng thông tin; nhận token/surface mới |
| Patient | `/patient/history/[reportId]` | Alias chi tiết phiếu | theo `/patient/reports/[reportId]` | Không tạo implementation trùng |
| Patient | `/patient/reports/[reportId]` | Chi tiết phiếu | loading, not found/error, delete confirm, critical ack | Giữ clinical card/status contract |
| Patient | `/patient/trends` | Xu hướng đơn/nhóm, chart/heatmap | catalog loading/error, empty, explanation loading/error | Giữ control surface; tăng content hierarchy và density |
| Patient | `/patient/profile` | Hồ sơ và response style | loading, error, view/edit/saving, empty | Chuyển sang shared input/select/button và option cards |
| Doctor | `/doctor` | Worklist ưu tiên | loading skeleton, error/retry, empty, populated, pagination | Giữ worklist density; nhận shell/brand/surface mới |
| Doctor | `/doctor/reports/[reportId]` | Review phiếu | loading, error, review progress, confirm, completion | Giữ sticky in-flow toolbar và clinical semantics |
| Doctor | `/doctor/trend-reviews` | Danh sách review xu hướng | loading, error, empty, filters, populated | Giữ task model; giảm cảm giác màn rỗng |
| Doctor | `/doctor/trend-reviews/[requestId]` | Review xu hướng chi tiết | loading, error, chart, comment, outcome | Giữ two-column task geometry và review outcome |
| Admin | `/admin` | SLO, trace và observability | loading, error, filters, charts, table, pagination | Chuyển vào shared AppShell; tăng table/surface hierarchy |
| Admin | `/admin/traces/[requestId]` | Trace detail | loading, error, empty detail, populated | Nhận shared shell và branded navigation |
| System | `/_not-found` | 404 | not found + recovery CTA | Bổ sung mới |
| System | route error | Segment failure | error + retry | Bổ sung mới |
| System | global error | Root failure | error + reset | Bổ sung mới |
| System | route loading | Navigation/loading | polite live status | Bổ sung mới |

## 4. Phát hiện theo mức độ ưu tiên

### P0 — Safety / clinical semantics

Không phát hiện yêu cầu sửa logic y khoa trong phạm vi UI. Các vùng sau được xác định là bất biến và đã được giữ nguyên:

- mapping NORMAL / LOW / HIGH / CRITICAL và emergency warning;
- authoritative `is_critical` thay vì suy diễn CRITICAL từ HIGH;
- reference range, critical threshold và comparison behavior;
- analyte aliases, units và conversions;
- source/provenance presentation;
- auth, role routing, RBAC và patient data access.

### P1 — System consistency và task completion

| Phát hiện | Ảnh hưởng | Xử lý |
|---|---|---|
| Admin dùng shell riêng | Người dùng cảm giác chuyển sang công cụ khác | Admin dùng chung `AppShell`, content rail, skip link và branded rail |
| Thiếu loading/error/404 toàn cục | Navigation failure dễ thành màn trắng | Bổ sung `loading.tsx`, `error.tsx`, `global-error.tsx`, `not-found.tsx` |
| `--content-standard` và `--content-wide` là `none` | Tier không có tác dụng, dòng đọc quá dài | Đặt 72rem / 96rem và cùng left rail |
| Login dùng raw controls, target thấp và error dạng text | Trải nghiệm đầu vào yếu, focus không nhất quán | Dùng shared Input/Button/Alert, 44px target, tab semantics |
| Analysis có hai nhóm tab/button tùy biến | Interaction và focus khó dự đoán | Dùng shared `SegmentedControl`, Button, Input, NativeSelect và SystemState |
| Trạng thái rỗng phân mảnh | Khoảng trắng lớn, CTA không nhất quán | Tạo `SystemState` dùng chung cho loading/empty/error/not-found |

### P2 — Visual hierarchy và polish

| Phát hiện | Ảnh hưởng | Xử lý |
|---|---|---|
| Dashboard latest card có glow nhiều lớp | Cảm giác demo/AI hơn là clinical tool | Giảm về một glass focal surface, shadow mỏng, accent rất nhẹ |
| Brand chủ yếu là chữ | Thiếu dấu hiệu nhận diện lặp lại | Tạo code-native `BrandMark` và `BrandLockup` |
| Radius/shadow rải rác | Mất nhịp sản phẩm | Chuẩn hóa token radius, hairline/card/glass/button shadow |
| Cards dữ liệu quá giống nhau | Scan chậm | Thêm accent 2px theo status nhưng không đổi màu/ý nghĩa status |
| Public, auth, product dùng material khác nhau | Brand bị đứt đoạn | Dùng cùng màu nền, glass recipe, border và typography |
| Motion có `transition-all` và hover translate dày | Nhiễu, khó kiểm soát reduced motion | Primitives dùng transition thuộc tính cụ thể; reduced-motion override |

## 5. Audit theo hệ thống component

### Navigation và shell

- Desktop rail sticky, mobile sheet, skip link và topbar đều có mặt.
- Sau refactor, patient/doctor/admin cùng dùng một shell và một content rail.
- Active navigation vẫn dùng `aria-current="page"`; focus ring được làm rõ.
- Brand lockup xuất hiện ở desktop rail và mobile sheet.

### Data surfaces

- Clinical result cards tiếp tục là surface đặc; không đặt critical content lên kính trong suốt.
- Glass chỉ dùng cho shell, toolbar, auth panel và focal summary.
- Worklist, history rows, admin tables có border/shadow/hover cùng nhịp.
- Charts giữ nguyên data, domain, reference/critical bands và tooltip logic.

### Form controls

- Button, Input, Textarea, NativeSelect có minimum target 44px ở size mặc định.
- Login, analysis và profile dùng shared primitives.
- Error dùng live/alert semantics; loading dùng status semantics.
- Native date input vẫn lưu ISO và hiển thị `dd/mm/yyyy` qua lớp presentation hiện có.

### Status và cảnh báo

- `StatusIndicator` vẫn là canonical renderer.
- Màu không phải tín hiệu duy nhất: icon và label vẫn bắt buộc.
- Critical, abnormal, normal, unknown, review và workflow states không bị remap.

### Assistant, dialogs và overlays

- Patient assistant safe area, stop/retry/focus restoration và source disclosure giữ nguyên.
- Sheet/Dialog tiếp tục dùng Base UI primitives; không quay lại browser `alert/confirm`.
- Z-index shell 30/40 và assistant 70 vẫn có thứ tự rõ.

## 6. Responsive audit

- ≥1024px: sidebar cố định, topbar sticky, standard/wide rail áp dụng.
- 768–1023px: mobile/topbar navigation, one-column auth, rail max-width mở.
- <768px: 1rem shell gutter; PageHero/action stacks; history ba vùng xếp dọc; report/trend sidebars về một cột; dashboard focal cards xếp dọc.
- Không phát hiện horizontal scroll bắt buộc ngoài các bảng/chart chủ đích có overflow container.
- Reduced motion tắt page-enter animation và hover translation.

## 7. Kết luận audit

Sau refactor, LumiLab có một visual system duy nhất xuyên public, patient, doctor và admin. Những phần còn cần xác nhận thủ công khi có browser session là typography rendering trên Windows/macOS, pixel-level chart density ở 320/768/1440px và focus traversal trong Google Sign-In iframe. Không có thay đổi nào đối với hành vi y khoa hoặc hợp đồng API.
