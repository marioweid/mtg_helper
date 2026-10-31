export interface DiscoverFace {
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  power?: string | null;
  toughness?: string | null;
  loyalty?: string | null;
  defense?: string | null;
}

export interface DiscoverFacts extends DiscoverFace {
  oracle_id: string;
  mana_value: number | null;
  keywords: string[] | null;
  layout: string | null;
  faces: DiscoverFace[];
}

export interface DiscoverCandidate {
  oracle_id: string;
  facts: DiscoverFacts;
  image_uri?: string | null;
  state: "unassessed" | "assessed" | "failed";
  assessment: {
    fit: "core" | "support" | "conditional" | "weak" | "uncertain";
    reason: string;
    caveat: string;
    evidence: { key: string; quote: string }[];
  } | null;
  evidence_errors: string[];
  recommended: boolean;
  excluded: boolean;
}

export interface CommanderStrategyChoice {
  title: string;
  pace: string;
  early_game: string;
  engine: string;
  payoff: string;
  goal: string;
  explanation: string;
  uncertainties: string[];
}

export interface DiscoverRun {
  id: string;
  status: "running" | "completed" | "failed" | "interrupted" | "unknown";
  phase: string;
  goal: string;
  created_at: string;
  source_hash: string;
  rules_hash: string;
  profile: string;
  error: string | null;
  stale: boolean;
  candidates: DiscoverCandidate[];
  known_cost_microusd: number;
  held_microusd: number;
  strategies?: CommanderStrategyChoice[];
}

export interface StrategyTerm {
  id: string;
  slug: string;
  label: string;
}

export interface DiscoverStrategy {
  prose: string;
  queries: StrategyQuery[];
  revision: string;
  updated_at: string;
  needs_review: boolean;
}

export interface StrategyQuery {
  purpose: string;
  groups: { oracle_tag_ids: string[]; printed_keywords: string[] }[];
  card_types_any: (
    | "Creature"
    | "Artifact"
    | "Enchantment"
    | "Instant"
    | "Sorcery"
    | "Planeswalker"
    | "Battle"
  )[];
}

export interface DiscoverSourceStatus {
  status: "ready" | "stale" | "unavailable" | "mismatched";
  card_updated_at: string | null;
  tag_updated_at: string | null;
  warning: string | null;
}

export interface StrategyMatch {
  oracle_id: string;
  name: string;
  image_uri: string | null;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  keywords: string[];
  match_count: number;
  global_popularity_rank: number | null;
  evidence: {
    query_purpose: string;
    criterion_type: "oracle_tag" | "printed_keyword";
    criterion_id: string | null;
    criterion_label: string;
    matched_tag_id: string | null;
    matched_tag_label: string | null;
    relation: "direct" | "descendant" | "keyword";
  }[];
}

export interface StrategyMatches {
  status: "ready" | "stale" | "setup_needed" | "unavailable" | "mismatched";
  source: DiscoverSourceStatus;
  strategy: DiscoverStrategy | null;
  cards: StrategyMatch[];
  next_cursor: string | null;
  total: number;
}

export interface DiscoverTerms {
  oracle_tags: StrategyTerm[];
  printed_keywords: string[];
}

export interface TermSuggestionRun {
  id: string;
  status: "running" | "completed" | "failed" | "interrupted" | "unknown";
  error: string | null;
  queries: StrategyQuery[];
  strategy_revision: string | null;
  source_hash: string | null;
}

export interface DiscoverSetup {
  draft: DiscoverRun | null;
  suggestion: TermSuggestionRun | null;
  prose: string | null;
}
