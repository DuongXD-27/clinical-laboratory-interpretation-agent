"use client";

import type React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface ClinicalConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "neutral" | "critical" | "brand";
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
}

export default function ClinicalConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Xác nhận",
  cancelLabel = "Quay lại",
  tone = "neutral",
  loading = false,
  onConfirm,
}: ClinicalConfirmDialogProps) {
  const handleConfirm = async () => {
    await onConfirm();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={!loading}
        className="clinical-dialog max-w-md p-6 bg-[var(--surface)] text-[var(--foreground)] border border-[var(--border)] rounded-2xl shadow-xl backdrop-blur-md"
      >
        <DialogHeader className="gap-2">
          <DialogTitle className="text-lg font-bold text-[var(--foreground)] tracking-tight">
            {title}
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--foreground-secondary)] leading-relaxed">
            {description}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-6 flex-row justify-end gap-3 border-none bg-transparent p-0">
          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => onOpenChange(false)}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={tone === "critical" ? "destructive" : "primary"}
            disabled={loading}
            onClick={() => void handleConfirm()}
          >
            {loading ? "Đang xử lý..." : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
