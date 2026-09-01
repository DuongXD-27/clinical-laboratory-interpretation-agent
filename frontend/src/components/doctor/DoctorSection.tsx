import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description?: ReactNode;
  meta?: ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "critical" | "ocr" | "question";
  children: ReactNode;
  className?: string;
};

export default function DoctorSection({
  title,
  description,
  meta,
  icon: Icon,
  tone = "default",
  children,
  className,
}: Props) {
  return (
    <section className={cn("doctor-section", className)} data-tone={tone}>
      <header className="doctor-section__header">
        <div className="doctor-section__heading">
          {Icon ? <Icon aria-hidden="true" /> : null}
          <div>
            <h2>{title}</h2>
            {description ? <div className="doctor-section__description">{description}</div> : null}
          </div>
        </div>
        {meta ? <div className="doctor-section__meta">{meta}</div> : null}
      </header>
      <div className="doctor-section__body">{children}</div>
    </section>
  );
}
