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
    card_types      TEXT[] NOT NULL DEFAULT '{}',
    subtypes        TEXT[] NOT NULL DEFAULT '{}',
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

-- Type/subtype filtering (soft boosting)
CREATE INDEX IF NOT EXISTS idx_cards_card_types ON cards USING GIN (card_types);
CREATE INDEX IF NOT EXISTS idx_cards_subtypes ON cards USING GIN (subtypes);

-- ============================================================
-- ACCOUNTS
-- ============================================================
CREATE TABLE IF NOT EXISTS accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- DECKS
-- ============================================================
CREATE TABLE IF NOT EXISTS decks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID REFERENCES accounts(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    commander_id    UUID NOT NULL REFERENCES cards(id),
    partner_id      UUID REFERENCES cards(id),
    description     TEXT,
    bracket         INTEGER CHECK (bracket BETWEEN 1 AND 4),
    stage           TEXT NOT NULL DEFAULT 'created',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- DECK CARDS
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    category        TEXT,
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
-- DECK FEEDBACK (per-deck thumbs up/down)
-- ============================================================
CREATE TABLE IF NOT EXISTS deck_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id),
    feedback        TEXT NOT NULL CHECK (feedback IN ('up', 'down')),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deck_feedback_deck_id ON deck_feedback (deck_id);

-- ============================================================
-- CONVERSATION TURNS (AI chat history per deck)
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    turn_order      INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- VIEW: deck detail with full card info
-- ============================================================
CREATE OR REPLACE VIEW deck_detail_view AS
SELECT
    dc.deck_id,
    dc.id          AS deck_card_id,
    dc.quantity,
    dc.category,
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
    c.rarity
FROM deck_cards dc
JOIN cards c ON dc.card_id = c.id;
