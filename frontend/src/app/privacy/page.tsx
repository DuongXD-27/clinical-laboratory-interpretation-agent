import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Chính sách quyền riêng tư · VMEC-05",
  description:
    "Dữ liệu xét nghiệm của bạn được lưu ở đâu, gửi cho ai, giữ bao lâu và ai xem được.",
};

/** Trang chính sách quyền riêng tư.
 *
 * Bắt buộc phải có để publish OAuth app của Google, nhưng nội dung được viết
 * từ hành vi THẬT của hệ thống chứ không phải mẫu chung: mỗi đoạn dưới đây
 * tương ứng với một luồng dữ liệu đã kiểm trong mã nguồn và cấu hình
 * production. Không hứa điều gì mà code chưa làm.
 *
 * Là server component, không có `"use client"`: trang này phải đọc được khi
 * chưa đăng nhập, và Google sẽ tự động tải nó về để kiểm tra.
 */

const UPDATED = "23/08/2026";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="m-0 text-lg font-semibold tracking-tight text-[var(--foreground)]">{title}</h2>
      <div className="mt-2 flex flex-col gap-3 text-sm leading-relaxed text-[var(--foreground-secondary)]">
        {children}
      </div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main className="min-h-dvh bg-[var(--background)] px-5 py-10">
      <article className="mx-auto w-full max-w-3xl">
        <Link href="/" className="text-sm font-medium text-[var(--brand-strong)] hover:underline">
          ← Về trang giới thiệu
        </Link>

        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-[var(--foreground)] lg:text-3xl">
          Chính sách quyền riêng tư
        </h1>
        <p className="mt-2 text-sm text-[var(--foreground-muted)]">Cập nhật lần cuối: {UPDATED}</p>

        <p className="mt-6 text-sm leading-relaxed text-[var(--foreground-secondary)]">
          VMEC-05 là ứng dụng giải thích kết quả xét nghiệm bằng tiếng Việt. Trang này mô tả đúng những gì
          hệ thống thực sự làm với dữ liệu của bạn — lưu ở đâu, gửi cho ai, giữ bao lâu. Nếu có điểm nào
          trong đây không khớp với hành vi thật của ứng dụng, hãy báo cho chúng tôi.
        </p>

        <Section title="1. Dữ liệu chúng tôi thu thập">
          <p>
            <strong>Tài khoản:</strong> tên đăng nhập, mật khẩu (chỉ lưu dạng băm bcrypt, không lưu bản
            gốc), và email nếu bạn tự điền. Nếu đăng nhập bằng Google, chúng tôi nhận email đã được Google
            xác minh và họ tên hiển thị trên tài khoản Google của bạn. Chúng tôi không nhận mật khẩu Google
            và không truy cập được bất kỳ dữ liệu nào khác trong tài khoản đó.
          </p>
          <p>
            <strong>Kết quả xét nghiệm:</strong> tên chỉ số, giá trị, đơn vị, ngày xét nghiệm, cùng tuổi và
            giới tính bạn nhập để hệ thống chọn đúng khoảng tham chiếu.
          </p>
          <p>
            <strong>Ảnh phiếu xét nghiệm:</strong> nếu bạn dùng chức năng đọc phiếu từ ảnh. Xem mục 3 về
            cách ảnh được xử lý.
          </p>
          <p>
            <strong>Dữ liệu vận hành:</strong> mỗi lượt gọi tới máy chủ được ghi lại một dòng gồm đường
            dẫn, mã trạng thái, thời gian xử lý và vai trò tài khoản. Dòng này{" "}
            <strong>không chứa</strong> tên chỉ số, giá trị xét nghiệm, tên đăng nhập hay nội dung bạn nhập.
          </p>
        </Section>

        <Section title="2. Dữ liệu được lưu ở đâu">
          <p>
            Cơ sở dữ liệu đặt tại <strong>Frankfurt, Đức</strong> (Neon, hạ tầng AWS khu vực
            eu-central-1). Máy chủ ứng dụng đặt tại châu Âu (Railway). Giao diện web phục vụ qua Vercel.
          </p>
          <p>
            Nghĩa là kết quả xét nghiệm của bạn được lưu bên ngoài Việt Nam. Chúng tôi chọn khu vực này để
            máy chủ và cơ sở dữ liệu nằm gần nhau, giúp ứng dụng phản hồi nhanh.
          </p>
        </Section>

        <Section title="3. Dữ liệu gửi cho bên thứ ba">
          <p>
            Ứng dụng dùng dịch vụ của bên thứ ba cho ba việc. Đây là phần bạn nên đọc kỹ nhất.
          </p>
          <p>
            <strong>Giải thích kết quả — OpenAI.</strong> Để viết lời giải thích dễ hiểu, hệ thống gửi tên
            chỉ số, giá trị, đơn vị, khoảng tham chiếu, cùng tuổi và giới tính của bạn tới mô hình{" "}
            <code className="font-mono text-xs">gpt-4o-mini</code> của OpenAI. Chúng tôi không gửi tên,
            email hay bất kỳ thông tin nhận dạng nào khác.
          </p>
          <p>
            <strong>Đọc phiếu từ ảnh — OpenRouter.</strong> Nếu bạn tải ảnh phiếu lên, ảnh đó được chuyển
            tới OpenRouter để trích xuất chữ. Ảnh <strong>không được lưu xuống ổ đĩa máy chủ của chúng
            tôi</strong> và không được lưu vào cơ sở dữ liệu — nó chỉ tồn tại trong bộ nhớ trong lúc xử lý.
            Chúng tôi chỉ lưu lại tên tệp, độ tin cậy nhận dạng và phần chữ đã trích xuất. Chức năng này
            luôn yêu cầu bạn tick xác nhận trước khi tải ảnh lên, chính vì lý do này. Chúng tôi không kiểm
            soát được OpenRouter lưu ảnh bao lâu.
          </p>
          <p>
            <strong>Giám sát vận hành — Langfuse.</strong> Hệ thống gửi số liệu về từng lượt gọi mô hình
            ngôn ngữ (thời gian, số token, mã lỗi) tới Langfuse để phát hiện sự cố. Nội dung câu hỏi và câu
            trả lời <strong>được che trước khi gửi</strong>: giá trị xét nghiệm, tên chỉ số, tuổi và giới
            tính của bạn không rời khỏi hệ thống qua đường này.
          </p>
        </Section>

        <Section title="4. Chế độ dùng thử không tài khoản">
          <p>
            Nếu bạn chọn &ldquo;Dùng thử với tư cách khách&rdquo;, hệ thống <strong>không tạo tài khoản và
            không lưu bất kỳ dữ liệu nào</strong> của bạn vào cơ sở dữ liệu. Phiên khách tồn tại trong một
            mã phiên tạm, hết hạn sau 2 giờ, và mọi thứ mất theo nó.
          </p>
          <p>
            Lưu ý: kết quả bạn nhập trong chế độ khách vẫn được gửi tới OpenAI để tạo lời giải thích, giống
            như khi đã đăng nhập.
          </p>
        </Section>

        <Section title="5. Ai xem được dữ liệu của bạn">
          <p>
            <strong>Bạn</strong> xem được toàn bộ phiếu của mình. Hệ thống ràng buộc mỗi phiếu với đúng một
            tài khoản; bạn không thể xem phiếu của người khác kể cả khi biết mã phiếu.
          </p>
          <p>
            <strong>Bác sĩ</strong> trong hệ thống xem được phiếu để đưa ra ý kiến chuyên môn và trả lời
            câu hỏi bạn gửi.
          </p>
          <p>
            <strong>Quản trị viên</strong> chỉ xem được dữ liệu vận hành mô tả ở mục 1 —{" "}
            <strong>không xem được kết quả xét nghiệm</strong>. Đây là ràng buộc trong mã nguồn, không phải
            quy định nội bộ.
          </p>
        </Section>

        <Section title="6. Thời gian lưu giữ">
          <p>
            Phiếu xét nghiệm và tài khoản được giữ cho tới khi bạn yêu cầu xoá. Dữ liệu vận hành ở mục 1
            được tự động xoá sau <strong>14 ngày</strong>. Dữ liệu phiên khách không được lưu nên không có
            gì để xoá.
          </p>
        </Section>

        <Section title="7. Quyền của bạn">
          <p>
            Bạn có thể yêu cầu xem, sửa hoặc xoá dữ liệu của mình. Khi xoá tài khoản, toàn bộ phiếu xét
            nghiệm gắn với tài khoản đó bị xoá theo.
          </p>
          <p>
            Chúng tôi không bán dữ liệu, không dùng dữ liệu của bạn để huấn luyện mô hình, và không dùng
            cho quảng cáo.
          </p>
        </Section>

        <Section title="8. Điều ứng dụng này không làm">
          <p>
            VMEC-05 <strong>không chẩn đoán bệnh, không kê đơn và không thay thế bác sĩ</strong>. Lời giải
            thích do hệ thống tạo ra nhằm giúp bạn hiểu con số trên phiếu và chuẩn bị câu hỏi khi đi khám.
            Mọi quyết định về sức khoẻ cần có ý kiến của nhân viên y tế.
          </p>
        </Section>

        <Section title="9. Liên hệ">
          <p>
            Có câu hỏi về chính sách này, hoặc muốn yêu cầu xoá dữ liệu, hãy liên hệ nhóm phát triển
            VMEC-05 qua email hỗ trợ ghi trên màn hình đăng nhập bằng Google.
          </p>
        </Section>

        <p className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--foreground-muted)]">
          Chính sách này mô tả hệ thống tại thời điểm cập nhật ở đầu trang. Khi luồng dữ liệu thay đổi,
          trang này được sửa theo.
        </p>
      </article>
    </main>
  );
}
