"use client";

import { useState } from "react";
import { authFetch } from "@/lib/api";
import { getOcrIndicators, parseFiniteLabValue } from "@/lib/ocrReviewValidation.mjs";
import type { AnalysisResult } from "@/types/analysis";

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
};

type Props = {
  onResult: (result: AnalysisResult) => void;
  onUnauthorized: () => void;
  accent?: "blue" | "indigo";
};

export default function OcrReviewPanel({
  onResult,
  onUnauthorized,
  accent = "blue",
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [reviewToken, setReviewToken] = useState("");
  const [threshold, setThreshold] = useState(0.7);
  const [meta, setMeta] = useState({ age: "", gender: "male", date: "" });
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<"upload" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const buttonClass = accent === "indigo" ? "bg-indigo-600 hover:bg-indigo-700" : "bg-blue-600 hover:bg-blue-700";

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
      const response = await authFetch("/api/v1/ocr/upload", { method: "POST", body: form });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "OCR thất bại");

      const indicators = getOcrIndicators(data);
      if (indicators.length === 0) {
        setRows([]);
        setReviewToken("");
        throw new Error(
          "Không tìm thấy chỉ số xét nghiệm trong ảnh. Hãy chụp rõ toàn bộ phiếu xét nghiệm và thử lại."
        );
      }

      setReviewToken(String(data.review_token || ""));
      setThreshold(Number(data.low_confidence_threshold ?? 0.7));
      setRows(indicators.map((item: Record<string, unknown>) => ({
        draft_id: String(item.draft_id || ""),
        name: String(item.name || ""),
        value: Number(item.value),
        unit: String(item.unit || ""),
        confidence: Number(item.confidence),
        raw_text: String(item.raw_text || ""),
        needs_review: Boolean(item.needs_review),
        included: true,
        reviewed: false,
        low_confidence_acknowledged: false,
      })));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Không thể nhận diện ảnh");
    } finally {
      setBusy(false);
      setBusyAction(null);
    }
  };

  const confirm = async () => {
    if (!meta.age || !meta.date) {
      setError("Vui lòng điền tuổi và ngày xét nghiệm.");
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
    if (rows.some((row) => !row.reviewed)) {
      setError("Bạn cần đối chiếu và xác nhận từng dòng OCR.");
      return;
    }
    if (rows.some((row) => row.included && row.needs_review && !row.low_confidence_acknowledged)) {
      setError("Chỉ số có độ tin cậy thấp cần xác nhận riêng trước khi phân tích.");
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
          patient_age: Number(meta.age),
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
      if (!response.ok) throw new Error(data.detail || "Không thể xác nhận bản OCR");
      onResult(data as AnalysisResult);
    } catch (caught: unknown) {
      setError(
        caught instanceof DOMException && caught.name === "AbortError"
          ? "Phân tích quá 90 giây. Backend hoặc dịch vụ AI đang chậm; vui lòng thử lại."
          : caught instanceof Error
            ? caught.message
            : "Không thể xác nhận bản OCR"
      );
    } finally {
      window.clearTimeout(timeoutId);
      setBusy(false);
      setBusyAction(null);
    }
  };

  return (
    <div className="bg-white dark:bg-zinc-900 p-6 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm space-y-4">
      <div>
        <h2 className="font-semibold text-lg">OCR Review Gate</h2>
        <p className="text-xs text-zinc-500 mt-1">
          Ảnh chỉ tạo bản nháp. Mọi dòng phải được đối chiếu; dòng dưới {Math.round(threshold * 100)}% cần xác nhận tăng cường.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="file"
          accept="image/*"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setRows([]);
            setReviewToken("");
          }}
          className="file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 text-sm border border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg px-3 py-2 w-full"
        />
        <button type="button" onClick={upload} disabled={busy} className={`px-6 py-2 ${buttonClass} text-white rounded-lg text-sm font-medium disabled:opacity-50`}>
          {busyAction === "upload" ? "Đang nhận diện..." : "Nhận diện OCR"}
        </button>
      </div>

      {busy && (
        <div role="status" className="p-3 rounded-lg bg-blue-50 text-blue-800 border border-blue-200 text-sm">
          {busyAction === "confirm"
            ? "Đã xác nhận bản OCR. Hệ thống đang đối chiếu ngưỡng và tạo giải thích; nếu AI chậm sẽ tự dùng bản giải thích đã kiểm duyệt."
            : "Đang tải ảnh và nhận diện chỉ số. Bước này thường mất 20–90 giây, vui lòng giữ trang đang mở."}
        </div>
      )}

      {rows.length > 0 && (
        <div className="space-y-4 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          {rows.map((row, index) => (
            <div key={row.draft_id} className={`rounded-xl border p-3 space-y-3 ${row.needs_review ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20" : "border-zinc-200 dark:border-zinc-700"}`}>
              <div className="flex items-center justify-between gap-3">
                <span className={`text-xs font-semibold ${row.needs_review ? "text-amber-700 dark:text-amber-400" : "text-emerald-700 dark:text-emerald-400"}`}>
                  Confidence {Math.round(row.confidence * 100)}%{row.needs_review ? " — cần xác nhận riêng" : ""}
                </span>
                <label className="text-xs flex items-center gap-2">
                  <input type="checkbox" checked={row.included} onChange={(event) => updateRow(index, { included: event.target.checked })} />
                  Đưa vào phân tích
                </label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-[1fr_8rem_8rem] gap-2">
                <input value={row.name} onChange={(event) => updateRow(index, { name: event.target.value }, true)} className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700" aria-label="Tên chỉ số" />
                <input type="number" required step="any" value={row.value} onChange={(event) => updateRow(index, { value: event.target.value }, true)} className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700" aria-label="Giá trị" />
                <input value={row.unit} onChange={(event) => updateRow(index, { unit: event.target.value }, true)} className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700" aria-label="Đơn vị" />
              </div>
              {row.raw_text && <p className="text-xs text-zinc-500">Ảnh gốc: “{row.raw_text}”</p>}
              <label className="text-sm flex items-start gap-2">
                <input type="checkbox" className="mt-1" checked={row.reviewed} onChange={(event) => updateRow(index, { reviewed: event.target.checked })} />
                Tôi đã đối chiếu tên, giá trị và đơn vị với ảnh gốc.
              </label>
              {row.needs_review && row.included && (
                <label className="text-sm font-medium text-amber-800 dark:text-amber-300 flex items-start gap-2">
                  <input type="checkbox" className="mt-1" checked={row.low_confidence_acknowledged} onChange={(event) => updateRow(index, { low_confidence_acknowledged: event.target.checked })} />
                  Tôi hiểu OCR có thể đọc sai và xác nhận giá trị đã sửa ở trên là đúng với phiếu.
                </label>
              )}
            </div>
          ))}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input type="number" min="0" max="120" value={meta.age} onChange={(event) => setMeta((current) => ({ ...current, age: event.target.value }))} placeholder="Tuổi" className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700" />
            <select value={meta.gender} onChange={(event) => setMeta((current) => ({ ...current, gender: event.target.value }))} className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700">
              <option value="male">Nam</option><option value="female">Nữ</option><option value="other">Khác</option>
            </select>
            <input type="date" value={meta.date} onChange={(event) => setMeta((current) => ({ ...current, date: event.target.value }))} className="border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700" />
          </div>
          <button type="button" onClick={confirm} disabled={busy} className={`w-full px-6 py-3 ${buttonClass} text-white rounded-xl text-sm font-semibold disabled:opacity-50`}>
            {busyAction === "confirm" ? "Đang phân tích..." : "Xác nhận an toàn & Phân tích"}
          </button>
        </div>
      )}
      {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 border border-red-200 text-sm">{error}</div>}
    </div>
  );
}
