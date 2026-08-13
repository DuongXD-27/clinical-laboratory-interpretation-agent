"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";

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
        router.replace("/");
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
      router.replace("/");
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
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div>
            <h1>Hồ sơ cá nhân</h1>
            <p>Thông tin bệnh nhân dùng cho các lần xét nghiệm đã lưu.</p>
          </div>
          <Link href="/patient" className="secondary-button px-3 py-2.5">Dashboard</Link>
        </header>

        <section className="patient-card p-5 sm:p-7">
          {loading ? (
            <div className="loading-message" role="status">Đang tải hồ sơ...</div>
          ) : error ? (
            <div role="alert" className="error-message">{error}</div>
          ) : profile ? (
            <>
              <div className="section-heading">
                <span className="eyebrow">Patient Profile</span>
                <h2>{profile.full_name || profile.username}</h2>
                <p>Patient ID: {profile.patient_id}</p>
              </div>

              <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <label className="field-label">
                  Họ tên
                  <input disabled={!editing} value={form.full_name} onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))} className="form-control mt-2" />
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
                  <input disabled={!editing} type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} className="form-control mt-2" />
                </label>
              </div>

              <div className="mt-5 text-sm text-slate-500">
                <p>Created: {new Date(profile.created_at).toLocaleString()}</p>
                <p>Updated: {new Date(profile.updated_at).toLocaleString()}</p>
              </div>

              <div className="mt-6 flex flex-wrap gap-2">
                {editing ? (
                  <>
                    <button type="button" onClick={save} disabled={saving} className="primary-button">
                      {saving ? "Đang lưu..." : "Save"}
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
                      Cancel
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={() => setEditing(true)} className="primary-button">Edit</button>
                )}
              </div>
            </>
          ) : (
            <div className="empty-metrics">Không tìm thấy hồ sơ bệnh nhân.</div>
          )}
        </section>
      </div>
    </main>
  );
}
