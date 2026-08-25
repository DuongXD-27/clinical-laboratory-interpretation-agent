"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { formatMoment } from "@/lib/patientUi.mjs";

type PatientProfile = {
  patient_id: number;
  username: string;
  full_name?: string | null;
  date_of_birth?: string | null;
  sex?: "male" | "female" | "other" | null;
  email?: string | null;
  created_at: string;
  updated_at: string;
};

export default function PatientProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [form, setForm] = useState({ full_name: "", date_of_birth: "", sex: "male", email: "" });
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
    <div className="profile-page-layout">
      <div className="page-section-heading">
        <div>
          <span className="eyebrow">Tài khoản bệnh nhân</span>
          <h1>Thông tin cá nhân</h1>
          <p>Quản lý thông tin dùng để đối chiếu khi xem các phiếu đã lưu.</p>
        </div>
      </div>
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
