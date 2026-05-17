/**
 * Skeleton placeholders — animated pulse boxes for loading states.
 *
 * ``Skeleton`` is a single box; the page-specific helpers compose it into
 * layout shells that match the post-load page silhouette.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-white/10 ${className}`} />;
}

export function DeckDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-[280px] w-full rounded-2xl" />
      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-3">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-11 w-full" />
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}

export function DeckListSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="aspect-[4/5] w-full rounded-xl" />
      ))}
    </div>
  );
}
