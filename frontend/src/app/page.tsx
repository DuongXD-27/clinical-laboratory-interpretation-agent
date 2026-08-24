"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Camera,
  FileQuestion,
  FileText,
  MessageCircle,
  ShieldCheck,
  Stethoscope,
  TrendingUp,
} from "lucide-react";

const features = [
  {
    title: "Giải thích từng chỉ số",
    description: "Mỗi chỉ số có giá trị, khoảng tham chiếu và phần diễn giải viết cho người không chuyên.",
    icon: FileText,
  },
  {
    title: "Đọc phiếu từ ảnh",
    description: "Chụp hoặc tải ảnh phiếu, hệ thống nhận diện chỉ số và cho bạn kiểm tra lại trước khi phân tích.",
    icon: Camera,
  },
  {
    title: "Cảnh báo giá trị nguy kịch",
    description: "Khi phát hiện chỉ số nghiêm trọng, ứng dụng cảnh báo rõ ràng và nhắc bạn liên hệ bác sĩ.",
    icon: AlertTriangle,
  },
  {
    title: "Theo dõi xu hướng",
    description: "Xem biểu đồ biến động của một chỉ số qua nhiều lần xét nghiệm.",
    icon: TrendingUp,
  },
  {
    title: "Câu hỏi mang đi khám",
    description: "Chọn sẵn các câu hỏi phù hợp với kết quả để hỏi bác sĩ, có thể sao chép hoặc in.",
    icon: FileQuestion,
  },
  {
    title: "Bác sĩ phản hồi",
    description: "Bác sĩ có thể xem phiếu, ghi nhận xét lâm sàng và trả lời trực tiếp câu hỏi của bạn.",
    icon: MessageCircle,
  },
];

const steps = [
  ["Nhập kết quả", "Gõ tay từng chỉ số hoặc tải ảnh phiếu lên."],
  ["Xem giải thích", "Nhận diễn giải từng chỉ số kèm nguồn tham khảo."],
  ["Mang đi khám", "Lưu lịch sử, chọn câu hỏi và nhận phản hồi từ bác sĩ."],
];

