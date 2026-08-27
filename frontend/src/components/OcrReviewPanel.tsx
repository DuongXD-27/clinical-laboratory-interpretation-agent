"use client";

import React, { useCallback, useEffect, useMemo, useState, Fragment } from "react";
import MetricInput from "@/components/MetricInput";
import UploadDropzone from "@/components/UploadDropzone";
import { API_BASE, authFetch } from "@/lib/api";
import { getOcrIndicators, parseFiniteLabValue } from "@/lib/ocrReviewValidation.mjs";
import { friendlyOcrError } from "@/lib/ocrErrors.mjs";
import type { AnalysisResult } from "@/types/analysis";
import { ScanLine } from "lucide-react";

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

function getConfirmReadiness(meta: { age: string; date: string }, rows: ReviewRow[]) {
  const age = Number(meta.age);
  const issues: string[] = [];
  let originalError: string | null = null;

  if (!Number.isInteger(age) || age < 0 || age > 120 || !meta.date) {
    issues.push("Vui lòng nhập tuổi hợp lệ và chọn ngày xét nghiệm.");
    originalError = "Vui lòng điền tuổi hợp lệ và ngày xét nghiệm.";
  }

  const invalidRow = rows.find(row => parseFiniteLabValue(row.value) === null);
  if (invalidRow) {
    issues.push(invalidRow.included ? "Có chỉ số có giá trị chưa hợp lệ." : "Có chỉ số (bị bỏ qua) có giá trị chưa hợp lệ.");
    if (!originalError) originalError = `Giá trị của chỉ số ${invalidRow.name || "chưa có tên"} phải là một số hợp lệ.`;
  }

  const includedRows = rows.filter(r => r.included);
  
  if (includedRows.length > 0) {
    const missingReview = includedRows.filter(r => !r.reviewed).length;
    if (missingReview > 0) {
      issues.push(`Còn ${missingReview} chỉ số cần bạn kiểm tra.`);
      if (!originalError) originalError = "Vui lòng kiểm tra và xác nhận các chỉ số trước khi phân tích.";
    }

    const missingAck = includedRows.filter(r => r.needs_review && !r.low_confidence_acknowledged).length;
    if (missingAck > 0) {
      issues.push(`Còn ${missingAck} chỉ số cần xác nhận.`);
      if (!originalError) originalError = "Một số giá trị cần được kiểm tra kỹ và xác nhận trước khi phân tích.";
    }
  } else {
    issues.push("Không có chỉ số nào được đưa vào phân tích.");
  }

  return {
    ready: originalError === null && includedRows.length > 0,
    issues,
    originalError,
  };
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
      if (!response.ok) throw new Error(friendlyOcrError(
        response.status,
        data.detail,
        response.headers.get("X-OCR-Error-Code"),
      ));

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
    const readiness = getConfirmReadiness(meta, rows);
    if (!readiness.ready) {
      if (readiness.originalError) setError(readiness.originalError);
      return;
    }
    
    const age = Number(meta.age);
    const parsedValues = rows.map(r => parseFiniteLabValue(r.value) as number);

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
  
  const readiness = useMemo(() => getConfirmReadiness(meta, rows), [meta, rows]);
  const globalReviewed = includedRows.length > 0 && includedRows.every(
    (row) => row.reviewed && (!row.needs_review || row.low_confidence_acknowledged),
  );

  const setGlobalReviewed = (checked: boolean) => {
    setRows((current) => current.map((row) => (
      row.supported && row.included
        ? {
            ...row,
            reviewed: checked,
            low_confidence_acknowledged: row.needs_review ? checked : row.low_confidence_acknowledged,
          }
        : row
    )));
  };

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex items-center text-sm font-medium whitespace-nowrap overflow-x-auto pb-2 sm:pb-0 select-none" aria-label="Quy trình tải ảnh">
        {workflowSteps.map((label, index) => {
          const step = index + 1;
          const isActiveOrPast = currentStep >= step;
          return (
            <Fragment key={label}>
              <div className={`flex items-center gap-2 ${isActiveOrPast ? 'text-foreground' : 'text-muted-foreground/70'}`}>
                <span className={`flex items-center justify-center w-6 h-6 rounded-full border text-xs font-semibold ${isActiveOrPast ? 'bg-[var(--surface)] border-[var(--border)] shadow-sm' : 'border-[var(--border)]/50'}`}>
                  {step}
                </span>
                <span>{label}</span>
              </div>
              {index < workflowSteps.length - 1 && (
                <div className="w-8 sm:w-12 h-px bg-[var(--border)]/60 mx-3 sm:mx-4" />
              )}
            </Fragment>
          );
        })}
      </div>

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
        <div role="status" aria-live="polite" className="ocr-processing-surface mt-4">
          <div className="ocr-processing-icon" aria-hidden="true"><ScanLine /></div>
          <div>
            <strong>Đang đọc phiếu xét nghiệm...</strong>
            <p>AI đang nhận diện tên chỉ số, giá trị và đơn vị. Quá trình này có thể mất một chút thời gian.</p>
          </div>
          <span className="ocr-processing-track" aria-hidden="true"><span /></span>
        </div>
      )}

      {rows.length > 0 && (
        <div className="mt-8 border-t border-slate-100 pt-7">
          <div className="section-heading">
            <span className="eyebrow">Bước kiểm tra</span>
            <h2>Kiểm tra các chỉ số</h2>
            <p>AI đã đọc các thông tin dưới đây từ ảnh. Hãy đối chiếu với phiếu gốc trước khi tiếp tục.</p>
          </div>

          <div className="mt-6 mb-4 rounded-[1.25rem] bg-[var(--surface-subtle)] border border-[var(--border)]/60 px-5 py-4 shadow-[inset_0_2px_10px_rgba(0,0,0,0.01)]">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
              <div className="flex flex-col">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-0.5">Đưa vào phân tích</span>
                <span className="text-foreground font-semibold text-lg">{includedRows.length}</span>
              </div>
              <div className="w-px h-8 bg-[var(--border)]/60 hidden sm:block"></div>
              <div className="flex flex-col">
                <span className="text-xs font-medium text-amber-700 uppercase tracking-wider mb-0.5">Cần hoàn tất</span>
                <span className="text-amber-700 font-semibold text-lg">{includedRows.filter(r => !r.reviewed || (r.needs_review && !r.low_confidence_acknowledged) || parseFiniteLabValue(r.value) === null).length}</span>
              </div>
              <div className="w-px h-8 bg-[var(--border)]/60 hidden sm:block"></div>
              <div className="flex flex-col">
                <span className="text-xs font-medium text-emerald-700 uppercase tracking-wider mb-0.5">Sẵn sàng</span>
                <span className="text-emerald-700 font-semibold text-lg">{includedRows.filter(r => r.reviewed && (!r.needs_review || r.low_confidence_acknowledged) && parseFiniteLabValue(r.value) !== null).length}</span>
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
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
                  removeLabel="Không đưa vào phân tích"
                  attentionMessage={row.needs_review ? "Độ tin cậy OCR thấp — cần đối chiếu với phiếu gốc" : undefined}
                >
                  {row.raw_text && <p className="ocr-evidence">Nội dung OCR: “{row.raw_text}”</p>}
                </MetricInput>
              );
            })}
          </div>

          {excludedRows.length > 0 && (
            <div className="mt-6 rounded-xl bg-slate-50 border border-slate-200 px-5 py-4">
              <h3 className="text-sm font-semibold text-slate-800 mb-3 uppercase tracking-wider">Không đưa vào phân tích ({excludedRows.length} chỉ số)</h3>
              <div className="grid gap-2">
                {excludedRows.map((row) => {
                  const index = rows.indexOf(row);
                  const isInvalid = parseFiniteLabValue(row.value) === null;
                  return (
                    <div key={row.draft_id} className={`flex items-center justify-between gap-3 py-2.5 px-4 rounded-lg ${isInvalid ? 'bg-amber-50 border border-amber-200' : 'bg-white border border-slate-100'} shadow-sm`}>
                      <div className="flex flex-col min-w-0">
                        <span className="truncate text-sm font-medium text-slate-700">{row.name}</span>
                        {isInvalid && <span className="text-xs text-amber-700 font-medium mt-0.5">Giá trị OCR chưa hợp lệ - Cần sửa giá trị này trước khi tiếp tục.</span>}
                      </div>
                      <button type="button" className="text-sm font-medium text-[var(--brand)] hover:text-[var(--brand-strong)] shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand)] rounded transition-colors" onClick={() => updateRow(index, { included: true, reviewed: false })}>
                        Đưa lại vào phân tích
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {unsupportedRows.length > 0 && (
            <div className="info-message mt-4" role="status">
              <p className="font-semibold text-slate-800">Chỉ số chưa được hỗ trợ</p>
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

          <div className="ocr-global-confirmation mt-6">
            <label>
              <input
                type="checkbox"
                checked={globalReviewed}
                onChange={(event) => setGlobalReviewed(event.target.checked)}
              />
              <span>
                <strong>Tôi đã đối chiếu toàn bộ dữ liệu OCR với ảnh gốc</strong>
                <small>Tôi xác nhận tên chỉ số, giá trị và đơn vị của tất cả mục được đưa vào phân tích là chính xác.</small>
              </span>
            </label>
          </div>

          <div className="mt-4">
            <button type="button" onClick={confirm} disabled={busy || !readiness.ready} className="primary-button w-full">
              {busyAction === "confirm" ? "Đang phân tích kết quả..." : "Phân tích kết quả"}
            </button>
            {!readiness.ready && readiness.issues.length > 0 && !busy && (
              <div className="mt-3 text-sm font-medium text-amber-700 text-center" role="status">
                {readiness.issues[0]}
              </div>
            )}
          </div>
        </div>
      )}

      {busyAction === "confirm" && (
        <div role="status" aria-live="polite" className="ocr-processing-surface mt-4">
          <div className="ocr-processing-icon" aria-hidden="true"><ScanLine /></div>
          <div>
            <strong>Đang phân tích các chỉ số đã xác nhận...</strong>
            <p>Hệ thống đang đối chiếu dữ liệu đã duyệt và chuẩn bị phần giải thích.</p>
          </div>
          <span className="ocr-processing-track" aria-hidden="true"><span /></span>
        </div>
      )}

      {error && <div role="alert" className="error-message mt-4">{error}</div>}
    </div>
  );
}
