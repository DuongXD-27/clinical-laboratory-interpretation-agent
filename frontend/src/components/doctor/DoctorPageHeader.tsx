import { PageHero } from "@/components/common/LayoutPrimitives";

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
  return <PageHero eyebrow={eyebrow} title={title} description={description} actions={actions} backHref={backHref} backLabel={backLabel} />;
}
