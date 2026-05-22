export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface DataResponse<T> {
  data: T;
  meta?: PaginationMeta;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
}

// Accounts
export interface AccountResponse {
  id: string;
  display_name: string;
  created_at: string;
}

export interface AccountUpdate {
  display_name?: string;
}

// Cards
export interface CardResponse {
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  oracle_text: string | null;
  color_identity: string[];
  image_uri: string | null;
  rarity: string | null;
  commander_legal: boolean;
}

// Decks
export interface DeckSummary {
  id: string;
  name: string;
  commander_name: string;
  commander_image: string | null;
  commander_color_identity: string[];
  bracket: number | null;
  stage: string;
  card_count: number;
  created_at: string;
  updated_at: string;
}

export interface DeckResponse {
  id: string;
  name: string;
  description: string | null;
  bracket: number | null;
  stage: string;
  commander_id: string;
  partner_id: string | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
  stage_targets: Record<string, number>;
  suggestion_collection_ids: string[];
  max_price_cents: number | null;
  min_price_cents: number | null;
  archetype_tags: string[];
}

export interface DeckCardItem {
  deck_card_id: string;
  card_id: string;
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  oracle_text: string | null;
  color_identity: string[];
  image_uri: string | null;
  rarity: string | null;
  quantity: number;
  categories: string[];
  added_by: string;
  ai_reasoning: string | null;
  qualifying_stages: string[];
  tags: string[];
  price_eur_cents: number | null;
  owned_in: CollectionMembership[];
}

export interface CommanderCardSummary {
  id: string;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  image_uri: string | null;
  color_identity: string[];
}

export interface DeckDetailResponse {
  id: string;
  name: string;
  description: string | null;
  bracket: number | null;
  stage: string;
  commander_id: string;
  partner_id: string | null;
  commander_color_identity: string[];
  commander_card: CommanderCardSummary | null;
  partner_card: CommanderCardSummary | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
  stage_targets: Record<string, number>;
  suggestion_collection_ids: string[];
  max_price_cents: number | null;
  min_price_cents: number | null;
  archetype_tags: string[];
  cards: DeckCardItem[];
}

export interface DeckCreate {
  commander_scryfall_id: string;
  partner_scryfall_id?: string | null;
  name: string;
  description?: string | null;
  bracket?: number;
  stage_targets?: Record<string, number> | null;
  suggestion_collection_ids?: string[];
  max_price_cents?: number | null;
  min_price_cents?: number | null;
  archetype_tags?: string[];
}

export interface DeckUpdate {
  name?: string;
  description?: string | null;
  bracket?: number;
  suggestion_collection_ids?: string[];
  max_price_cents?: number | null;
  min_price_cents?: number | null;
  archetype_tags?: string[];
}

export interface DeckCardAdd {
  card_scryfall_id: string;
  quantity?: number;
  categories?: string[];
  added_by?: "user" | "ai";
  ai_reasoning?: string | null;
}

export interface DeckCardResponse {
  deck_card_id: string;
  deck_id: string;
  card_id: string;
  scryfall_id: string;
  name: string;
  quantity: number;
  categories: string[];
  added_by: string;
}

// AI
export interface CollectionMembership {
  id: string;
  name: string;
}

export interface CardSuggestion {
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  image_uri: string | null;
  oracle_text: string | null;
  power: string | null;
  toughness: string | null;
  rarity: string | null;
  cmc: number | null;
  color_identity: string[];
  category: string;
  reasoning: string;
  synergies: string[];
  highlight_reasons: string[] | null;
  price_eur_cents: number | null;
  owned_in: CollectionMembership[];
  qualifying_stages: string[];
  sources: string[];
}

export interface BuildResponse {
  stage: string;
  stage_number: number;
  total_stages: number;
  suggestions: CardSuggestion[];
  unresolved: string[];
}

export interface SuggestResponse {
  suggestions: CardSuggestion[];
  unresolved: string[];
}

// Deck Description Agent
export interface DescribeMessage {
  role: string;
  content: string;
}

export interface DescribeRequest {
  commander_scryfall_id: string;
  partner_scryfall_id?: string | null;
  bracket: number;
  history: DescribeMessage[];
  message: string;
}

