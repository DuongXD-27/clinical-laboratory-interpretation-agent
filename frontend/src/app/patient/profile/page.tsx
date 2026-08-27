"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { formatMoment } from "@/lib/patientUi.mjs";
import { RESPONSE_STYLES } from "@/lib/responseStyleUi.mjs";
import PatientPageHeader from "@/components/patient/PatientPageHeader";

type PatientProfile = {
  patient_id: number;
  username: string;
  full_name?: string | null;
  date_of_birth?: string | null;
  sex?: "male" | "female" | "other" | null;
  email?: string | null;
  response_style?: "concise" | "simple" | "detailed" | null;
  created_at: string;
  updated_at: string;
};

export default function PatientProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [form, setForm] = useState({ full_name: "", date_of_birth: "", sex: "male", email: "", response_style: "simple" });
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch("/api/v1/patient/me/profile");
      if (response.status === 401) {
        clearSession();
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Chưa tải được hồ sơ cá nhân.");
      const data = await response.json() as PatientProfile;
      setProfile(data);
      setForm({
        full_name: data.full_name ?? "",
        date_of_birth: data.date_of_birth ?? "",
        sex: data.sex ?? "male",
        email: data.email ?? "",
        response_style: data.response_style ?? "simple",
      });
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Chưa tải được hồ sơ cá nhân.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch profile after client auth guard.
    void loadProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once after auth guard.
  }, [router]);

  const save = async () => {
    if (form.email && !form.email.includes("@")) {
      setError("Email chưa hợp lệ.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await authFetch("/api/v1/patient/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: form.full_name || null,
          date_of_birth: form.date_of_birth || null,
          sex: form.sex || null,
          email: form.email || null,
          response_style: form.response_style || "simple",
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Chưa lưu được hồ sơ.");
      }
      const data = await response.json() as PatientProfile;
      setProfile(data);
      setEditing(false);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Chưa lưu được hồ sơ.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="patient-page-layout profile-page-layout">
      <PatientPageHeader
        eyebrow="Tài khoản bệnh nhân"
        title="Thông tin cá nhân"
        description="Quản lý thông tin dùng để đối chiếu khi xem các phiếu đã lưu."
      />
      <section className="patient-card p-5 sm:p-7">
          {loading ? (
            <div className="loading-message" role="status">Đang tải hồ sơ...</div>
          ) : error ? (
            <div role="alert" className="error-message">{error}</div>
          ) : profile ? (
            <>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="section-heading">
                  <span className="eyebrow">Hồ sơ bệnh nhân</span>
                  <h2>{profile.full_name || profile.username}</h2>
                  <p>Thông tin dùng để đối chiếu khi xem lại các phiếu đã lưu.</p>
                </div>
                {!editing && (
                  <button type="button" onClick={() => setEditing(true)} className="primary-button w-full sm:w-auto">
                    Chỉnh sửa
                  </button>
                )}
              </div>

              <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <label className="field-label">
                  Họ tên
                  <input disabled={!editing} value={form.full_name} placeholder="Chưa cập nhật" onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))} className="form-control mt-2" />
                </label>
                <label className="field-label">
                  Ngày sinh
                  <input disabled={!editing} type="date" value={form.date_of_birth} onChange={(event) => setForm((current) => ({ ...current, date_of_birth: event.target.value }))} className="form-control mt-2" />
                </label>
                <label className="field-label">
                  Giới tính
                  <select disabled={!editing} value={form.sex} onChange={(event) => setForm((current) => ({ ...current, sex: event.target.value }))} className="form-control mt-2">
                    <option value="male">Nam</option>
                    <option value="female">Nữ</option>
                    <option value="other">Khác</option>
                  </select>
                </label>
                <label className="field-label">
                  Email
                  <input disabled={!editing} type="email" value={form.email} placeholder="Chưa cập nhật" onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} className="form-control mt-2" />
                </label>
              </div>

              <div className="mt-8 border-t pt-6">
                <div className="section-heading mb-4">
                  <span className="eyebrow">Tùy chọn hiển thị</span>
                  <h3 className="text-lg font-semibold">Cách LumiLab giải thích cho bạn</h3>
                  <p className="text-sm text-gray-500">Chọn phong cách phản hồi phù hợp nhất với nhu cầu đọc hiểu kết quả xét nghiệm của bạn.</p>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {RESPONSE_STYLES.map((style) => (
                    <label
                      key={style.id}
                      className={`flex flex-col p-4 rounded-lg border cursor-pointer transition-colors ${
                        form.response_style === style.id ? "border-emerald-600 bg-emerald-50/50" : "border-gray-200 hover:border-gray-300"
                      } ${!editing ? "opacity-90 cursor-default" : ""}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-gray-900">{style.title}</span>
                        <input
                          type="radio"
                          name="response_style"
                          value={style.id}
                          disabled={!editing}
                          checked={form.response_style === style.id}
                          onChange={(e) => setForm((curr) => ({ ...curr, response_style: e.target.value }))}
                          className="h-4 w-4 text-emerald-600 focus:ring-emerald-500"
                        />
                      </div>
                      <p className="text-xs text-gray-500">{style.description}</p>
                    </label>
                  ))}
                </div>
              </div>

              {editing && (
                <div className="mt-6 flex flex-wrap gap-2">
                  <button type="button" onClick={save} disabled={saving} className="primary-button">
                    {saving ? "Đang lưu..." : "Lưu thay đổi"}
                  </button>
                  <button type="button" onClick={() => {
                    setEditing(false);
                    setForm({
                      full_name: profile.full_name ?? "",
                      date_of_birth: profile.date_of_birth ?? "",
                      sex: profile.sex ?? "male",
                      email: profile.email ?? "",
                      response_style: profile.response_style ?? "simple",
                    });
                  }} className="secondary-button">
                    Hủy
                  </button>
                </div>
              )}

              <div className="profile-meta mt-6">
                <p>Tạo lúc: {formatMoment(profile.created_at)}</p>
                <p>Cập nhật lúc: {formatMoment(profile.updated_at)}</p>
              </div>
            </>
          ) : (
            <div className="empty-metrics">Không tìm thấy hồ sơ bệnh nhân.</div>
          )}
      </section>
    </div>
  );
}
