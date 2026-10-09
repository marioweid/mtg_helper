# User-deck recovery smoke test

## Now

Yuna and Meren lists were supplied by the user as known-good examples. Raw text is preserved in
`yuna.txt` and `meren.txt`. The separately approved four-call Luna/Terra recovery test is complete:
Yuna recovered 15/16 targets and Meren 19/19 from 50 suggestions per model. No UI, production
recommendation path, or application model setting changed. The answer lists stayed hidden.

Results and limitations: [measured report](../../../docs/research/deck-recovery-smoke/README.md).
The four-call authorization and prior New Cards budgets are exhausted; additional paid calls need
new permission.

## Offline validation

The cached Scryfall Oracle export matches the SHA-256 recorded in
`docs/research/new-cards-spike-2026-10-05/data-report.json`. Its source timestamp is
`2026-10-04T21:01:57.080+00:00`; this is a frozen snapshot, not a live legality guarantee.

| Fixture | Commander | Main including commander | Nonland targets | Land cards | Sideboard |
| --- | --- | ---: | ---: | ---: | ---: |
| Yuna | Yuna, Grand Summoner | 100 | 65 | 34 | 1 |
| Meren | Meren of Clan Nel Toth | 100 | 66 | 33 | 0 |

All entries resolved, were Commander-legal and within commander colors in that snapshot. Main-deck
Oracle identities were unique. The commander is explicitly identified independently of its position
in the raw text: Yuna occurs after the sideboard marker, but is not a sideboard entry. Guiding Hydra
is the sideboard card and is excluded from recovery scoring.

Resolve exact whole-card names first, then an unambiguous front-face alias for names abbreviated
in the supplied lists. Do not alias every face: the frozen source also contains prepare cards with
associated faces named Reanimate and Swords to Plowshares; those are not the standalone originals.
Score by resolved Oracle identity, not substring similarity or printing identity.

For this test, classify by the front face's type. Agadeem's Awakening, Disciple of Freyalise,
Fell the Profane, and Malakir Rebirth count as nonlands. Dryad Arbor counts as a land.

## First-run protocol (now executed)

- Input: commander facts and a short strategy brief, not the full list or target-card names.
- Inferred Yuna brief: counter growth/redistribution with creature-based acceleration.
- Inferred Meren brief: sacrifice and creature-recursion value with reusable ETB/death effects.
- Do not add an unstated budget, bracket, or no-infinite-combo preference.
- Request exactly 50 ranked unique nonland candidates, with short reasons.
- No community sources, embeddings, provided-answer candidates, or decklist scraping.
- Resolve and check suggestions against source facts after generation; do not quietly replace
  duplicates, invalid cards, missing facts, or failed calls to improve the score.
- Exclude commanders, sideboards, and land-front cards from exact-hit scoring.
- Report exact hits out of 50, recovery out of 65/66, top-ten hits, duplicates, unresolved names,
  illegal/off-color/land outputs, off-list alternatives, latency, tokens, and cost.
- Treat 20 exact hits as promising and 30 as stronger initial evidence at the fixed pool size.
  Inspect engine hits as well as staples; off-list alternatives need human judgment.

The direct-prompt test measures whether the model can discover familiar cards for the intended
strategy. It does not prove the proposed local-search hybrid, rules explanations, New Cards recall,
interactive response times, or correct behavior after plan/direction changes. If promising, test the
next piece independently rather than implementing the whole architecture at once.

See `docs/recommendation-vision-and-proof.md` for the broader, still-proposed interaction design.