export default function LandingPage() {

  return (
    <main className="landing-page">
      <nav className="landing-nav" aria-label="Điều hướng trang giới thiệu">
        <div className="landing-container landing-nav-inner">
          <Link href="/" className="landing-logo" aria-label="VMEC">
            <span className="brand-mark" aria-hidden="true">+</span>
            <span>VMEC</span>
          </Link>
          <div className="landing-nav-links">
            <a href="#features">Tính năng</a>
            <a href="#how-it-works">Cách hoạt động</a>
            <a href="#doctor">Dành cho bác sĩ</a>
          </div>
          {/* Thanh này KHÔNG đổi theo phiên đăng nhập, có chủ ý.
              Trang giới thiệu là trang công khai; hiện tên tài khoản ở đây là
              để lộ danh tính người dùng cho bất kỳ ai đi ngang qua màn hình —
              với một ứng dụng y tế thì riêng việc "người này có tài khoản" đã
              là thông tin không nên khoe.
              Cũng KHÔNG tự chuyển hướng người đã đăng nhập: trước đây trang
              này `router.replace()` sang trang của vai trò, nên link "Về trang
              giới thiệu" ở màn đăng nhập bấm vào là bị đá đi ngay. */}
          <div className="landing-nav-actions">
            <Link href="/login" className="text-button">Đăng nhập</Link>
            <Link href="/login?tab=register" className="landing-primary-link">Bắt đầu miễn phí</Link>
          </div>
        </div>
      </nav>

      <section className="landing-container landing-hero">
        <div className="landing-hero-copy">
          <span className="landing-badge">Miễn phí · Không cần tài khoản để dùng thử</span>
          <h1>Hiểu rõ phiếu xét nghiệm của bạn, bằng tiếng Việt</h1>
          <p>
            Nhập kết quả hoặc tải ảnh phiếu xét nghiệm. Ứng dụng giải thích từng chỉ số dễ hiểu,
            cảnh báo giá trị bất thường và giúp bạn chuẩn bị câu hỏi mang đi khám.
          </p>
          <div className="landing-hero-actions">
            <Link href="/login" className="landing-primary-link">Dùng thử ngay - không cần đăng ký</Link>
            <Link href="/login" className="landing-secondary-link">Đăng nhập</Link>
          </div>
          <p className="landing-privacy-note">
            <span aria-hidden="true">[]</span>
            Chế độ khách không lưu bất kỳ dữ liệu nào.
          </p>
        </div>

        <div className="landing-demo-card" aria-label="Minh họa kết quả xét nghiệm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-muted-foreground">Chỉ số xét nghiệm</p>
              <h2 className="mt-1 text-2xl font-bold text-foreground">WBC</h2>
            </div>
            <span className="status-badge status-abnormal">Cao</span>
          </div>
          <p className="mt-5 text-4xl font-bold text-foreground">
            12.4 <span className="text-base font-medium text-muted-foreground">10^9/L</span>
          </p>
          <div className="landing-range" aria-hidden="true">
            <span />
          </div>
          <div className="mt-2 flex justify-between text-xs text-muted-foreground">
            <span>4.0</span>
            <span>Khoảng tham chiếu</span>
            <span>10.0</span>
          </div>
          <div className="mt-6 rounded-xl border border-[var(--status-abnormal-border)] bg-[var(--status-abnormal-bg)] p-4 text-sm leading-6 text-[var(--status-abnormal-fg)]">
            <p className="font-semibold text-foreground">Giá trị cao hơn ngưỡng bình thường.</p>
            <p className="mt-1">Kết quả này có thể liên quan đến viêm, nhiễm trùng hoặc phản ứng của cơ thể.</p>
          </div>
        </div>
      </section>

      <section className="landing-trust-band" aria-label="Cam kết sản phẩm">
        <div className="landing-container landing-trust-grid">
          <div><strong>VI</strong> Giải thích bằng tiếng Việt dễ hiểu</div>
          <div><strong><ShieldCheck className="h-4 w-4" /></strong> Có trích dẫn nguồn y khoa</div>
          <div><strong><Stethoscope className="h-4 w-4" /></strong> Không thay thế chẩn đoán của bác sĩ</div>
        </div>
      </section>

      <section id="features" className="landing-container landing-section">
        <div className="landing-section-heading">
          <span className="eyebrow">Tính năng</span>
          <h2>Một nơi để hiểu, lưu và chuẩn bị cho buổi khám</h2>
        </div>
        <div className="landing-feature-grid">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
            <article key={feature.title} className="landing-feature-card">
              <div className="landing-icon" aria-hidden="true">
                <Icon className="h-5 w-5" />
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </article>
            );
          })}
        </div>
      </section>

      <section id="how-it-works" className="landing-container landing-section">
        <div className="landing-section-heading">
          <span className="eyebrow">Cách hoạt động</span>
          <h2>Từ phiếu xét nghiệm đến câu hỏi mang đi khám</h2>
        </div>
        <div className="landing-steps">
          {steps.map(([title, description], index) => (
            <article key={title} className="landing-step">
              <span aria-hidden="true">{index + 1}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="doctor" className="landing-doctor-section">
        <div className="landing-container landing-doctor-grid">
          <div className="landing-doctor-panel" aria-hidden="true">
            <div className="h-3 w-28 rounded-full bg-[var(--brand-soft)]" />
            <div className="mt-5 grid gap-3">
              <div className="h-12 rounded-xl bg-[var(--surface)]" />
              <div className="h-12 rounded-xl bg-[var(--surface)]" />
              <div className="h-24 rounded-xl bg-[var(--brand-soft)]" />
            </div>
          </div>
          <div>
            <span className="eyebrow">Dành cho bác sĩ</span>
            <h2>Dành cho bác sĩ</h2>
            <p>
              Portal bác sĩ hỗ trợ xem phiếu xét nghiệm của bệnh nhân, ghi nhận xét lâm sàng
              và trả lời trực tiếp những câu hỏi bệnh nhân đã chọn.
            </p>
            <Link href="/login" className="landing-text-link">Đăng nhập portal bác sĩ -&gt;</Link>
            <p className="mt-3 text-sm text-muted-foreground">Tài khoản bác sĩ do quản trị viên cấp.</p>
          </div>
        </div>
      </section>

      <section className="landing-container">
        <div className="landing-disclaimer">
          <h2>Lưu ý quan trọng</h2>
          <p>
            Ứng dụng cung cấp thông tin tham khảo được tạo bởi AI, không phải chẩn đoán y khoa
            và không thay thế ý kiến của bác sĩ. Trong trường hợp khẩn cấp, hãy liên hệ cơ sở y tế
            hoặc bác sĩ chuyên môn ngay.
          </p>
        </div>
      </section>

      <section className="landing-cta">
        <div className="landing-container">
          <h2>Bắt đầu đọc phiếu xét nghiệm theo cách dễ hiểu hơn</h2>
          <Link href="/login" className="landing-white-link">Dùng thử ngay</Link>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="landing-container landing-footer-inner">
          <div className="landing-logo">
            <span className="brand-mark" aria-hidden="true">+</span>
            <span>VMEC</span>
          </div>
          <p>© 2026 VMEC. Thông tin chỉ mang tính tham khảo.</p>
          {/* Google kiểm trang chủ có dẫn tới chính sách quyền riêng tư không
              trước khi cho publish OAuth app. Nhưng lý do chính vẫn là người
              dùng phải tìm được nó mà không cần đoán URL. */}
          <Link href="/privacy" className="landing-text-link">
            Chính sách quyền riêng tư
          </Link>
        </div>
      </footer>
    </main>
  );
}
