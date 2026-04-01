export default function DeckDetailLoading() {
  return (
    <div className="animate-pulse">
      {/* Header skeleton */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <div className="h-7 w-56 rounded bg-white/10" />
          <div className="h-4 w-40 rounded bg-white/5" />
        </div>
        <div className="flex gap-2">
          <div className="h-9 w-32 rounded-lg bg-white/10" />
          <div className="h-9 w-16 rounded-lg bg-white/5" />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Card list skeleton */}
        <div className="flex flex-col gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4">
              <div className="mb-3 h-5 w-24 rounded bg-white/10" />
              <div className="flex flex-col gap-2">
                {[...Array(3)].map((_, j) => (
                  <div key={j} className="h-10 rounded bg-white/5" />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Sidebar skeleton */}
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4 h-48" />
          <div className="rounded-xl border border-white/10 bg-white/5 p-4 h-64" />
        </div>
      </div>
    </div>
  );
}
