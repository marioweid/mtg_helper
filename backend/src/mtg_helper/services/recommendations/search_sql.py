"""Parameterized grouped matching; only the page is expanded into source explanations."""

# ruff: noqa: E501 -- preserve readable, parameterized relational expressions.
MATCH_SQL = """
WITH searches AS MATERIALIZED (
    SELECT ordinal AS query_id, value AS query FROM jsonb_array_elements($1::jsonb)
        WITH ORDINALITY source(value, ordinal)
), groups AS MATERIALIZED (
    SELECT q.query_id, g.ordinal AS group_id, g.value AS criteria FROM searches q
    CROSS JOIN LATERAL jsonb_array_elements(q.query->'groups')
        WITH ORDINALITY g(value, ordinal)
), tag_hits AS MATERIALIZED (
    SELECT DISTINCT g.query_id,g.group_id,m.oracle_id,selected.id::uuid AS criterion_id,
        m.tag_id AS matched_tag_id
    FROM groups g CROSS JOIN LATERAL
        jsonb_array_elements_text(g.criteria->'oracle_tag_ids') selected(id)
    JOIN scryfall_tag_descendants d ON d.ancestor_id=selected.id::uuid
    JOIN scryfall_tag_memberships m ON m.tag_id=d.descendant_id
    WHERE $11::uuid IS NULL OR m.oracle_id=$11
), keyword_hits AS MATERIALIZED (
    SELECT DISTINCT g.query_id,g.group_id,n.oracle_id,selected.keyword
    FROM groups g CROSS JOIN LATERAL
        jsonb_array_elements_text(g.criteria->'printed_keywords') selected(keyword)
    CROSS JOIN new_card_catalog n
    JOIN new_card_catalog_state s ON s.generation=n.generation
    WHERE COALESCE(n.source_facts->'keywords','[]'::jsonb) ? selected.keyword
        AND ($11::uuid IS NULL OR n.oracle_id=$11)
), group_hits AS (
    SELECT query_id,group_id,oracle_id FROM tag_hits
    UNION SELECT query_id,group_id,oracle_id FROM keyword_hits
), query_hits AS (
    SELECT query_id,oracle_id FROM group_hits GROUP BY query_id,oracle_id
    HAVING count(*)=(SELECT count(*) FROM groups g WHERE g.query_id=group_hits.query_id)
), matched_queries AS MATERIALIZED (
    SELECT h.query_id,h.oracle_id,q.query->>'purpose' AS purpose FROM query_hits h
    JOIN searches q ON q.query_id=h.query_id JOIN new_card_catalog n ON n.oracle_id=h.oracle_id
    WHERE jsonb_array_length(q.query->'card_types_any')=0 OR EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(q.query->'card_types_any') kind(value)
        WHERE COALESCE(n.source_facts->'card_faces'->0->>'type_line',
            n.source_facts->>'type_line','') LIKE '%' || kind.value || '%')
), eligible AS MATERIALIZED (
    SELECT c.id,c.oracle_id,c.name,
        (c.edhrec_rank IS NULL OR c.edhrec_rank<=0) AS rank_missing,
        CASE WHEN c.edhrec_rank>0 THEN c.edhrec_rank ELSE 0 END AS sort_rank,
        CASE WHEN c.edhrec_rank>0 THEN c.edhrec_rank ELSE NULL END AS global_popularity_rank
    FROM cards c JOIN new_card_catalog n ON n.oracle_id=c.oracle_id
    JOIN new_card_catalog_state s ON s.generation=n.generation
    WHERE c.is_canonical AND EXISTS (SELECT 1 FROM matched_queries m WHERE m.oracle_id=c.oracle_id)
      AND n.source_facts->'legalities'->>'commander'='legal'
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
      AND c.color_identity <@ $2::text[] AND n.oracle_id <> ALL($3::uuid[])
      AND NOT EXISTS (SELECT 1 FROM deck_cards dc JOIN cards owned ON owned.id=dc.card_id
          WHERE dc.deck_id=$4 AND owned.oracle_id=n.oracle_id)
      AND NOT EXISTS (SELECT 1 FROM deck_card_plans p JOIN cards planned ON planned.id=p.card_id
          WHERE p.deck_id=$4 AND p.direction='addition' AND planned.oracle_id=n.oracle_id)
      AND NOT EXISTS (SELECT 1 FROM discover_dismissals d
          WHERE d.deck_id=$4 AND d.account_id=$5 AND d.oracle_id=n.oracle_id)
), page AS MATERIALIZED (
    SELECT eligible.*,lower(name) AS sort_name FROM eligible
    WHERE $6::boolean IS NULL OR (rank_missing,sort_rank,lower(name),oracle_id::text)>($6,$7,$8,$9)
    ORDER BY rank_missing,sort_rank,lower(name),oracle_id::text LIMIT $10
), details AS (
    SELECT page.*,c.image_uri,n.source_facts,evidence.items AS evidence,
        evidence.match_count FROM page JOIN cards c ON c.id=page.id
    JOIN new_card_catalog n ON n.oracle_id=page.oracle_id
    CROSS JOIN LATERAL (
        SELECT jsonb_agg(DISTINCT item ORDER BY item) AS items,
            count(DISTINCT criterion)::integer AS match_count FROM (
            SELECT 'tag:' || h.criterion_id::text AS criterion,
                jsonb_build_object('query_purpose',q.purpose,'criterion_id',h.criterion_id::text,
                'criterion_label',COALESCE(t.metadata->>'label',t.slug),
                'matched_tag_id',h.matched_tag_id::text,
                'matched_tag_label',COALESCE(m.metadata->>'label',m.slug),
                'relation',CASE WHEN h.criterion_id=h.matched_tag_id
                    THEN 'direct' ELSE 'descendant' END) AS item
            FROM tag_hits h JOIN matched_queries q ON q.oracle_id=h.oracle_id AND q.query_id=h.query_id
            JOIN scryfall_tags t ON t.id=h.criterion_id JOIN scryfall_tags m ON m.id=h.matched_tag_id
            WHERE h.oracle_id=page.oracle_id
            UNION ALL
            SELECT 'keyword:' || h.keyword, jsonb_build_object('query_purpose',q.purpose,
                'criterion_id',NULL,'criterion_label',h.keyword,'matched_tag_id',NULL,
                'matched_tag_label',NULL,'relation','keyword')
            FROM keyword_hits h JOIN matched_queries q
                ON q.oracle_id=h.oracle_id AND q.query_id=h.query_id WHERE h.oracle_id=page.oracle_id
        ) matched
    ) evidence
)
SELECT totals.total,details.* FROM (SELECT count(*)::integer AS total FROM eligible) totals
LEFT JOIN details ON true
ORDER BY details.rank_missing,details.sort_rank,lower(details.name),details.oracle_id::text
"""
