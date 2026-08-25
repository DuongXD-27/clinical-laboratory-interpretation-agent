import Link from "next/link";
import { ArrowLeft } from "lucide-react";

type Props = {
  eyebrow: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  backHref?: string;
  backLabel?: string;
};

export default function DoctorPageHeader({
  eyebrow,
  title,
  description,
  actions,
  backHref,
  backLabel = "Quay lại",
}: Props) {
  return (
    <header className="doctor-page-header">
      {backHref && (
        <Link className="doctor-page-header__back" href={backHref}>
          <ArrowLeft aria-hidden="true" />
          {backLabel}
        </Link>
      )}
      <div className="doctor-page-header__row">
        <div className="doctor-page-header__copy">
          <p className="doctor-page-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          {description && <div className="doctor-page-description">{description}</div>}
        </div>
        {actions && <div className="doctor-page-header__actions">{actions}</div>}
      </div>
    </header>
  );
}
