import type { ReactNode } from "react";

type Props = {
  id: string;
  name: string;
  label?: string;
  unit: string;
  value: string | number;
  onValueChange: (value: string) => void;
  onRemove: () => void;
  removeLabel?: string;
  onNameChange?: (value: string) => void;
  onUnitChange?: (value: string) => void;
  attentionMessage?: string;
  children?: ReactNode;
};

export default function MetricInput({
  id,
  name,
  label,
  unit,
  value,
  onValueChange,
  onRemove,
  removeLabel,
  onNameChange,
  onUnitChange,
  attentionMessage,
  children,
}: Props) {
  const valueId = `metric-value-${id}`;
  const nameId = `metric-name-${id}`;
  const unitId = `metric-unit-${id}`;

  return (
    <article className={`metric-card ${attentionMessage ? "metric-card-attention" : ""}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          {onNameChange ? (
            <label className="field-label" htmlFor={nameId}>
              Chỉ số
              <input
                id={nameId}
                value={name}
                onChange={(event) => onNameChange(event.target.value)}
                className="form-control mt-2"
                autoComplete="off"
              />
            </label>
          ) : (
            <>
              <h3 className="text-[15px] font-semibold text-slate-900">{label ?? name}</h3>
              {label && label !== name && <p className="mt-0.5 text-xs text-slate-500">{name}</p>}
            </>
          )}
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="text-sm font-medium text-slate-500 hover:text-slate-700 hover:bg-slate-100 px-2 py-1 rounded transition-colors"
          aria-label={`${removeLabel || "Xóa chỉ số"} ${label ?? name}`}
          title={removeLabel || "Xóa chỉ số"}
        >
          {removeLabel || "×"}
        </button>
      </div>

      {attentionMessage && (
        <p className="mt-3 flex items-start gap-2 text-sm font-medium text-amber-800" role="note">
          <span aria-hidden="true">!</span>
          {attentionMessage}
        </p>
      )}

      <div className={`mt-4 grid gap-3 ${onUnitChange ? "sm:grid-cols-[1fr_10rem]" : ""}`}>
        <label className="field-label" htmlFor={valueId}>
          Giá trị
          <div className="mt-2 flex min-w-0 items-center overflow-hidden rounded-xl border border-slate-300 bg-white transition focus-within:border-blue-600 focus-within:ring-4 focus-within:ring-blue-100">
            <input
              id={valueId}
              type="number"
              min="0"
              step="any"
              value={value}
              onChange={(event) => onValueChange(event.target.value)}
              placeholder="Nhập giá trị"
              className="min-w-0 flex-1 border-0 bg-transparent px-3.5 py-3 text-base text-slate-900 outline-none placeholder:text-slate-400"
            />
            {!onUnitChange && (
              <span className="shrink-0 border-l border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
                {unit}
              </span>
            )}
          </div>
        </label>

        {onUnitChange && (
          <label className="field-label" htmlFor={unitId}>
            Đơn vị
            <input
              id={unitId}
              value={unit}
              onChange={(event) => onUnitChange(event.target.value)}
              className="form-control mt-2"
              autoComplete="off"
            />
          </label>
        )}
      </div>

      {children && <div className="mt-4 border-t border-slate-100 pt-4">{children}</div>}
    </article>
  );
}
