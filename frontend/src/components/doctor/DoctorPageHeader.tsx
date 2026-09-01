import { PageHero } from "@/components/common/LayoutPrimitives";

type Props = {
  eyebrow: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  backHref?: string;
  backLabel?: string;
  transitionName?: string;
};

export default function DoctorPageHeader({
  eyebrow,
  title,
  description,
  actions,
  backHref,
  backLabel = "Quay lại",
  transitionName,
}: Props) {
  return (
    <PageHero
      className="doctor-page-hero"
      eyebrow={eyebrow}
      title={title}
      description={description}
      actions={actions}
      backHref={backHref}
      backLabel={backLabel}
      transitionName={transitionName}
    />
  );
}