export interface DescribeResponse {
  reply: string;
  done: boolean;
  description: string | null;
  suggested_name: string | null;
  stage_targets: Record<string, number> | null;
}

// Keyword-extracting agent (replaces describe for the new flow)
export interface KeywordExtractRequest {
  commander_scryfall_id: string;
  partner_scryfall_id?: string | null;
  bracket: number;
  history: DescribeMessage[];
  message: string;
}

export interface KeywordExtractResponse {
  reply: string;
  done: boolean;
  archetype_tags: string[];
  suggested_name: string | null;
  stage_targets: Record<string, number> | null;
}

// Tribal tag enumeration (used by keyword pickers)
export interface TribalTag {
  tag: string;
  subtype: string;
  card_count: number;
}

/**
 * Total number of physical cards across rows. Sums ``quantity`` so basic-land
 * rows like "18 Forest" count as 18, not 1. Treats missing quantity as 1.
 */
export function totalCardCount(cards: DeckCardItem[]): number {
  return cards.reduce((sum, c) => sum + (c.quantity ?? 1), 0);
}

/**
 * Buckets a deck card belongs to: union of user-set categories and the
 * auto-derived qualifying_stages, minus the retrieval-only "bangers" pseudo-
 * stage (it isn't a real classification). Cards left with no buckets fall
 * into "untagged".
 */
export function bucketsFor(card: DeckCardItem): string[] {
  const buckets = new Set<string>();
  for (const c of card.categories) {
    if (c !== "bangers") buckets.add(c);
  }
  for (const s of card.qualifying_stages) {
    if (s !== "bangers") buckets.add(s);
  }
  if (buckets.size === 0) buckets.add("untagged");
  return [...buckets];
}

// Combos (Commander Spellbook)
export interface ComboCardRef {
  name: string;
  scryfall_id: string | null;
  image_uri: string | null;
}

export interface ComboPiece {
  card: ComboCardRef;
  in_deck: boolean;
}

export interface Combo {
  id: string;
  pieces: ComboPiece[];
  produces: string[];
  description: string | null;
  popularity: number | null;
  bracket_tag: string | null;
  missing_count: number;
}

export interface ComboListResponse {
  active: Combo[];
  almost_there: Combo[];
}

export type BracketViolationRule =
  | "game_changer"
  | "mass_land_destruction"
  | "fast_mana"
  | "infinite_combo"
  | "extra_turn_chain";

export interface BracketViolation {
  rule: BracketViolationRule;
  severity: "block" | "warn";
  message: string;
  cards: string[];
}

export interface BracketValidationResponse {
  declared_bracket: number;
  legal: boolean;
  violations: BracketViolation[];
}

export interface RiskyCard {
  card_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number;
  color: string;
  pips_required: number;
  sources_available: number;
  sources_required: number;
}

export interface ColorStatus {
  color: string;
  pip_count: number;
  source_count: number;
  target: number;
  deficit: number;
  turn_demand: number;
  turn_deficit: number;
  risky_cards: RiskyCard[];
}

export interface ManaBaseReport {
  total_lands: number;
  total_colored_pips: number;
  colors: ColorStatus[];
  avg_cmc: number;
  ramp_count: number;
  recommended_lands: number;
  land_delta: number;
}

export interface ManaFixResponse {
  report: ManaBaseReport;
  suggestions: CardSuggestion[];
  unresolved: string[];
}

export interface SwapCandidate extends CardSuggestion {
  price_delta_cents: number;
  function_loss_pct: number;
  similarity_breakdown: Record<string, number>;
}

export interface SwapResponse {
  source_card_id: string;
  source_price_cents: number | null;
  candidates: SwapCandidate[];
}

export interface SwapRequest {
  max_price_cents?: number;
  limit?: number;
}

// Playtest
export interface ManaEngineThreshold {
  min_mana?: number;
  min_hand?: number;
}

export interface BoardStateThreshold {
  min_power?: number;
  min_creatures?: number;
}

export interface VelocityThreshold {
  min_spells_per_turn?: number;
  min_hand?: number;
}

export interface EngineThresholdConfig {
  mana_engine?: ManaEngineThreshold;
  board_state?: BoardStateThreshold;
  velocity?: VelocityThreshold;
}

