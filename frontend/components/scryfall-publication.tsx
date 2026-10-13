export type ScryfallSourceStatus =
  | { status: "unavailable" }
  | {
      status: "current" | "mismatched";
      tag_count: number;
      membership_count: number;
      published_at: string;
      manifest: {
        oracle_cards: { updated_at: string };
        oracle_tags: { updated_at: string };
      };
    };

function timestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

/** Show the exact last-good publication and receipt times without claiming recommendation cutover. */
export function ScryfallPublication({ source }: { source: ScryfallSourceStatus }) {
  return (
    <section className="rounded border border-white/10 bg-black/30 p-4">
      <h2 className="text-base font-semibold text-white">Scryfall source publication</h2>
      {source.status === "unavailable" ? (
        <p className="mt-2 text-sm text-amber-300">
          No complete Oracle-tag publication. Run Sync Scryfall.
        </p>
      ) : (
        <>
          {source.status === "mismatched" ? (
            <p role="alert" className="mt-2 text-sm text-red-400">
              Card/tag generation mismatch. Run Sync Scryfall before using tags.
            </p>
          ) : (
            <p className="mt-2 text-sm text-green-300">Matching card/tag generation</p>
          )}
          <p className="mt-2 text-sm text-gray-300">
            {source.tag_count.toLocaleString("en-US")} tags ·{" "}
            {source.membership_count.toLocaleString("en-US")} direct memberships
          </p>
          <dl className="mt-3 grid gap-3 text-xs md:grid-cols-3">
            <div>
              <dt className="text-gray-500">Card export updated</dt>
              <dd className="text-gray-200">
                {timestamp(source.manifest.oracle_cards.updated_at)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Tag export updated</dt>
              <dd className="text-gray-200">{timestamp(source.manifest.oracle_tags.updated_at)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Published locally</dt>
              <dd className="text-gray-200">{timestamp(source.published_at)}</dd>
            </div>
          </dl>
        </>
      )}
      <p className="mt-3 text-xs text-gray-500">
        Source publication only. Label-consumer replacement is not yet active.
      </p>
    </section>
  );
}
