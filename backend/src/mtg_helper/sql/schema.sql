-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- CARDS (populated from Scryfall bulk data)
-- ============================================================
CREATE TABLE IF NOT EXISTS cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scryfall_id     UUID UNIQUE NOT NULL,
    oracle_id       UUID,
    name            TEXT NOT NULL,
    mana_cost       TEXT,
    cmc             DECIMAL,
    type_line       TEXT,
    oracle_text     TEXT,
    color_identity  TEXT[] NOT NULL DEFAULT '{}',
    colors          TEXT[] NOT NULL DEFAULT '{}',
    keywords        TEXT[] NOT NULL DEFAULT '{}',
    power           TEXT,
    toughness       TEXT,
    legalities      JSONB NOT NULL DEFAULT '{}',
    image_uri       TEXT,
    prices          JSONB NOT NULL DEFAULT '{}',
    rarity          TEXT,
    set_code        TEXT,
    released_at     DATE,
    edhrec_rank     INTEGER,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    hub_tags        TEXT[] NOT NULL DEFAULT '{}',
    mtgjson_tags     TEXT[] NOT NULL DEFAULT '{}',
    traits          TEXT[] NOT NULL DEFAULT '{}',
    card_types      TEXT[] NOT NULL DEFAULT '{}',
    subtypes        TEXT[] NOT NULL DEFAULT '{}',
    token_types     TEXT[] NOT NULL DEFAULT '{}',
    border_color    TEXT,
    security_stamp  TEXT,
    game_changer    BOOLEAN NOT NULL DEFAULT false,
    embedded_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fuzzy name search
CREATE INDEX IF NOT EXISTS idx_cards_name_trgm
    ON cards USING GIN (name gin_trgm_ops);

-- Color identity subset filtering
CREATE INDEX IF NOT EXISTS idx_cards_color_identity
    ON cards USING GIN (color_identity);

-- Full-text search on oracle text
CREATE INDEX IF NOT EXISTS idx_cards_oracle_text_fts
    ON cards USING GIN (to_tsvector('english', COALESCE(oracle_text, '')));

-- Type line partial match
CREATE INDEX IF NOT EXISTS idx_cards_type_line_trgm
    ON cards USING GIN (type_line gin_trgm_ops);

-- Legality JSONB filtering
CREATE INDEX IF NOT EXISTS idx_cards_legalities
    ON cards USING GIN (legalities);

-- Mana value range queries
CREATE INDEX IF NOT EXISTS idx_cards_cmc ON cards (cmc);

-- Tag-based filtering (hybrid retrieval)
CREATE INDEX IF NOT EXISTS idx_cards_tags ON cards USING GIN (tags);

-- Mechanical trait filtering (etb, activated, evasion)
CREATE INDEX IF NOT EXISTS idx_cards_traits ON cards USING GIN (traits);

-- Type/subtype filtering (soft boosting)
CREATE INDEX IF NOT EXISTS idx_cards_card_types ON cards USING GIN (card_types);
CREATE INDEX IF NOT EXISTS idx_cards_subtypes ON cards USING GIN (subtypes);
CREATE INDEX IF NOT EXISTS idx_cards_token_types ON cards USING GIN (token_types);