export interface PlaytestSimulateRequest {
  trials?: number;
  turns?: number;
  on_the_play?: boolean;
  max_mulligans?: number;
  seed?: number | null;
  thresholds?: EngineThresholdConfig | null;
}

export interface PlaytestTurnStat {
  turn: number;
  avg_lands_in_play: number;
  avg_mana_available: number;
  avg_mana_spent: number;
  mana_utilization: number;
  avg_spells_cast_cumulative: number;
  pct_land_drop: number;
  pct_cast_any: number;
  avg_dead_cards: number;
  avg_interaction_in_hand: number;
  avg_cards_drawn_extra: number;
  avg_selection_events: number;
  avg_tutors_cast: number;
  lands_p25: number;
  lands_p50: number;
  lands_p75: number;
  mana_p25: number;
  mana_p50: number;
  mana_p75: number;
  avg_creatures_on_board: number;
  avg_total_power: number;
  avg_cards_in_hand: number;
  pct_mana_engine_hit_cum: number;
  pct_board_state_hit_cum: number;
  pct_velocity_hit_cum: number;
  pct_any_threshold_hit_cum: number;
}

export interface EngineThresholdSummary {
  avg_first_mana_engine_turn: number;
  avg_first_board_state_turn: number;
  avg_first_velocity_turn: number;
  avg_first_any_threshold_turn: number;
  pct_ever_mana_engine: number;
  pct_ever_board_state: number;
  pct_ever_velocity: number;
  pct_ever_any: number;
}

export interface PlaytestOpeningHandStats {
  pct_screwed_mull: number;
  pct_balanced: number;
  pct_flood_mull: number;
  pct_kept_7: number;
  pct_kept_6: number;
  pct_kept_5: number;
  pct_kept_le4: number;
}

export interface PlaytestStats {
  trials: number;
  turns: number;
  on_the_play: boolean;
  avg_mulligans: number;
  mulligan_distribution: number[];
  avg_total_spells_cast: number;
  total_spells_stddev: number;
  pct_flood: number;
  pct_screw: number;
  avg_first_missed_land_turn: number;
  opening_hand: PlaytestOpeningHandStats;
  engine_thresholds: EngineThresholdSummary;
  commander: PlaytestCommanderStats | null;
  partner: PlaytestCommanderStats | null;
  engine_class: PlaytestEngineClass;
  per_turn: PlaytestTurnStat[];
}

export interface PlaytestCommanderStats {
  name: string;
  avg_cast_turn: number;
  pct_ever_cast: number;
}

export type PlaytestEngineClass =
  | "none"
  | "token_generator"
  | "counter_distributor"
  | "sac_payoff"
  | "ramp_engine"
  | "draw_engine";

// Import
export interface DeckImportRequest {
  deck_list: string;
  name: string;
  description?: string | null;
  bracket?: number;
}

export interface DeckUrlImportRequest {
  url: string;
  name?: string | null;
  description?: string | null;
  bracket?: number;
}

export interface DeckImportResponse {
  deck: DeckResponse;
  imported_count: number;
  unresolved: string[];
  color_violations: string[];
  suggested_archetype_tags: string[];
}

// Onboarding
export interface QuickstartRequest {
  commander_scryfall_id: string;
  partner_scryfall_id?: string | null;
  bracket?: number;
  max_price_cents?: number | null;
  min_price_cents?: number | null;
  name?: string | null;
}

export interface QuickstartStageResult {
  stage: string;
  target: number;
  accepted: number;
}

export interface QuickstartResponse {
  deck: DeckResponse;
  stages: QuickstartStageResult[];
}

// Feedback
export interface FeedbackCreate {
  card_scryfall_id: string;
  feedback: "up" | "down" | "reject";
  reason?: string | null;
}

export interface FeedbackResponse {
  id: string;
  deck_id: string;
  card_id: string;
  card_name: string;
  feedback: string;
  reason: string | null;
  created_at: string;
}

// Ranking Weights
export interface RankingWeights {
  semantic: number;
  synergy: number;
  popularity: number;
  personal: number;
  deck_inclusion: number;
  moxfield_inclusion: number;
  trusted_quota: number;
}

