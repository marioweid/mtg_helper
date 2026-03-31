import { COLOR_SYMBOLS } from "@/lib/constants";

export function ManaSymbols({ colors }: { colors: string[] }) {
  if (colors.length === 0) return <span className="text-xs text-gray-500">Colorless</span>;
  return (
    <div className="flex gap-1">
      {colors.map((c) => {
        const sym = COLOR_SYMBOLS[c];
        if (!sym) return null;
        return (
          <span
            key={c}
            className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${sym.bg} ${sym.text}`}
          >
            {sym.label}
          </span>
        );
      })}
    </div>
  );
}
