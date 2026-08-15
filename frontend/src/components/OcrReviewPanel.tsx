"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MetricInput from "@/components/MetricInput";
import UploadDropzone from "@/components/UploadDropzone";
import { API_BASE, authFetch } from "@/lib/api";
import { getOcrIndicators, parseFiniteLabValue } from "@/lib/ocrReviewValidation.mjs";
import type { AnalysisResult } from "@/types/analysis";

type UploadPolicy = {
  mode: "internal_only" | "demo_only" | "open_with_consent";
  upload_enabled: boolean;
  consent_required: boolean;
  custom_image_allowed: boolean;
  consent_text: string;
};

type ReviewRow = {
  draft_id: string;
  name: string;
  value: number | string;
  unit: string;
  confidence: number;
  raw_text?: string;
  needs_review: boolean;
  included: boolean;
  reviewed: boolean;
  low_confidence_acknowledged: boolean;
  supported: boolean;
  unsupported_reason: string;
};

type Props = {
  onResult: (result: AnalysisResult) => void;
  onUnauthorized: () => void;
  accent?: "blue" | "indigo";
};

function friendlyUploadError(status: number, detail: unknown) {
  if (status >= 500) {
    return "Không thể đọc rõ phiếu xét nghiệm này. Hãy thử ảnh rõ hơn hoặc nhập kết quả thủ công.";
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  return "Không thể đọc rõ phiếu xét nghiệm này. Hãy thử ảnh rõ hơn hoặc nhập kết quả thủ công.";
}

export default function OcrReviewPanel({ onResult, onUnauthorized }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [policy, setPolicy] = useState<UploadPolicy | null>(null);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [reviewToken, setReviewToken] = useState("");
  const [meta, setMeta] = useState({ age: "", gender: "male", date: "" });
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<"upload" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [policyLoaded, setPolicyLoaded] = useState(false);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/v1/ocr/policy`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: UploadPolicy | null) => {
        if (active && data) setPolicy(data);
      })
      .catch(() => {
        /* Keep uploads disabled when policy cannot be read. */
      })
      .finally(() => {
        if (active) setPolicyLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const resetDraft = useCallback(() => {
    setRows([]);
    setReviewToken("");
    setError(null);
  }, []);

  const handleFileChange = useCallback((picked: File | null) => {
    setFile(picked);
    resetDraft();
  }, [resetDraft]);

  const updateRow = (index: number, patch: Partial<ReviewRow>, resetReview = false) => {
    setRows((current) => current.map((row, rowIndex) => (
      rowIndex === index
        ? {
            ...row,
            ...patch,
            ...(resetReview ? { reviewed: false, low_confidence_acknowledged: false } : {}),
          }
        : row
    )));
  };

  const upload = async () => {
    if (!file) {
      setError("Vui lòng chọn ảnh phiếu xét nghiệm.");
      return;
    }
    setBusy(true);
    setBusyAction("upload");
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      // Clicking the primary action is the explicit upload consent; the backend
      // contract still requires this field and independently enforces policy.
      form.append("consent_acknowledged", "true");
      const response = await authFetch("/api/v1/ocr/upload", { method: "POST", body: form });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(friendlyUploadError(response.status, data.detail));

      const indicators = getOcrIndicators(data);
      if (indicators.length === 0) {
        setRows([]);
        setReviewToken("");
        throw new Error("Không tìm thấy chỉ số xét nghiệm trong ảnh. Hãy chụp rõ toàn bộ phiếu và thử lại.");
      }

      setReviewToken(String(data.review_token || ""));
      setRows(indicators.map((item: Record<string, unknown>) => ({
        supported: item.supported !== false,
        draft_id: String(item.draft_id || ""),
        name: String(item.name || ""),
        value: Number(item.value),
        unit: String(item.unit || ""),
        confidence: Number(item.confidence),
        raw_text: String(item.raw_text || ""),
        needs_review: Boolean(item.needs_review),
        unsupported_reason: String(item.unsupported_reason || "Chỉ số này hiện tại chưa được hỗ trợ."),
        included: item.supported !== false,
        reviewed: item.supported === false,
        low_confidence_acknowledged: false,
      })));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Không thể đọc rõ phiếu xét nghiệm này. Hãy thử ảnh rõ hơn hoặc nhập kết quả thủ công.");
    } finally {
      setBusy(false);
      setBusyAction(null);
    }
  };

  const confirm = async () => {
    const age = Number(meta.age);
    if (!Number.isInteger(age) || age < 0 || age > 120 || !meta.date) {
      setError("Vui lòng điền tuổi hợp lệ và ngày xét nghiệm.");
      return;
    }
    const parsedValues: number[] = [];
    for (const row of rows) {
      const parsedValue = parseFiniteLabValue(row.value);
      if (parsedValue === null) {
        setError(`Giá trị của chỉ số ${row.name || "chưa có tên"} phải là một số hợp lệ.`);
        return;
      }
      parsedValues.push(parsedValue);
    }
    if (rows.some((row) => row.included && !row.reviewed)) {
      setError("Vui lòng kiểm tra và xác nhận các chỉ số trước khi phân tích.");
      return;
    }
    if (rows.some((row) => row.included && row.needs_review && !row.low_confidence_acknowledged)) {
      setError("Một số giá trị cần được kiểm tra kỹ và xác nhận trước khi phân tích.");
      return;
    }

    setBusy(true);
    setBusyAction("confirm");
    setError(null);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await authFetch("/api/v1/ocr/confirm", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          review_token: reviewToken,
          patient_age: age,
          patient_gender: meta.gender,
          test_date: meta.date,
          language: "vi",
          indicators: rows.map((row, index) => ({
            draft_id: row.draft_id,
            name: row.name,
            value: parsedValues[index],
            unit: row.unit,
            included: row.included,
            reviewed: row.reviewed,
            low_confidence_acknowledged: row.low_confidence_acknowledged,
          })),
        }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(response.status >= 500
          ? "Chưa thể phân tích kết quả lúc này. Vui lòng thử lại sau."
          : (typeof data.detail === "string" ? data.detail : "Không thể phân tích kết quả."));
      }
      onResult(data as AnalysisResult);
    } catch (caught: unknown) {
      setError(
        caught instanceof DOMException && caught.name === "AbortError"
          ? "Quá trình phân tích mất nhiều thời gian hơn dự kiến. Vui lòng thử lại."
          : caught instanceof Error
            ? caught.message
            : "Không thể phân tích kết quả lúc này. Vui lòng thử lại."
      );
    } finally {
      window.clearTimeout(timeoutId);
      setBusy(false);
      setBusyAction(null);
    }
  };

  const includedRows = rows.filter((row) => row.supported && row.included);
  const excludedRows = rows.filter((row) => row.supported && !row.included);
  const unsupportedRows = rows.filter((row) => !row.supported);
  const uploadsAllowed = Boolean(policy?.upload_enabled && policy.custom_image_allowed);
  const uploadUnavailable = policyLoaded && !uploadsAllowed;
  const currentStep = busyAction === "confirm" ? 3 : rows.length > 0 ? 2 : 1;
  const workflowSteps = ["Tải phiếu", "Kiểm tra dữ liệu", "Phân tích", "Xem kết quả"];

  return (
    <section className="patient-card p-5 sm:p-7" aria-labelledby="upload-title">
      <div className="section-heading">
        <span className="eyebrow">Đọc kết quả từ ảnh</span>
        <h2 id="upload-title">Tải ảnh phiếu xét nghiệm</h2>
        <p>Tải ảnh phiếu xét nghiệm để hệ thống đọc các chỉ số giúp bạn.</p>
      </div>

      <ol className="ocr-stepper" aria-label="Quy trình phân tích ảnh phiếu xét nghiệm">
        {workflowSteps.map((label, index) => {
          const step = index + 1;
          const complete = step < currentStep;
          const active = step === currentStep;
          return (
            <li key={label} className={complete ? "complete" : active ? "active" : ""} aria-current={active ? "step" : undefined}>
              <span aria-hidden="true">{complete ? "✓" : step}</span>
              <strong>{label}</strong>
            </li>
          );
        })}
      </ol>

      <div className="mt-6">
        <UploadDropzone
          file={file}
          previewUrl={previewUrl}
          disabled={!uploadsAllowed}
          busy={busy}
          onFileChange={handleFileChange}
        />
      </div>

      {uploadUnavailable && (
        <div className="info-message mt-4" role="status">
          Tải ảnh cá nhân hiện chưa được bật trong môi trường này. Chính sách tải ảnh do hệ thống quản lý.
        </div>
      )}

      {file && rows.length === 0 && (
        <div className="mt-5">
          {policy?.consent_required && (
            <p className="mb-4 text-xs leading-5 text-slate-500">
              Khi chọn “Đọc phiếu xét nghiệm”, bạn đồng ý gửi ảnh để xử lý theo chính sách hiện hành. Ảnh gốc không được lưu sau khi yêu cầu kết thúc.
            </p>
          )}
          <button type="button" onClick={upload} disabled={busy || !uploadsAllowed} className="primary-button w-full">
            {busyAction === "upload" ? "Đang đọc phiếu xét nghiệm..." : "Đọc phiếu xét nghiệm"}
          </button>
        </div>
      )}

      {busyAction === "upload" && (
        <div role="status" aria-live="polite" className="loading-message mt-4">
          <span className="loading-dot" aria-hidden="true" />
          Đang đọc phiếu xét nghiệm. Quá trình này có thể mất một chút thời gian...
        </div>
      )}

      {rows.length > 0 && (
        <div className="mt-8 border-t border-slate-100 pt-7">
          <div className="section-heading">
            <span className="eyebrow">Bước kiểm tra</span>
            <h2>Kiểm tra các chỉ số</h2>
            <p>AI đã đọc các thông tin dưới đây từ ảnh. Hãy đối chiếu với phiếu gốc trước khi tiếp tục.</p>
          </div>

          <div className="mt-5 grid gap-3">
            {includedRows.map((row) => {
              const index = rows.indexOf(row);
              return (
                <MetricInput
                  key={row.draft_id}
                  id={row.draft_id}
                  name={row.name}
                  unit={row.unit}
                  value={row.value}
                  onNameChange={(value) => updateRow(index, { name: value }, true)}
                  onUnitChange={(value) => updateRow(index, { unit: value }, true)}
                  onValueChange={(value) => updateRow(index, { value }, true)}
                  onRemove={() => updateRow(index, {
                    included: false,
                    reviewed: true,
                    low_confidence_acknowledged: false,
                  })}
                  attentionMessage={row.needs_review ? "Vui lòng kiểm tra kỹ lại giá trị này." : undefined}
                >
                  {row.raw_text && <p className="mb-3 text-xs text-slate-500">Nội dung đọc được: “{row.raw_text}”</p>}
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={row.reviewed}
                      onChange={(event) => updateRow(index, { reviewed: event.target.checked })}
                    />
                    <span>Tôi đã kiểm tra tên, giá trị và đơn vị với ảnh gốc.</span>
                  </label>
                  {row.needs_review && (
                    <label className="check-row mt-3 text-amber-900">
                      <input
                        type="checkbox"
                        checked={row.low_confidence_acknowledged}
                        onChange={(event) => updateRow(index, { low_confidence_acknowledged: event.target.checked })}
                      />
                      <span>Tôi xác nhận giá trị trên đã đúng với phiếu xét nghiệm.</span>
                    </label>
                  )}
                </MetricInput>
              );
            })}
          </div>

          {excludedRows.length > 0 && (
            <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              {excludedRows.map((row) => {
                const index = rows.indexOf(row);
                return (
                  <div key={row.draft_id} className="flex items-center justify-between gap-3 py-1">
                    <span className="truncate">Đã bỏ qua {row.name}</span>
                    <button type="button" className="text-button" onClick={() => updateRow(index, { included: true, reviewed: false })}>
                      Hoàn tác
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {unsupportedRows.length > 0 && (
            <div className="info-message mt-4" role="status">
              <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
              <div className="mt-2 grid gap-1">
                {unsupportedRows.map((row) => (
                  <p key={row.draft_id}>
                    {row.name}: {row.unsupported_reason}
                  </p>
                ))}
              </div>
            </div>
          )}

          <div className="mt-7">
            <h3 className="text-sm font-semibold text-slate-900">Thông tin chung</h3>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <label className="field-label" htmlFor="ocr-age">
                Tuổi
                <input id="ocr-age" type="number" min="0" max="120" value={meta.age} onChange={(event) => setMeta((current) => ({ ...current, age: event.target.value }))} className="form-control mt-2" />
              </label>
              <label className="field-label" htmlFor="ocr-gender">
                Giới tính
                <select id="ocr-gender" value={meta.gender} onChange={(event) => setMeta((current) => ({ ...current, gender: event.target.value }))} className="form-control mt-2">
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                  <option value="other">Khác</option>
                </select>
              </label>
              <label className="field-label" htmlFor="ocr-date">
                Ngày xét nghiệm
                <input id="ocr-date" type="date" value={meta.date} onChange={(event) => setMeta((current) => ({ ...current, date: event.target.value }))} className="form-control mt-2" />
              </label>
            </div>
          </div>

          <button type="button" onClick={confirm} disabled={busy || includedRows.length === 0} className="primary-button mt-6 w-full">
            {busyAction === "confirm" ? "Đang phân tích kết quả..." : "Phân tích kết quả"}
          </button>
        </div>
      )}

      {busyAction === "confirm" && (
        <div role="status" aria-live="polite" className="loading-message mt-4">
          <span className="loading-dot" aria-hidden="true" />
          Đang phân tích các chỉ số đã xác nhận...
        </div>
      )}

      {error && <div role="alert" className="error-message mt-4">{error}</div>}
    </section>
  );
}
