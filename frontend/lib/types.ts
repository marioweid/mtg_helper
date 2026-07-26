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
  oracle_id?: string | null;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  oracle_text: string | null;
  color_identity: string[];
  image_uri: string | null;
  rarity: string | null;
  commander_legal: boolean;
  game_changer: boolean;
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
  archetype_tags: string[];
}

export interface DeckCardItem {
  deck_card_id: string;
  card_id: string;
  scryfall_id: string;
  oracle_id?: string | null;
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
  role_reasons: Record<string, string[]>;
  tags: string[];
  hub_tags: string[];
  mtgjson_tags: string[];
  price_eur_cents: number | null;
  owned_in: CollectionMembership[];
  game_changer: boolean;
  deck_fit_score?: number | null;
  deck_fit_band?: "strong" | "solid" | "weak" | null;
  deck_fit_reasons?: string[];
  deck_fit_protected?: boolean;
  planned_cut_quantity: number;
}

export interface ManaCurveRecommendation {
  source: "moxfield" | "fallback";
  deck_count: number;
  confidence: "high" | "fallback";
  buckets: Record<string, number>;
}

export interface DeckManaCurve {
  current: Record<string, number>;
  recommended: ManaCurveRecommendation;
  delta: Record<string, number>;
  progress_delta: Record<string, number>;
}

export interface CommanderCardSummary {
  id: string;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  image_uri: string | null;
  color_identity: string[];
  tags?: string[];
  hub_tags?: string[];
  mtgjson_tags?: string[];
  game_changer: boolean;
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
  archetype_tags: string[];
  mana_curve: DeckManaCurve | null;
  cards: DeckCardItem[];
  physical_card_count: number;
  planned_card_count: number;
  planned_changes: PlannedDeckChange[];
}

export interface DeckCreate {
  commander_scryfall_id: string;
  partner_scryfall_id?: string | null;
  name: string;
  description?: string | null;
  bracket?: number;
  stage_targets?: Record<string, number> | null;
  suggestion_collection_ids?: string[];
  archetype_tags?: string[];
}

export interface DeckUpdate {
  name?: string;
  description?: string | null;
  bracket?: number;
  suggestion_collection_ids?: string[];
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
  oracle_id?: string | null;
  name: string;
  quantity: number;
  categories: string[];
  added_by: string;
}

// AI
export interface CollectionMembership {
  id: string;
  name: string;
  quantity: number;
}

export type PlannedChangeDirection = "addition" | "cut";

export interface PlannedDeckChange {
  id: string;
  deck_id: string;
  card_id: string;
  scryfall_id: string;
  oracle_id?: string | null;
  name: string;
  image_uri: string | null;
  direction: PlannedChangeDirection;
  quantity: number;
  collection_id: string | null;
  physical_quantity: number;
  projected_quantity: number;
  categories: string[];
  added_by: "user" | "ai";
  ai_reasoning: string | null;
  owned_in: CollectionMembership[];
  created_at: string;
  updated_at: string;
}

export interface PlannedDeckChangeCreate {
  card_scryfall_id: string;
  direction: PlannedChangeDirection;
  quantity?: number;
  categories?: string[];
  added_by?: "user" | "ai";
  ai_reasoning?: string | null;
}

export interface PlannedDeckChangeUpdate {
  quantity?: number;
  collection_id?: string | null;
}

export interface PlannedShoppingListRequest {
  collection_ids: string[];
}