-- ============================================================
-- MTGJSON CARD METADATA (sidecar enrichment + diff source)
-- ============================================================
CREATE TABLE IF NOT EXISTS mtgjson_card_metadata (
    scryfall_id       UUID PRIMARY KEY,
    mtgjson_uuid      UUID NOT NULL,
    name              TEXT NOT NULL,
    keywords          TEXT[] NOT NULL DEFAULT '{}',
    types             TEXT[] NOT NULL DEFAULT '{}',
    supertypes        TEXT[] NOT NULL DEFAULT '{}',
    subtypes          TEXT[] NOT NULL DEFAULT '{}',
    edhrec_saltiness  NUMERIC,
    is_funny          BOOLEAN NOT NULL DEFAULT false,
    is_online_only    BOOLEAN NOT NULL DEFAULT false,
    is_rebalanced     BOOLEAN NOT NULL DEFAULT false,
    is_game_changer   BOOLEAN NOT NULL DEFAULT false,
    leadership_skills JSONB NOT NULL DEFAULT '{}',
    related_cards     JSONB NOT NULL DEFAULT '{}',
    raw_identifiers   JSONB NOT NULL DEFAULT '{}',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mtgjson_card_metadata_keywords
    ON mtgjson_card_metadata USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_mtgjson_card_metadata_types
    ON mtgjson_card_metadata USING GIN (types);
CREATE INDEX IF NOT EXISTS idx_mtgjson_card_metadata_supertypes
    ON mtgjson_card_metadata USING GIN (supertypes);
CREATE INDEX IF NOT EXISTS idx_mtgjson_card_metadata_subtypes
    ON mtgjson_card_metadata USING GIN (subtypes);

-- ============================================================
-- MTGJSON OFFICIAL KEYWORD CATALOG
-- ============================================================
CREATE TABLE IF NOT EXISTS mtgjson_keywords (
    keyword         TEXT PRIMARY KEY,
    tag             TEXT UNIQUE NOT NULL,
    label           TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN (
        'ability_word', 'keyword_ability', 'keyword_action'
    )),
    mtgjson_version TEXT,
    mtgjson_date    DATE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mtgjson_keywords_category
    ON mtgjson_keywords (category, label);

-- ============================================================
-- MOXFIELD HUB CATALOG + CARD MEMBERSHIP
-- ============================================================
CREATE TABLE IF NOT EXISTS moxfield_hubs (
    id                INTEGER PRIMARY KEY,
    slug              TEXT UNIQUE NOT NULL,
    tag               TEXT UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT,
    shows_in_decklist BOOLEAN NOT NULL DEFAULT false,
    active            BOOLEAN NOT NULL DEFAULT true,
    enabled           BOOLEAN NOT NULL DEFAULT true,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at         TIMESTAMPTZ,
    last_card_sync_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_moxfield_hubs_active_name
    ON moxfield_hubs (active, name);

CREATE TABLE IF NOT EXISTS moxfield_hub_card_stats (
    hub_id               INTEGER NOT NULL REFERENCES moxfield_hubs(id) ON DELETE CASCADE,
    card_id              UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    hub_deck_count       INTEGER NOT NULL,
    baseline_deck_count  INTEGER NOT NULL,
    hub_deck_pct         REAL NOT NULL,
    baseline_deck_pct    REAL NOT NULL,
    synergy_score        REAL NOT NULL,
    hub_sample_size      INTEGER NOT NULL,
    baseline_sample_size INTEGER NOT NULL,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (hub_id, card_id)
);

CREATE INDEX IF NOT EXISTS idx_moxfield_hub_card_stats_card
    ON moxfield_hub_card_stats (card_id);
CREATE INDEX IF NOT EXISTS idx_moxfield_hub_card_stats_hub_score
    ON moxfield_hub_card_stats (hub_id, synergy_score DESC);

-- ============================================================
-- ARCHIDEKT TAG CATALOG + CARD MEMBERSHIP
-- ============================================================
CREATE TABLE IF NOT EXISTS archidekt_tags (
    id                BIGSERIAL PRIMARY KEY,
    slug              TEXT UNIQUE NOT NULL,
    tag               TEXT UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT,
    active            BOOLEAN NOT NULL DEFAULT true,
    enabled           BOOLEAN NOT NULL DEFAULT true,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at         TIMESTAMPTZ,
    last_card_sync_at TIMESTAMPTZ,
    last_error        TEXT,
    last_error_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_archidekt_tags_active_name
    ON archidekt_tags (active, enabled, name);

CREATE TABLE IF NOT EXISTS archidekt_tag_card_stats (
    tag_id                BIGINT NOT NULL REFERENCES archidekt_tags(id) ON DELETE CASCADE,
    card_id               UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    tag_deck_count        INTEGER NOT NULL,
    baseline_deck_count   INTEGER NOT NULL,
    tag_deck_pct          REAL NOT NULL,
    baseline_deck_pct     REAL NOT NULL,
    synergy_score         REAL NOT NULL,
    tag_sample_size       INTEGER NOT NULL,
    baseline_sample_size  INTEGER NOT NULL,
    fetched_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tag_id, card_id)
);

CREATE INDEX IF NOT EXISTS idx_archidekt_tag_card_stats_card
    ON archidekt_tag_card_stats (card_id);
CREATE INDEX IF NOT EXISTS idx_archidekt_tag_card_stats_score
    ON archidekt_tag_card_stats (tag_id, synergy_score DESC);

-- ============================================================
-- SHARED, ADMIN-CURATED THEME GROUPS
-- ============================================================
CREATE TABLE IF NOT EXISTS theme_groups (
    id          BIGSERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    label       TEXT NOT NULL,
    description TEXT,
    aliases     TEXT[] NOT NULL DEFAULT '{}',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE theme_groups ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS theme_group_members (
    id                BIGSERIAL PRIMARY KEY,
    group_id          BIGINT NOT NULL REFERENCES theme_groups(id) ON DELETE CASCADE,
    source            TEXT NOT NULL CHECK (source IN ('moxfield', 'archidekt')),
    moxfield_hub_id   INTEGER REFERENCES moxfield_hubs(id) ON DELETE CASCADE,
    archidekt_tag_id  BIGINT REFERENCES archidekt_tags(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (source = 'moxfield' AND moxfield_hub_id IS NOT NULL AND archidekt_tag_id IS NULL)
        OR
        (source = 'archidekt' AND archidekt_tag_id IS NOT NULL AND moxfield_hub_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_theme_member_moxfield_unique
    ON theme_group_members (moxfield_hub_id) WHERE moxfield_hub_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_theme_member_archidekt_unique
    ON theme_group_members (archidekt_tag_id) WHERE archidekt_tag_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_theme_groups_visible
    ON theme_groups (enabled, deleted_at, sort_order, label);

-- ============================================================
-- ACCOUNTS
-- ============================================================
CREATE TABLE IF NOT EXISTS accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    TEXT NOT NULL,
    google_sub      TEXT UNIQUE,
    email           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Email is the canonical owner key for decks. Enforce case-insensitive uniqueness.
CREATE UNIQUE INDEX IF NOT EXISTS accounts_email_unique_idx
    ON accounts (lower(email)) WHERE email IS NOT NULL;

-- ============================================================
-- DECKS
-- ============================================================
CREATE TABLE IF NOT EXISTS decks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_email     TEXT,
    name            TEXT NOT NULL,
    commander_id    UUID NOT NULL REFERENCES cards(id),
    partner_id      UUID REFERENCES cards(id),
    description     TEXT,
    bracket         INTEGER CHECK (bracket BETWEEN 1 AND 5),
    stage           TEXT NOT NULL DEFAULT 'created',
    stage_targets   JSONB NOT NULL DEFAULT '{}',
    archetype_tags  TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backfill column on pre-existing decks tables (older deployments). Must run
-- before the GIN index below or `CREATE INDEX` fails on prod with
-- "column archetype_tags does not exist".
ALTER TABLE decks ADD COLUMN IF NOT EXISTS archetype_tags TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_decks_archetype_tags
    ON decks USING GIN (archetype_tags);

-- ============================================================
-- DECK CARDS
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    categories      TEXT[] NOT NULL DEFAULT '{}',
    added_by        TEXT NOT NULL DEFAULT 'user' CHECK (added_by IN ('user', 'ai')),
    ai_reasoning    TEXT,
    UNIQUE (deck_id, card_id)
);

-- ============================================================
-- PREFERENCES (account-level)
-- ============================================================
CREATE TABLE IF NOT EXISTS preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    preference_type TEXT NOT NULL CHECK (preference_type IN (
        'pet_card', 'avoid_card', 'avoid_archetype', 'general', 'feedback_boosting',
        'user_profile_boosting'
    )),
    card_id         UUID REFERENCES cards(id),
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_preferences_feedback_boosting
    ON preferences (account_id) WHERE preference_type = 'feedback_boosting';

CREATE UNIQUE INDEX IF NOT EXISTS idx_preferences_user_profile_boosting
    ON preferences (account_id) WHERE preference_type = 'user_profile_boosting';

-- ============================================================
-- DECK FEEDBACK (per-deck thumbs up/down/reject)
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    feedback        TEXT NOT NULL CHECK (feedback IN ('up', 'down', 'reject')),
    reject_count    INT NOT NULL DEFAULT 0,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_deck_feedback_deck_card
    ON deck_feedback (deck_id, card_id);

CREATE INDEX IF NOT EXISTS idx_deck_feedback_deck_id ON deck_feedback (deck_id);

-- ============================================================
-- DECK COACH MEMORY (per-account, per-deck notes for Commander Coach)
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_coach_memory (
    deck_id     UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    account_id  UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (deck_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_deck_coach_memory_account
    ON deck_coach_memory (account_id, updated_at DESC);

-- Deck chat feature was removed; drop the legacy conversation_turns table on
-- existing databases. Safe no-op if the table was never created.
DROP TABLE IF EXISTS conversation_turns;

-- ============================================================
-- DECK SNAPSHOTS (point-in-time copies of a deck for history + diffing)
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    label           TEXT,
    source          TEXT NOT NULL CHECK (source IN ('manual', 'auto_stage')),
    stage           TEXT NOT NULL,
    deck_name       TEXT NOT NULL,
    bracket         INTEGER,
    stage_targets   JSONB NOT NULL DEFAULT '{}',
    archetype_tags  TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deck_snapshots_deck_id
    ON deck_snapshots (deck_id, created_at DESC);

CREATE TABLE IF NOT EXISTS deck_snapshot_cards (
    snapshot_id     UUID NOT NULL REFERENCES deck_snapshots(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    quantity        INTEGER NOT NULL,
    categories      TEXT[] NOT NULL DEFAULT '{}',
    added_by        TEXT NOT NULL DEFAULT 'user' CHECK (added_by IN ('user', 'ai')),
    ai_reasoning    TEXT,
    PRIMARY KEY (snapshot_id, card_id)
);

-- ============================================================
-- ACCOUNT RANKING WEIGHTS (per-user signal weight overrides)
-- ============================================================
CREATE TABLE IF NOT EXISTS account_ranking_weights (
    account_id  UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    semantic    REAL NOT NULL DEFAULT 0.25,
    synergy     REAL NOT NULL DEFAULT 0.22,
    popularity  REAL NOT NULL DEFAULT 0.20,
    personal    REAL NOT NULL DEFAULT 0.15,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- COLLECTIONS (per-account, named, Moxfield-importable)
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);

CREATE INDEX IF NOT EXISTS idx_collections_account ON collections(account_id);

-- ============================================================
-- COLLECTION CARDS (printings owned, keyed by card_id + foil)
-- ============================================================
CREATE TABLE IF NOT EXISTS collection_cards (
    collection_id     UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    card_id           UUID NOT NULL REFERENCES cards(id),
    set_code          TEXT NOT NULL DEFAULT '',
    collector_number  TEXT NOT NULL DEFAULT '',
    foil              BOOL NOT NULL DEFAULT FALSE,
    quantity          INT  NOT NULL DEFAULT 1 CHECK (quantity > 0),
    condition         TEXT,
    language          TEXT,
    tags              TEXT[] NOT NULL DEFAULT '{}',
    purchase_price    NUMERIC,
    last_modified     TIMESTAMPTZ,
    PRIMARY KEY (collection_id, card_id, set_code, collector_number, foil)
);

CREATE INDEX IF NOT EXISTS idx_collection_cards_card ON collection_cards(card_id);

-- ============================================================
-- PLANNED DECK CHANGES (overlay; never part of physical calculations)
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_card_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    direction       TEXT NOT NULL CHECK (direction IN ('addition', 'cut')),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    collection_id   UUID REFERENCES collections(id) ON DELETE SET NULL,
    categories      TEXT[] NOT NULL DEFAULT '{}',
    added_by        TEXT NOT NULL DEFAULT 'user' CHECK (added_by IN ('user', 'ai')),
    ai_reasoning    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (deck_id, card_id)
);

CREATE INDEX IF NOT EXISTS idx_deck_card_plans_deck
    ON deck_card_plans (deck_id, direction, created_at);

-- ============================================================
-- MIGRATIONS (idempotent column additions for existing DBs)
-- ============================================================
DROP VIEW IF EXISTS deck_detail_view;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS border_color TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS security_stamp TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS game_changer BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS hub_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE cards DROP COLUMN IF EXISTS edhrec_tags;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS mtgjson_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE moxfield_hubs ADD COLUMN IF NOT EXISTS last_card_sync_at TIMESTAMPTZ;
ALTER TABLE moxfield_hubs ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true;
UPDATE cards
SET mtgjson_tags = tags
WHERE cardinality(mtgjson_tags) = 0
  AND cardinality(hub_tags) = 0
  AND cardinality(tags) > 0;
CREATE INDEX IF NOT EXISTS idx_cards_hub_tags ON cards USING GIN (hub_tags);
CREATE INDEX IF NOT EXISTS idx_cards_mtgjson_tags ON cards USING GIN (mtgjson_tags);
ALTER TABLE decks ADD COLUMN IF NOT EXISTS stage_targets JSONB NOT NULL DEFAULT '{}';
ALTER TABLE deck_feedback ADD COLUMN IF NOT EXISTS reject_count INT NOT NULL DEFAULT 0;
ALTER TABLE deck_feedback DROP CONSTRAINT IF EXISTS deck_feedback_feedback_check;
ALTER TABLE deck_feedback ADD CONSTRAINT deck_feedback_feedback_check
    CHECK (feedback IN ('up', 'down', 'reject'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_deck_feedback_deck_card ON deck_feedback (deck_id, card_id);
ALTER TABLE preferences DROP CONSTRAINT IF EXISTS preferences_preference_type_check;
ALTER TABLE preferences ADD CONSTRAINT preferences_preference_type_check
    CHECK (preference_type IN (
        'pet_card', 'avoid_card', 'avoid_archetype', 'general',
        'feedback_boosting', 'user_profile_boosting'
    ));

-- Collection filter: per-deck list of collections that scope suggestions.
-- Empty array = no filtering; non-empty = candidates restricted to the UNION of owned cards.
ALTER TABLE decks DROP CONSTRAINT IF EXISTS decks_collection_mode_check;
ALTER TABLE decks DROP CONSTRAINT IF EXISTS decks_collection_threshold_check;
ALTER TABLE decks DROP COLUMN IF EXISTS collection_mode;
ALTER TABLE decks DROP COLUMN IF EXISTS collection_id;
ALTER TABLE decks DROP COLUMN IF EXISTS collection_threshold;
ALTER TABLE decks
    ADD COLUMN IF NOT EXISTS suggestion_collection_ids UUID[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_decks_suggestion_collections
    ON decks USING GIN (suggestion_collection_ids);

-- Deck-level price range removed; price is now a per-request build filter only.
ALTER TABLE decks DROP CONSTRAINT IF EXISTS decks_max_price_cents_check;
ALTER TABLE decks DROP CONSTRAINT IF EXISTS decks_min_price_cents_check;
ALTER TABLE decks DROP COLUMN IF EXISTS max_price_cents;
ALTER TABLE decks DROP COLUMN IF EXISTS min_price_cents;

-- deck_cards: replace single `category TEXT` with `categories TEXT[]` so a card
-- can belong to multiple buckets (e.g. ramp + draw) the way the wizard already
-- counts them via qualifying_stages. Backfill from the old column then drop it.
-- The deck_detail_view depends on the column, so drop the view first; the
-- CREATE OR REPLACE VIEW at the bottom of this file rebuilds it against the
-- new column.
ALTER TABLE deck_cards
    ADD COLUMN IF NOT EXISTS categories TEXT[] NOT NULL DEFAULT '{}';
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deck_cards' AND column_name = 'category'
    ) THEN
        UPDATE deck_cards
        SET categories = ARRAY[category]
        WHERE category IS NOT NULL
          AND (categories IS NULL OR cardinality(categories) = 0);
        DROP VIEW IF EXISTS deck_detail_view;
        ALTER TABLE deck_cards DROP COLUMN category;
    END IF;
END $$;

ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_collection_threshold_check;
ALTER TABLE accounts DROP COLUMN IF EXISTS collection_suggestions_enabled;
ALTER TABLE accounts DROP COLUMN IF EXISTS default_collection_id;
ALTER TABLE accounts DROP COLUMN IF EXISTS collection_threshold;

-- Google Sign-In identity columns. google_sub is the OIDC subject claim;
-- email is denormalized for admin gating + display.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS google_sub TEXT;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS email TEXT;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_google_sub_key'
    ) THEN
        ALTER TABLE accounts ADD CONSTRAINT accounts_google_sub_key UNIQUE (google_sub);
    END IF;
END $$;
-- Replace non-unique email index with case-insensitive unique index.
DROP INDEX IF EXISTS accounts_email_idx;
CREATE UNIQUE INDEX IF NOT EXISTS accounts_email_unique_idx
    ON accounts (lower(email)) WHERE email IS NOT NULL;

-- Migrate deck ownership from owner_id (UUID FK) to owner_email (TEXT).
-- Email is unique app-wide, immutable enough for ownership, and avoids
-- orphaning when the accounts row is recreated under a new UUID.
ALTER TABLE decks ADD COLUMN IF NOT EXISTS owner_email TEXT;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'decks' AND column_name = 'owner_id'
    ) THEN
        EXECUTE $mig$
            UPDATE decks d
               SET owner_email = a.email
              FROM accounts a
             WHERE d.owner_email IS NULL
               AND d.owner_id = a.id
               AND a.email IS NOT NULL
        $mig$;
        ALTER TABLE decks DROP CONSTRAINT IF EXISTS decks_owner_id_fkey;
        ALTER TABLE decks DROP COLUMN IF EXISTS owner_id;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_decks_owner_email ON decks (lower(owner_email));

-- Commander-deck inclusion signal. Moxfield top commander decks are the source of truth.
ALTER TABLE account_ranking_weights
    ADD COLUMN IF NOT EXISTS deck_inclusion REAL NOT NULL DEFAULT 0.20;
ALTER TABLE account_ranking_weights
    ALTER COLUMN popularity SET DEFAULT 0.10;

-- ============================================================
-- MOXFIELD TOP-DECK RECOMMENDATIONS (cached per commander)
-- ============================================================
CREATE TABLE IF NOT EXISTS moxfield_commander_recs (
    commander_id      UUID PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    moxfield_card_id  TEXT,
    payload           JSONB NOT NULL,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-commander Moxfield top-decks inclusion weight.
ALTER TABLE account_ranking_weights
    ADD COLUMN IF NOT EXISTS moxfield_inclusion REAL NOT NULL DEFAULT 0.20;

-- Fraction of each result page reserved for trusted Moxfield cards.
-- 1.0 = historical "all trusted first"; lower values free slots for the
-- composite (keyword + tag + FTS) channel so user-supplied chips matter.
ALTER TABLE account_ranking_weights
    ADD COLUMN IF NOT EXISTS trusted_quota REAL NOT NULL DEFAULT 1.0;

DROP TABLE IF EXISTS edhrec_theme_index;
DROP TABLE IF EXISTS edhrec_commander_recs;
DROP TABLE IF EXISTS edhrec_tags;

-- ============================================================
-- FEATURE FLAGS (runtime toggles; admin-set overrides)
-- ============================================================
-- account_id NULL = global scope. A primary key cannot span a nullable
-- column, so uniqueness is enforced by two partial indexes instead.
CREATE TABLE IF NOT EXISTS feature_flags (
    flag       TEXT NOT NULL,
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    enabled    BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE feature_flags
    ALTER COLUMN account_id TYPE UUID USING account_id::UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'feature_flags'::regclass
          AND conname = 'feature_flags_account_id_fkey'
    ) THEN
        ALTER TABLE feature_flags
            ADD CONSTRAINT feature_flags_account_id_fkey
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS feature_flags_global_idx
    ON feature_flags (flag) WHERE account_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS feature_flags_account_idx
    ON feature_flags (flag, account_id) WHERE account_id IS NOT NULL;

-- ============================================================
-- VIEW: deck detail with full card info
-- ============================================================
DROP VIEW IF EXISTS deck_detail_view;
CREATE OR REPLACE VIEW deck_detail_view AS
SELECT
    dc.deck_id,
    dc.id          AS deck_card_id,
    dc.quantity,
    dc.categories,
    dc.added_by,
    dc.ai_reasoning,
    c.id           AS card_id,
    c.scryfall_id,
    c.name,
    c.mana_cost,
    c.cmc,
    c.type_line,
    c.oracle_text,
    c.color_identity,
    c.image_uri,
    c.rarity,
    c.tags,
    c.hub_tags,
    c.mtgjson_tags,
    CASE
        WHEN (c.prices->>'eur') IS NULL THEN NULL
        ELSE ROUND((c.prices->>'eur')::numeric * 100)::integer
    END           AS price_eur_cents,
    c.power,
    c.game_changer
FROM deck_cards dc
JOIN cards c ON dc.card_id = c.id;
