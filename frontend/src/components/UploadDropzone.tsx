"use client";

import Image from "next/image";
import { useRef, useState } from "react";

type Props = {
  file: File | null;
  previewUrl: string;
  disabled?: boolean;
  busy?: boolean;
  onFileChange: (file: File | null) => void;
};

const ACCEPTED_IMAGES = ".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff";

export default function UploadDropzone({ file, previewUrl, disabled = false, busy = false, onFileChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const chooseFile = () => {
    if (!disabled && !busy) inputRef.current?.click();
  };

  const acceptFile = (picked: File | null) => {
    if (picked) onFileChange(picked);
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGES}
        hidden
        tabIndex={-1}
        onChange={(event) => {
          acceptFile(event.target.files?.[0] ?? null);
          event.target.value = "";
        }}
      />

      {!file ? (
        <div
          className={`upload-dropzone ${dragActive ? "upload-dropzone-active" : ""} ${disabled ? "upload-dropzone-disabled" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!disabled) setDragActive(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragActive(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            if (!disabled && !busy) acceptFile(event.dataTransfer.files?.[0] ?? null);
          }}
        >
          <div className="upload-icon" aria-hidden="true">↑</div>
          <h3 className="mt-4 text-base font-semibold text-slate-900">Tải ảnh phiếu xét nghiệm</h3>
          <p className="mt-1 text-sm text-slate-500">Kéo thả ảnh vào đây hoặc</p>
          <button type="button" onClick={chooseFile} disabled={disabled || busy} className="secondary-button mt-4">
            Chọn ảnh
          </button>
          <p className="mt-4 text-xs text-slate-400">JPG, PNG, WEBP, BMP hoặc TIFF</p>
        </div>
      ) : (
        <div className="selected-file-card">
          <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100">
            {previewUrl && <Image src={previewUrl} alt="Ảnh phiếu xét nghiệm đã chọn" fill unoptimized className="object-cover" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-900">{file.name}</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
              Sẵn sàng để đọc
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={chooseFile} disabled={busy} className="secondary-button px-3 py-2">
                Đổi ảnh
              </button>
              <button type="button" onClick={() => onFileChange(null)} disabled={busy} className="danger-button px-3 py-2">
                Xóa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
