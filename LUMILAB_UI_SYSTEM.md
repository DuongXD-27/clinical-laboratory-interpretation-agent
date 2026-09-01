# LumiLab UI System

Phiên bản: 1.0 — Clinical Glass / Quiet Medical Intelligence

## 1. Tinh thần thiết kế

LumiLab phải tạo cảm giác **bình tĩnh, chính xác và đồng hành**, không lạnh như HIS truyền thống và không phô diễn như một AI demo. Giao diện dùng ba lớp:

1. **Foundation** — nền xanh-xám rất nhạt, typography tối, khoảng thở rộng.
2. **Navigation glass** — shell, topbar, auth và control surfaces có blur nhẹ để tạo chiều sâu.
3. **Clinical solid** — kết quả, cảnh báo, bảng và quyết định lâm sàng luôn nằm trên surface gần như đặc.

Glass là vật liệu định hướng, không phải vật liệu cho dữ liệu nguy kịch.

## 2. Brand signature

`BrandMark` gồm hai “lens” trong suốt giao nhau quanh một clinical core. Hình ảnh này gợi ánh sáng, phòng xét nghiệm và việc chuyển dữ liệu thành hiểu biết mà không dùng dấu thập y tế phổ thông.

Quy tắc:

- Dùng `BrandLockup` trong public nav, auth, sidebar và mobile sheet.
- Không tự vẽ lại logo bằng chữ `+`, emoji hoặc icon khác.
- Mark mặc định 36px; không nhỏ hơn 28px.
- Context line dùng cho tên không gian: bệnh nhân, bác sĩ, vận hành.

## 3. Token architecture

### Primitive layer

| Nhóm | Token chính | Giá trị định hướng |
|---|---|---|
| Neutral | `--background` | `#f4f8fa` |
| Surface | `--surface` | `#ffffff` |
| Ink | `--foreground` | `#14262d` |
| Muted ink | `--foreground-muted` | `#687d86` |
| Border | `--border` | `#d7e3e7` |
| Teal | `--brand` | `#087d87` |
| Teal dark | `--brand-strong` | `#075f69` |
| Cyan/blue/violet atmosphere | `--holo-*` | opacity thấp, chỉ cho ambient depth |

### Semantic layer

- `--surface-subtle`: grouping, disabled và low-emphasis regions.
- `--glass-surface`: shell/control material.
- `--brand-soft`: selected/assistive state, không đại diện NORMAL.
- `--status-normal-*`: trong khoảng tham chiếu.
- `--status-abnormal-*`: LOW/HIGH cần lưu ý.
- `--status-critical-*`: CRITICAL/emergency presentation.
- `--status-unknown-*`: thiếu dữ liệu hoặc không thể đánh giá.

Không dùng brand green/teal để thay thế clinical NORMAL.

### Component layer

- Radius: 10 / 12 / 14 / 18px qua `--radius-sm/md/lg/glass`.
- Shadow: `--shadow-hairline`, `--shadow-card`, `--shadow-glass`, `--shadow-button`.
- Control default: min-height 44px.
- Shell: sidebar 16.5rem; topbar 4rem.
- Content tier: standard 72rem; wide 96rem.

## 4. Typography

Font stack ưu tiên `Aptos`, `Segoe UI Variable Text`, `Segoe UI`, sau đó system sans. Mục tiêu là render tiếng Việt rõ trên thiết bị hiện có, không tạo network dependency cho font.

| Cấp | Token / rule | Dùng cho |
|---|---|---|
| Page title | `--type-page-title`, 720 | mục tiêu trang |
| Section | `--type-section-title`, 700 | nhóm workflow |
| Card title | `--type-card-title`, 650–700 | entity/data card |
| Body | 14–16px, line-height 1.5–1.65 | nội dung giải thích |
| Metadata | 12–13px | thời gian, ID, đơn vị phụ |
| Eyebrow | 12px uppercase, tracking .08em | context, không phải heading thay thế |

Quy tắc:

- Mỗi page chỉ có một H1 trong content.
- Topbar dùng `p/span`, không tạo H1 thứ hai.
- Numeric medical values dùng tabular numbers khi so sánh theo cột.
- Không dùng gradient text.

## 5. Layout system

```text
AppShell
├── RoleSidebar (desktop)
└── AppFrame
    ├── RoleTopbar (sticky)
    └── Main
        └── ContentRail (standard | wide)
            ├── PageHero
            └── Page workflow
```

- Standard và wide cùng neo trái; width thay đổi nhưng điểm bắt đầu không nhảy.
- Patient dashboard/profile dùng standard.
- Analysis/history/report/trends/doctor/admin dùng wide khi cần bảng/chart.
- PageHero chứa eyebrow, H1, description, action group và `ClinicalSignal` trang trí.

