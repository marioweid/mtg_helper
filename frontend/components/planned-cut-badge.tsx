interface Props {
  quantity: number;
}

export function PlannedCutBadge({ quantity }: Props) {
  if (quantity < 1) return null;
  return (
    <span
      className="shrink-0 rounded bg-red-950/60 px-1.5 py-0.5 text-[10px] text-red-300"
      title="Still in the physical deck; excluded only after completion"
    >
      Planned cut ×{quantity}
    </span>
  );
}
