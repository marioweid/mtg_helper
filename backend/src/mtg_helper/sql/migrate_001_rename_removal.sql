-- Migration 001: rename category 'removal' -> 'interaction' in deck_cards
-- Run once against the database after deploying the code changes.
UPDATE deck_cards SET category = 'interaction' WHERE category = 'removal';
