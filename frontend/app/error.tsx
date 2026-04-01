"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-6 py-4 text-sm text-red-400 max-w-md">
        {error.message || "Something went wrong."}
      </p>
      <button
        onClick={reset}
        className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-300 hover:border-white/40 hover:text-white transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
