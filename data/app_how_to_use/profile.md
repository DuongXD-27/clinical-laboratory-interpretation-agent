```
feature: profile
role: patient
route: /patient/profile
section: personal-info
```

## Feature này dùng để làm gì?

Cho bệnh nhân xem và chỉnh sửa thông tin cá nhân (họ tên, ngày sinh, giới tính, email), dùng để "đối chiếu khi xem các phiếu đã lưu" (nguyên văn mô tả trên trang).

## Người dùng tìm ở đâu?

Menu điều hướng bên trái khu vực bệnh nhân: mục **"Thông tin cá nhân"** → route `/patient/profile`.

## Các bước sử dụng?

1. Vào mục "Thông tin cá nhân" trên menu.
2. Xem thông tin hiện tại: Họ tên, Ngày sinh, Giới tính, Email (mặc định các trường bị khóa/disabled).
3. Bấm nút **"Chỉnh sửa"** để mở khóa các trường nhập.
4. Sửa các trường cần thiết: Họ tên, Ngày sinh, Giới tính (Nam/Nữ/Khác), Email.
5. Bấm **"Lưu thay đổi"** để lưu, hoặc **"Hủy"** để hủy bỏ thay đổi và quay lại giá trị cũ.
6. Cuối trang hiển thị "Tạo lúc" và "Cập nhật lúc" của hồ sơ.

## Điều kiện/giới hạn?

- Chỉ dành cho tài khoản bệnh nhân đã đăng nhập (`getRole() === "patient"`) — **không có trong menu của guest**.
- Email nếu nhập phải chứa ký tự "@", nếu không hệ thống báo lỗi "Email chưa hợp lệ."
- Các trường có thể để trống (placeholder "Chưa cập nhật") — không bắt buộc phải điền đầy đủ.

## Không làm được gì?

- Không đổi được **username** hay **mật khẩu** tại trang này (chỉ có Họ tên, Ngày sinh, Giới tính, Email trong form — không có trường username/password).
- Không xóa được tài khoản từ trang này.
- Người dùng khách (guest) không có trang Thông tin cá nhân để chỉnh sửa.