export interface RankingWeightsResponse extends RankingWeights {
  account_id: string;
  updated_at: string;
}

export interface RankingWeightsUpdate {
  semantic: number;
  synergy: number;
  popularity: number;
  personal: number;
  deck_inclusion: number;
  moxfield_inclusion: number;
  trusted_quota: number;
}

// Collections
export interface CollectionResponse {
  id: string;
  account_id: string;
  name: string;
  card_count: number;
  created_at: string;
}

export interface CollectionCardItem {
  card_id: string;
  scryfall_id: string;
  name: string;
  set_code: string;
  collector_number: string;
  image_uri: string | null;
  color_identity: string[];
  type_line: string | null;
  quantity: number;
  foil: boolean;
  condition: string | null;
  language: string | null;
  tags: string[];
  purchase_price: string | null;
  last_modified: string | null;
}

export interface CollectionCreate {
  name: string;
}

export interface CollectionUpdate {
  name: string;
}

export interface CollectionCardAdd {
  scryfall_id?: string;
  name?: string;
  quantity?: number;
  foil?: boolean;
  set_code?: string;
  collector_number?: string;
  condition?: string | null;
  language?: string | null;
  tags?: string[];
  purchase_price?: string | null;
}

export interface CollectionCardUpdate {
  quantity?: number;
  condition?: string | null;
  language?: string | null;
  tags?: string[];
  purchase_price?: string | null;
}

export interface CollectionImportRequest {
  csv: string;
  mode: "merge" | "replace";
}

export interface CollectionImportResponse {
  imported: number;
  updated: number;
  removed: number;
  unresolved: string[];
}

// Deck Snapshots + Comparison
export type SnapshotSource = "manual" | "auto_stage";

export interface SnapshotSummary {
  id: string;
  deck_id: string;
  label: string | null;
  source: SnapshotSource;
  stage: string;
  deck_name: string;
  bracket: number | null;
  card_count: number;
  created_at: string;
}

export interface SnapshotCardItem {
  card_id: string;
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  color_identity: string[];
  image_uri: string | null;
  quantity: number;
  categories: string[];
  added_by: string;
  ai_reasoning: string | null;
}

export interface SnapshotDetailResponse {
  id: string;
  deck_id: string;
  label: string | null;
  source: SnapshotSource;
  stage: string;
  deck_name: string;
  bracket: number | null;
  stage_targets: Record<string, number>;
  archetype_tags: string[];
  created_at: string;
  cards: SnapshotCardItem[];
}

export interface SnapshotResponse {
  id: string;
  deck_id: string;
  label: string | null;
  source: SnapshotSource;
  stage: string;
  deck_name: string;
  bracket: number | null;
  stage_targets: Record<string, number>;
  archetype_tags: string[];
  created_at: string;
}

export interface DiffCardInfo {
  card_id: string;
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  image_uri: string | null;
  color_identity: string[];
}

export interface DiffEntry {
  card: DiffCardInfo;
  left_quantity: number;
  right_quantity: number;
  left_categories: string[];
  right_categories: string[];
}

export interface DeckDiff {
  added: DiffEntry[];
  removed: DiffEntry[];
  quantity_changed: DiffEntry[];
  common: DiffEntry[];
}

export type ComparisonKind = "deck" | "snapshot";

export interface ComparisonSideMeta {
  kind: ComparisonKind;
  id: string;
  deck_id: string;
  deck_name: string;
  label: string | null;
  stage: string;
  bracket: number | null;
  card_count: number;
}

export interface DeckCompareResponse {
  left: ComparisonSideMeta;
  right: ComparisonSideMeta;
  diff: DeckDiff;
}

// Preferences
export type PreferenceType =
  | "pet_card"
  | "avoid_card"
  | "avoid_archetype"
  | "general"
  | "feedback_boosting"
  | "user_profile_boosting";

export interface PreferenceCreate {
  preference_type: PreferenceType;
  card_scryfall_id?: string | null;
  description?: string | null;
}

export interface PreferenceResponse {
  id: string;
  account_id: string;
  preference_type: string;
  card_id: string | null;
  card_name: string | null;
  description: string | null;
  created_at: string;
}