export interface CardSuggestion {
  scryfall_id: string;
  oracle_id?: string | null;
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
  game_changer: boolean;
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

export interface CommanderSuggestIntent {
  archetype_tags: string[];
  mechanic_tags: string[];
  traits: string[];
  token_types: string[];
  color_identity: string[] | null;
  exact_color_identity: boolean;
  excluded_colors: string[];
  bracket: number;
  direction: string;
  must_have: string[];
  avoid: string[];
  oracle_terms: string[];
  required_phrases: string[];
  excluded_phrases: string[];
}

export interface CommanderSuggestRequest {
  history: DescribeMessage[];
  message: string;
  intent_override?: CommanderSuggestIntent | null;
  limit?: number;
}

export interface CommanderSuggestion {
  card: CardResponse;
  score: number;
  score_reasons: string[];
  matched_tags: string[];
  matched_traits: string[];
  matched_token_types: string[];
  card_advantage_reasons: string[];
}

export interface CommanderSuggestResponse {
  reply: string;
  done: boolean;
  intent: CommanderSuggestIntent;
  commanders: CommanderSuggestion[];
  stage_targets: Record<string, number> | null;
  suggested_name: string | null;
}

export interface KeywordChip {
  tag: string;
  label: string;
  deck_count?: number | null;
}

export interface KeywordGroup {
  category: string;
  display_name: string;
  keywords: KeywordChip[];
}

/**
 * Total number of physical cards across rows. Sums ``quantity`` so basic-land
 * rows like "18 Forest" count as 18, not 1. Treats missing quantity as 1.
 */
export function totalCardCount(cards: DeckCardItem[]): number {
  return cards.reduce((sum, c) => sum + (c.quantity ?? 1), 0);
}

/**
 * Full deck size including the commander. Every Commander deck has exactly
 * one commander that counts toward the 100-card total, so an empty deck
 * with just a commander reads as 1/100 and a complete deck as 100/100.
 * Partner commanders are ignored — only the primary counts.
 */
export function deckTotal(deck: { cards: DeckCardItem[]; commander_card?: unknown }): number {
  return totalCardCount(deck.cards) + (deck.commander_card ? 1 : 0);
}

/**
 * Buckets a deck card belongs to. Explicit `categories` fully override the
 * auto-derived `qualifying_stages` — set any category and the auto tags are
 * suppressed. Clear categories to revert to auto. Cards with neither fall
 * into "untagged".
 */
export function bucketsFor(card: DeckCardItem): string[] {
  const source = card.categories.length > 0 ? card.categories : card.qualifying_stages;
  if (source.length === 0) return ["untagged"];
  return [...new Set(source)];
}

export function bucketReason(card: DeckCardItem, bucket: string): string | undefined {
  if (card.categories.includes(bucket)) return "Manual deck role override";
  const reasons = card.role_reasons?.[bucket] ?? [];
  if (reasons.length === 0) return undefined;
  return `Auto-counted because of: ${reasons.join(", ")}`;
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
export interface PlaytestSimulateRequest {
  trials?: number;
  turns?: number;
  on_the_play?: boolean;
  max_mulligans?: number;
  seed?: number | null;
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
  avg_color_dead_cards: number;
  avg_interaction_in_hand: number;
  avg_cards_drawn_extra: number;
  avg_selection_events: number;
  avg_tutors_cast: number;
  avg_cards_in_hand: number;
  lands_p25: number;
  lands_p50: number;
  lands_p75: number;
  mana_p25: number;
  mana_p50: number;
  mana_p75: number;
  avg_mana_unspent: number;
  avg_hand_lands: number;
  avg_hand_ramp: number;
  avg_hand_draw: number;
  avg_hand_interaction: number;
  avg_hand_tutors: number;
  avg_hand_other: number;
}

export interface PlaytestColorScrewStats {
  pct_color_screw: number;
  shortages_by_color: Record<string, number>;
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
  color_screw: PlaytestColorScrewStats;
  commander: PlaytestCommanderStats | null;
  partner: PlaytestCommanderStats | null;
  per_card: PlaytestCardSimStat[];
  top_stuck_cards: PlaytestStuckCard[];
  unpaid_cost_summary: PlaytestUnpaidCost[];
  sample_trials: PlaytestSampleTrial[];
  cast_rate_by_cmc: Record<string, number>;
  mulligan_reasons: PlaytestMulliganReasonStats;
  per_turn: PlaytestTurnStat[];
}

export interface PlaytestCommanderStats {
  name: string;
  avg_cast_turn: number;
  pct_ever_cast: number;
}

export interface PlaytestCardSimStat {
  name: string;
  quantity_in_deck: number;
  pct_drawn_by_end: number;
  avg_first_cast_turn: number;
  pct_ever_cast: number;
  pct_stuck_in_hand_at_end: number;
}

export interface PlaytestStuckCard {
  name: string;
  cost: string | null;
  pct_stuck: number;
  blocker: "mana" | "colors" | "never_drawn";
}

export interface PlaytestUnpaidCost {
  cost: string;
  pct_failed: number;
  missing_colors: string[];
}

export interface PlaytestSampleTrial {
  bucket: "best" | "median" | "worst";
  mulligans: number;
  commander_cast_turn: number | null;
  land_turns: number[];
  spells_cast_turns: [number, string][];
  stuck_at_end: string[];
}

export interface PlaytestMulliganReasonStats {
  total: number;
  low_lands: number;
  high_lands: number;
  no_commander_color: number;
  no_early_play: number;
}

export interface AnalysisFinding {
  category:
    | "mana_base"
    | "consistency"
    | "curve"
    | "commander"
    | "color_fix"
    | "card_quality";
  severity: "info" | "warn" | "critical";
  title: string;
  detail: string;
  evidence: string;
}

export interface AnalysisCardHit {
  scryfall_id?: string | null;
  name: string;
  mana_cost?: string | null;
  cmc?: number | null;
  type_line?: string | null;
  oracle_text?: string | null;
  color_identity?: string[];
  tags?: string[];
  price_eur_cents?: number | null;
}

export interface AnalysisSwapSuggestion {
  remove: string[];
  add: AnalysisCardHit[];
  reason: string;
}

export interface SimulationAnalysisResponse {
  summary: string;
  findings: AnalysisFinding[];
  swap_suggestions: AnalysisSwapSuggestion[];
  tool_call_count: number;
}

export type CommanderCoachMode = "auto" | "doctor" | "builder" | "mana" | "meta";
export type CommanderCoachResolvedMode =
  | "doctor"
  | "builder"
  | "mana"
  | "meta"
  | "memory"
  | "chat"
  | "replacement";

export interface DoctorCut {
  card_name: string;
  reason: string;
  confidence: "low" | "medium" | "high";
}

export interface DoctorAdd {
  card: AnalysisCardHit;
  reason: string;
  confidence: "low" | "medium" | "high";
}

export interface DoctorSwap {
  remove: string[];
  add: AnalysisCardHit[];
  reason: string;
}

export interface DeckDoctorResponse {
  summary: string;
  game_plan: string;
  findings: AnalysisFinding[];
  cuts: DoctorCut[];
  adds: DoctorAdd[];
  swaps: DoctorSwap[];
  tool_call_count: number;
}

export interface ReplacementOption {
  card: AnalysisCardHit;
  reason: string;
  role_match: "same_role" | "role_upgrade" | "theme_upgrade" | "role_change";
  tradeoff: string | null;
}

export interface TargetedReplacementResponse {
  target_card_name: string;
  summary: string;
  keep_reason: string | null;
  best_pick: AnalysisCardHit | null;
  options: ReplacementOption[];
  tool_call_count: number;
}

export interface CommanderCoachRequest {
  message: string;
  mode?: CommanderCoachMode;
  coach_memory_notes?: string | null;
}

export interface CoachMemoryResponse {
  deck_id: string;
  account_id: string;
  notes: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface CoachMemoryUpdate {
  notes: string;
}

export interface CommanderCoachResponse {
  mode: CommanderCoachResolvedMode;
  reply: string;
  doctor: DeckDoctorResponse | null;
  replacement: TargetedReplacementResponse | null;
  coach_memory: CoachMemoryResponse | null;
  memory_updated: boolean;
}

export interface CommanderCoachStartResponse {
  job_id: string;
}

export interface CommanderCoachProgressEvent {
  event: string;
  message: string;
}

// Optimizer
export type SearchDepth = "quick" | "thorough" | "exhaustive";

export interface OptimizeRequest {
  sim?: PlaytestSimulateRequest;
  max_price_cents?: number | null;
  max_swaps?: number;
  search_depth?: SearchDepth;
}

export interface ProposedSwap {
  out_card_id: string;
  out_scryfall_id: string;
  out_card_name: string;
  in_scryfall_id: string;
  in_card_name: string;
  reason: string;
  score_delta: number;
  price_delta_cents: number | null;
}

export interface OptimizationProposal {
  baseline_stats: PlaytestStats;
  final_stats: PlaytestStats;
  swaps: ProposedSwap[];
  total_score_delta: number;
  total_price_delta_cents: number | null;
}

export interface OptimizeStartResponse {
  job_id: string;
}

export interface Capabilities {
  optimizer: boolean;
}

export interface OptimizeJobStatus {
  status: "running" | "ok" | "error";
  phase: string;
  current: number;
  total: number;
  proposal: OptimizationProposal | null;
  error: string | null;
}

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

export type CollectionImportFormat = "moxfield" | "manabox";

export interface CollectionImportRequest {
  csv: string;
  mode: "merge" | "replace";
  format: CollectionImportFormat;
}

export interface CollectionImportResponse {
  imported: number;
  updated: number;
  removed: number;
  unresolved: string[];
}

export interface CollectionUrlImportRequest {
  url: string;
  mode: "merge" | "replace";
}

export interface CollectionFromUrlRequest {
  url: string;
  name?: string;
}

export interface CollectionFromUrlResponse {
  collection: CollectionResponse;
  import: CollectionImportResponse;
}

// Deck Snapshots + Comparison
export type SnapshotSource = "manual" | "auto_stage" | "revision";

export type DeckRevisionSource = "selected_plans" | "single_plan";

export interface DeckRevisionChange {
  card_id: string;
  card_name: string;
  image_uri: string | null;
  direction: "addition" | "cut";
  quantity: number;
  categories: string[];
  added_by: "user" | "ai";
  ai_reasoning: string | null;
  collection_id: string | null;
  collection_name: string | null;
  plan_created_at: string;
  plan_updated_at: string;
}

export interface DeckRevision {
  id: string;
  deck_id: string;
  title: string;
  note: string | null;
  source: DeckRevisionSource;
  before_snapshot_id: string;
  after_snapshot_id: string;
  created_at: string;
  changes: DeckRevisionChange[];
}

export interface DeckRevisionCreate {
  title: string;
  note?: string | null;
  plan_ids: string[];
}

export interface DeckRevisionUpdate {
  title?: string;
  note?: string | null;
}

export type TopPickSource = "combined" | "moxfield" | "archidekt";

export interface TopPickSourceSummary {
  source: "moxfield" | "archidekt";
  deck_count: number;
  fetched_at: string | null;
  stale: boolean;
  error: string | null;
}

export interface TopPickCard {
  card_id: string;
  scryfall_id: string;
  oracle_id?: string | null;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  image_uri: string | null;
  price_eur_cents: number | null;
  combined_score: number;
  moxfield_count: number;
  moxfield_sample_size: number;
  moxfield_rate: number;
  archidekt_count: number;
  archidekt_sample_size: number;
  archidekt_rate: number;
  physical_quantity: number;
  plan_direction: "addition" | "cut" | null;
  planned_quantity: number;
  owned_in: CollectionMembership[];
}

export interface TopPicksResponse {
  commander_name: string;
  source: TopPickSource;
  sources: TopPickSourceSummary[];
  picks: TopPickCard[];
}

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
  price_eur_cents: number | null;
  owned_in: CollectionMembership[];
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
  mana_curve: DeckManaCurve | null;
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
