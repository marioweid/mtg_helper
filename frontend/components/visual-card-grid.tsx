import type { ReactNode } from "react";

interface GridProps {
  children: ReactNode;
}

interface TileProps {
  name: string;
  imageUri: string | null;
  onOpen?: () => void;
  badges?: ReactNode;
  footer?: ReactNode;
}

export function VisualCardGrid({ children }: GridProps) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {children}
    </ul>
  );
}

/** Artwork-first card tile used by deck and collection grids. */
export function VisualCardTile({ name, imageUri, onOpen, badges, footer }: TileProps) {
  const artwork = imageUri ? (
    <img
      src={imageUri}
      alt={name}
      width={488}
      height={680}
      loading="lazy"
      draggable={false}
      className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.015] motion-reduce:transition-none"
    />
  ) : (
    <span className="flex h-full items-center justify-center bg-zinc-900 px-3 text-center text-sm text-gray-400">
      {name}
    </span>
  );

  return (
    <li className="group min-w-0 overflow-hidden rounded-xl border border-white/10 bg-zinc-900/80 shadow-lg shadow-black/15 transition-colors hover:border-indigo-400/35">
      <div className="relative aspect-[5/7] overflow-hidden bg-black">
        {onOpen ? (
          <button
            type="button"
            onClick={onOpen}
            aria-label={`Open ${name}`}
            className="h-full w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400"
          >
            {artwork}
          </button>
        ) : (
          artwork
        )}
        {badges ? <div className="pointer-events-none absolute inset-0">{badges}</div> : null}
      </div>
      {footer ? <div className="border-t border-white/10 p-2.5">{footer}</div> : null}
    </li>
  );
}
