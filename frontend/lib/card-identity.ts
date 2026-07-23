export interface OracleIdentifiedCard {
  scryfall_id: string;
  oracle_id?: string | null;
}

/** Stable identity shared by every printing of one Oracle card. */
export function cardIdentity(card: OracleIdentifiedCard): string {
  return card.oracle_id ?? card.scryfall_id;
}
