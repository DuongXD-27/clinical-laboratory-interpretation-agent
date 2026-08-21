/** Trang chủ của từng vai trò.
 *
 * Dùng bảng tra thay vì chuỗi ba ngôi. Thêm vai trò thứ tư vào một biểu thức
 * `role === "doctor" ? "/doctor" : "/patient"` thì vai trò mới âm thầm rơi vào
 * nhánh else — và triệu chứng không hề chỉ về chỗ sai. Chuyện đã xảy ra thật:
 * admin bị đẩy sang `/patient`, trang đó thấy vai trò không khớp nên đá tiếp
 * về `/login`.
 *
 * Đặt ở `lib/` chứ không nằm trong một page: bản đầu tôi để bảng này ngay trong
 * `login/page.tsx`, nên `app/page.tsx` không dùng lại được và tiếp tục dùng
 * chuỗi ba ngôi cũ. Một bảng dùng chung thì chỗ thứ năm không thể lệch.
 *
 * Là `.mjs` theo đúng quy ước của thư mục: logic thuần tách khỏi component để
 * `npm test` chạy được bằng `node --test`.
 */
const HOME_BY_ROLE = {
  patient: "/patient",
  doctor: "/doctor",
  admin: "/admin",
  // Khách không có trang riêng: phiên khách chỉ dùng được màn phân tích, không
  // có lịch sử để mở.
  guest: "/patient",
};

export const DEFAULT_HOME = "/patient";

export function homeForRole(role) {
  if (!role) return DEFAULT_HOME;
  return HOME_BY_ROLE[role] ?? DEFAULT_HOME;
}

export const KNOWN_ROLES = Object.keys(HOME_BY_ROLE);
