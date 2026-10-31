"""Immutable flat-match baseline used only by preserved offline research replays."""

# ruff: noqa: E501 -- preserve the measured SQL verbatim; this is not the runtime matcher.
MATCH_SQL = """
WITH tag_hits AS MATERIALIZED (
    SELECT DISTINCT m.oracle_id, selected.tag_id AS criterion_id, m.tag_id AS matched_tag_id
    FROM unnest($1::uuid[]) selected(tag_id)
    JOIN scryfall_tag_descendants d ON d.ancestor_id=selected.tag_id
    JOIN scryfall_tag_memberships m ON m.tag_id=d.descendant_id
    /* exact tag identity */
), keyword_hits AS MATERIALIZED (
    SELECT DISTINCT n.oracle_id, selected.keyword
    FROM unnest($2::text[]) selected(keyword)
    CROSS JOIN new_card_catalog n
    JOIN new_card_catalog_state s ON s.generation=n.generation
    WHERE COALESCE(n.source_facts->'keywords','[]'::jsonb) ? selected.keyword
    /* exact keyword identity */
), hits AS (
    SELECT oracle_id, 'tag:' || criterion_id::text AS criterion FROM tag_hits
    UNION ALL SELECT oracle_id, 'keyword:' || keyword FROM keyword_hits
), scores AS (
    SELECT oracle_id, count(DISTINCT criterion)::integer AS match_count
    FROM hits GROUP BY oracle_id
), eligible AS MATERIALIZED (
    SELECT c.id, c.oracle_id, c.name, scores.match_count
    FROM scores JOIN cards c ON c.oracle_id=scores.oracle_id AND c.is_canonical
    JOIN new_card_catalog n ON n.oracle_id=c.oracle_id
    JOIN new_card_catalog_state s ON s.generation=n.generation
    WHERE n.source_facts->'legalities'->>'commander'='legal'
      AND c.legalities->>'commander'='legal'
      AND COALESCE(n.source_facts->'games','[]'::jsonb) ? 'paper'
      AND COALESCE(n.source_facts->>'layout','normal') NOT IN
          ('token','double_faced_token','art_series','emblem','planar','scheme')
      AND COALESCE(n.source_facts->>'border_color','black') NOT IN ('silver','gold')
      AND COALESCE(n.source_facts->>'security_stamp','') <> 'acorn'
      AND COALESCE(n.source_facts->>'set_type','') NOT IN ('memorabilia','token','vanguard')
      AND COALESCE(n.source_facts->'card_faces'->0->>'type_line',
          n.source_facts->>'type_line','') NOT LIKE '%Land%'
      AND COALESCE(n.source_facts->>'type_line','') NOT LIKE '%Conspiracy%'
      AND c.color_identity <@ $3::text[] AND n.oracle_id <> ALL($4::uuid[])
      AND NOT EXISTS (SELECT 1 FROM deck_cards dc JOIN cards owned ON owned.id=dc.card_id
          WHERE dc.deck_id=$5 AND owned.oracle_id=n.oracle_id)
      AND NOT EXISTS (SELECT 1 FROM deck_card_plans p JOIN cards planned ON planned.id=p.card_id
          WHERE p.deck_id=$5 AND p.direction='addition' AND planned.oracle_id=n.oracle_id)
      AND NOT EXISTS (SELECT 1 FROM discover_dismissals d
          WHERE d.deck_id=$5 AND d.account_id=$6 AND d.oracle_id=n.oracle_id)
), page AS MATERIALIZED (
    SELECT eligible.*, lower(name) AS sort_name FROM eligible
    WHERE $7::integer IS NULL OR match_count < $7
        OR (match_count=$7 AND (lower(name),oracle_id::text)>($8,$9))
    ORDER BY match_count DESC, lower(name), oracle_id::text LIMIT $10
), details AS (
    SELECT page.*, c.image_uri, n.source_facts, evidence.items AS evidence
    FROM page JOIN cards c ON c.id=page.id
    JOIN new_card_catalog n ON n.oracle_id=page.oracle_id
    CROSS JOIN LATERAL (
        SELECT jsonb_agg(item ORDER BY item::text) AS items FROM (
            SELECT jsonb_build_object('criterion_id',h.criterion_id::text,
                'criterion_label',COALESCE(t.metadata->>'label',t.slug),
                'matched_tag_id',h.matched_tag_id::text,
                'matched_tag_label',COALESCE(m.metadata->>'label',m.slug),
                'relation',CASE WHEN h.criterion_id=h.matched_tag_id
                    THEN 'direct' ELSE 'descendant' END) AS item
            FROM tag_hits h JOIN scryfall_tags t ON t.id=h.criterion_id
            JOIN scryfall_tags m ON m.id=h.matched_tag_id
            WHERE h.oracle_id=page.oracle_id
            UNION ALL
            SELECT jsonb_build_object('criterion_id',NULL,'criterion_label',h.keyword,
                'matched_tag_id',NULL,'matched_tag_label',NULL,'relation','keyword')
            FROM keyword_hits h WHERE h.oracle_id=page.oracle_id
        ) matched
    ) evidence
)
SELECT totals.total, details.* FROM (SELECT count(*)::integer AS total FROM eligible) totals
LEFT JOIN details ON true
ORDER BY details.match_count DESC, lower(details.name), details.oracle_id::text
"""
