import type { ReactNode } from "react";

type Props = {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  titleId?: string;
};

export default function PatientPageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
  titleId,
}: Props) {
  return (
    <header className={`patient-route-heading ${className}`.trim()}>
      <div className="min-w-0">
        <span className="patient-route-eyebrow">{eyebrow}</span>
        <h1 id={titleId}>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="patient-route-actions">{actions}</div> : null}
    </header>
  );
}
