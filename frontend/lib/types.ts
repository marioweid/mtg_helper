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
  category: string | null;
  added_by: string;
  ai_reasoning: string | null;
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
  owner_email: string | null;
  created_at: string;
  updated_at: string;
  stage_targets: Record<string, number>;
  suggestion_collection_ids: string[];
  max_price_cents: number | null;
  min_price_cents: number | null;
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
}

export interface DeckUpdate {
  name?: string;
  description?: string | null;
  bracket?: number;
  suggestion_collection_ids?: string[];
  max_price_cents?: number | null;
  min_price_cents?: number | null;
}

export interface DeckCardAdd {
  card_scryfall_id: string;
  quantity?: number;
  category?: string | null;
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
  category: string | null;
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
  category: string;
  reasoning: string;
  synergies: string[];
  highlight_reasons: string[] | null;
  price_eur_cents: number | null;
  owned_in: CollectionMembership[];
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

// Import
export interface DeckImportRequest {
  deck_list: string;
  name: string;
  description?: string | null;
  bracket?: number;
}

export interface DeckImportResponse {
  deck: DeckResponse;
  imported_count: number;
  unresolved: string[];
  color_violations: string[];
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
