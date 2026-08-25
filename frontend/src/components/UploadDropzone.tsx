"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { Check, ImageUp, RefreshCw, Trash2 } from "lucide-react";

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
          <div className="upload-icon" aria-hidden="true"><ImageUp /></div>
          <span className="patient-route-eyebrow mt-4">Nhận diện phiếu bằng AI</span>
          <h3 className="mt-1 text-lg font-semibold text-foreground">Tải ảnh phiếu xét nghiệm</h3>
          <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">Kéo thả ảnh rõ nét vào đây hoặc chọn ảnh từ thiết bị.</p>
          <button type="button" onClick={chooseFile} disabled={disabled || busy} className="patient-btn-secondary mt-5">
            Chọn ảnh
          </button>
          <p className="mt-4 text-xs text-muted-foreground">JPG, PNG, WEBP, BMP hoặc TIFF</p>
        </div>
      ) : (
        <div className="selected-file-card">
          <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100">
            {previewUrl && <Image src={previewUrl} alt="Ảnh phiếu xét nghiệm đã chọn" fill unoptimized className="object-cover" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">{file.name}</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-[var(--status-normal-fg)]">
              <Check aria-hidden="true" />
              Sẵn sàng để đọc
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={chooseFile} disabled={busy} className="patient-btn-secondary px-3">
                <RefreshCw aria-hidden="true" />
                Đổi ảnh
              </button>
              <button type="button" onClick={() => onFileChange(null)} disabled={busy} className="patient-btn-danger px-3">
                <Trash2 aria-hidden="true" />
                Xóa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
