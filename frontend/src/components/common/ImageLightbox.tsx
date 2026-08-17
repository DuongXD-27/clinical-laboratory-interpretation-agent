"use client";

import { useEffect } from "react";

type Props = {
  src: string;
  alt: string;
  open: boolean;
  onClose: () => void;
};

export default function ImageLightbox({ src, alt, open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="image-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label="Ảnh gốc phiếu xét nghiệm"
      onClick={onClose}
    >
      <button type="button" className="image-lightbox__close" onClick={onClose}>
        Đóng
      </button>
      {/* eslint-disable-next-line @next/next/no-img-element -- dynamic source from backend, rendered only inside a modal. */}
      <img src={src} alt={alt} onClick={(event) => event.stopPropagation()} />
    </div>
  );
}
