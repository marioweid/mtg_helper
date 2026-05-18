import type { CollectionMembership } from "@/lib/types";

interface Props {
  owned: CollectionMembership[];
  showUnowned?: boolean;
}

export function OwnedBadge({ owned, showUnowned = true }: Props) {
  if (owned.length === 0) {
    if (!showUnowned) return null;
    return (
      <span className="rounded bg-gray-800/60 px-1.5 py-0.5 text-[10px] text-gray-500">
        Unowned
      </span>
    );
  }
  return (
    <>
      {owned.slice(0, 2).map((c) => (
        <span
          key={c.id}
          className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] text-emerald-300"
          title="Owned in this collection"
        >
          ✓ {c.name}
        </span>
      ))}
      {owned.length > 2 && (
        <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] text-emerald-300">
          +{owned.length - 2}
        </span>
      )}
    </>
  );
}