## 6. Material hierarchy

| Material | Dùng | Không dùng |
|---|---|---|
| Foundation | page background | card data |
| Glass | sidebar, topbar, auth, trend controls, focal summary | critical cards, dense tables |
| Clinical solid | result cards, finding cards, worklist rows, tables | decorative background |
| Semantic tint | status strip, alert, verified notice | full-page decoration |

Không xếp glass lên glass quá hai lớp. Blur mặc định 18–24px, opacity đủ để text đạt contrast.

## 7. Components

### BrandLockup

- Props: `context`, `compact`.
- Context không phải tên role kỹ thuật; dùng ngôn ngữ người dùng.

### AppShell / ContentRail / PageHero

- Role: patient, doctor, admin.
- Có skip link và main focus target.
- Atmosphere luôn `aria-hidden` và không nhận pointer events.

### Button

- `primary`: một hành động chính mỗi vùng.
- `outline`: secondary/retry/cancel.
- `secondary`: navigation/assistive action.
- `ghost`: low emphasis/reset.
- `destructive`: destructive action, không dùng cho clinical CRITICAL label.
- Icon dùng `data-icon="inline-start|inline-end"` và Lucide.

### Input / Textarea / NativeSelect

- Min-height 44px; background solid; focus ring teal 3px mềm.
- Label luôn hiển thị, placeholder không thay label.
- Error kết nối bằng `aria-invalid` và alert/hint gần field khi có.

### SystemState

| Kind | Role | Nội dung |
|---|---|---|
| loading | status + polite | hành động đang diễn ra |
| empty | status | vì sao rỗng + CTA phù hợp |
| error | alert | không hoàn tất + recovery |
| not-found | status | route không tồn tại + đường về |

Không dùng skeleton cho hành động tức thời; skeleton dành cho cấu trúc dữ liệu có hình dạng dự đoán được.

### StatusIndicator

Canonical và bất biến. Mọi status cần icon + label; màu chỉ là tín hiệu phụ. `critical` chỉ đến từ authoritative clinical state.

### Clinical cards

- Border 1px, solid surface, shadow card.
- Accent trái 2px theo status để tăng tốc scan.
- Critical dùng red family hiện có, không phát sáng, không animate.
- Explanation có progressive disclosure độc lập và source footer.

### Tables và charts

- Header nền subtle, row hover nhẹ, numeric alignment nhất quán.
- Horizontal scroll nằm trong table wrapper, không đẩy viewport.
- Reference/critical bands không thay đổi màu ngữ nghĩa.
- Empty chart phải có lý do cụ thể, không chỉ “không có dữ liệu”.

## 8. Spacing và density

- Page section gap: 24–36px.
- Card gap: 16–20px.
- Card padding: 20–24px.
- Dense table cells: 10–14px vertical.
- Action group: 12–16px.
- Không dùng `space-y-*` làm API component mới; component mới nên có class semantic và `gap` rõ.

## 9. Interaction và motion

- Fast 150ms, normal 200ms, slow tối đa 250ms.
- Chỉ transition thuộc tính cần thiết; không dùng `transition-all` trong primitive mới.
- Hover elevation tối đa 1–2px.
- Page enter 220ms, translate 5px; tắt hoàn toàn với reduced motion.
- Focus-visible phải rõ hơn hover.
- Disabled không nhận pointer event và có cursor/opacity phù hợp.

## 10. Responsive rules

- Desktop ≥1024px: rail + sticky topbar.
- Tablet <1024px: sidebar ẩn, Sheet navigation, content full rail.
- Mobile <768px: 16px gutter, one-column forms/cards, action group có thể full width.
- Charts/tables dùng internal overflow; label và CTA không được truncate mất nghĩa.
- Touch targets tối thiểu 44×44px ở action chính.

## 11. Accessibility contract

- Skip link cho cả ba authenticated shells.
- `aria-current` cho active navigation.
- Tabs có `tablist/tab`, `aria-selected`, roving tab index khi dùng shared SegmentedControl.
- Loading có `role=status`; error có `role=alert`.
- Icon trang trí `aria-hidden`; icon-only control có accessible name.
- Không dùng color-only status.
- Tôn trọng reduced motion.
- Dialog/Sheet chịu trách nhiệm focus trap và restoration qua Base UI.

## 12. Governance

Mọi thay đổi UI liên quan dữ liệu xét nghiệm phải qua hai câu hỏi:

1. Thay đổi có làm khác ý nghĩa medical state, threshold, unit, source hay emergency behavior không?
2. Thay đổi có làm user hiểu một AI explanation là chẩn đoán hoặc quyết định của bác sĩ không?

Nếu câu trả lời có thể là “có”, thay đổi nằm ngoài phạm vi styling và cần review chuyên biệt.
