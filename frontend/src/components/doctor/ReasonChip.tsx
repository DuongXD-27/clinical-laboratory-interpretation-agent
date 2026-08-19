import type { ReviewFlag } from "@/types/doctor";

type Props = {
  flag: ReviewFlag;
};

export default function ReasonChip({ flag }: Props) {
  return (
    <span className={`chip-reason chip-reason--${flag.severity}`}>
      <span aria-hidden="true">⚑</span>
      {flag.detail}
    </span>
  );
}
