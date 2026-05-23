-- Migration 002: collapse interaction-flavored tags into a single 'interaction' tag,
-- fold removed 'utility' / 'bangers' / 'wipes' deck categories into 'theme' / 'interaction',
-- and clean up the simplified stage set on existing decks.

-- Rewrite cards.tags: any of the five old interaction tags -> 'interaction'.
UPDATE cards
SET tags = (
    SELECT ARRAY(
        SELECT DISTINCT CASE
            WHEN t IN ('removal', 'counterspell', 'board_wipe', 'protection', 'graveyard_hate')
                THEN 'interaction'
            ELSE t
        END
        FROM unnest(tags) AS t
    )
)
WHERE tags && ARRAY['removal', 'counterspell', 'board_wipe', 'protection', 'graveyard_hate'];

-- Rewrite deck_cards.categories: utility/bangers -> theme; wipes -> interaction.
UPDATE deck_cards
SET categories = (
    SELECT ARRAY(
        SELECT DISTINCT CASE
            WHEN c IN ('utility', 'bangers') THEN 'theme'
            WHEN c = 'wipes' THEN 'interaction'
            ELSE c
        END
        FROM unnest(categories) AS c
    )
)
WHERE categories && ARRAY['utility', 'bangers', 'wipes'];

-- Move any deck stuck on the removed 'utility' stage onto 'theme'.
UPDATE decks SET stage = 'theme' WHERE stage = 'utility';

-- Drop stale stage_targets keys for removed stages.
UPDATE decks
SET stage_targets = stage_targets - 'utility' - 'bangers' - 'wipes';
