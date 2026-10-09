export interface DiscoverQuery {
  purpose: string;
  oracle_text_all: string[];
  oracle_text_any: string[];
  type_line_any: string[];
  keywords_any: string[];
  mana_cost_all: string[];
  mana_value_min: number | null;
  mana_value_max: number | null;
}

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

export interface CommanderStrategyDraft {
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
  strategy?: CommanderStrategyDraft | null;
}

export interface DiscoverStatus {
  ready: boolean;
  reason: string | null;
  source_hash: string | null;
  rules_hash: string | null;
  catalog_updated_at: string | null;
  goal_seed: string;
  run: DiscoverRun | null;
  strategy_run?: DiscoverRun | null;
  strategy_cap_microusd?: number;
  strategy_reserved_microusd?: number;
  strategy_maximum_calls?: number;
  run_cap_microusd: number;
  daily_cap_microusd: number;
  reserved_microusd: number;
  maximum_calls: number;
}

export interface DiscoverPreview {
  name?: string;
  query?: DiscoverQuery | null;
  snapshot_hash?: string | null;
  rules_hash?: string | null;
  rule_query?: { purpose: string; text_all: string[]; text_any: string[]; cursor: string | null };
  cursor?: string | null;
  limit?: number;
}

export interface DiscoverPage {
  rules_hash: string;
  snapshot_hash: string;
  total: number;
  next_cursor: string | null;
  cards: DiscoverCandidate[];
  rule_results?: {
    rules_hash: string;
    matching_count: number;
    truncated: boolean;
    next_cursor: string | null;
    selected: { key: string; text: string }[];
  } | null;
}

export interface DiscoverGenerate {
  request_key: string;
  goal: string;
  constraint: DiscoverQuery | null;
  excluded_ids: string[];
}
