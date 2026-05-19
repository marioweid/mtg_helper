import type { ManaSource, PlaytestCard } from "@/lib/playtest";

interface Props {
  lands: PlaytestCard[];
  tapped: Set<string>;
  permanents: PlaytestCard[];
  rampSources: ManaSource[];
  currentTurn: number;
  onTapLand: (uid: string) => void;
}

export function Battlefield({
  lands,
  tapped,
  permanents,
  rampSources,
  currentTurn,
  onTapLand,
}: Props) {
  return (
    <div className="flex flex-col gap-3">
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-gray-500">
          Lands ({lands.length})
        </h3>
        {lands.length === 0 ? (
          <p className="text-xs text-gray-600">None on battlefield.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {lands.map((land) => {
              const isTapped = tapped.has(land.uid);
              return (
                <button
                  key={land.uid}
                  type="button"
                  onClick={() => onTapLand(land.uid)}
                  className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                    isTapped
                      ? "border-white/10 bg-white/5 text-gray-500 line-through"
                      : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
                  }`}
                  title={isTapped ? "Tapped" : `Produces: ${land.produces.join("/")}`}
                >
                  {land.name}
                </button>
              );
            })}
          </div>
        )}
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-gray-500">
          Mana sources ({rampSources.length})
        </h3>
        {rampSources.length === 0 ? (
          <p className="text-xs text-gray-600">No ramp out.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {rampSources.map((src) => {
              const ready = src.availableFromTurn <= currentTurn;
              const isTapped = tapped.has(src.uid);
              const inactive = !ready || isTapped;
              return (
                <span
                  key={src.uid}
                  className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                    inactive
                      ? "border-white/10 bg-white/5 text-gray-500"
                      : "border-amber-500/40 bg-amber-500/10 text-amber-200"
                  }`}
                  title={
                    ready
                      ? `Produces: ${src.produces.join("/")}`
                      : `Enters T${src.availableFromTurn} (summoning sick)`
                  }
                >
                  {src.name}
                  {!ready && <span className="ml-1 text-[10px]">·T{src.availableFromTurn}</span>}
                </span>
              );
            })}
          </div>
        )}
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-gray-500">
          Permanents ({permanents.length})
        </h3>
        {permanents.length === 0 ? (
          <p className="text-xs text-gray-600">None on battlefield.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {permanents.map((p) => (
              <span
                key={p.uid}
                className="rounded-md border border-indigo-500/40 bg-indigo-500/10 px-2 py-1 text-xs text-indigo-200"
                title={p.type_line ?? ""}
              >
                {p.name}
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
