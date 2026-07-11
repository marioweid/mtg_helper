# Role Suggestion Signal Separation Design

## Problem

Ramp, draw, and interaction classification is written to `cards.tags`, but structured candidate
search uses only `hub_tags || mtgjson_tags`. Candidate loading also aliases `hub_tags AS tags`,
so the stage eligibility filter examines deck-theme membership instead of functional card roles.
Full-text matches and broad theme associations can therefore outrank cards that actually perform
the requested function.

## Considered Approaches

1. **Separate eligibility from ranking (selected).** Use local rules-based tags for functional
   stage eligibility and source statistics as ranking priors. This fixes the broken boundary and
   retains the useful Moxfield/Archidekt signal.
2. **Use source tags as hard role truth.** This avoids local classification but incorrectly treats
   every card common in Draw- or Ramp-tagged decks as a draw or ramp card.
3. **Expand manual per-card classification.** This can be precise but does not scale and repeats
   work whenever cards are released.

## Design

- Structured role candidate search uses `cards.tags || mtgjson_tags` for ramp, draw, interaction,
  and lands-related queries.
- Candidate records expose `cards.tags AS tags`, retain `hub_tags` separately, and retain
  `mtgjson_tags` separately.
- Stage eligibility is a hard precision gate based on local functional tags. Moxfield and
  Archidekt group statistics may boost or add candidates only when the card passes that gate.
- Theme-stage selection continues to use shared Moxfield/Archidekt groups and source-qualified
  ungrouped tags. Theme behavior must not regress.
- The first repair does not add new role mappings, classifiers, or admin controls. Source-level
  role mappings are deferred until the corrected baseline is measured.

## Data Flow

1. Rule tagging writes functional roles to `cards.tags`.
2. MTGJSON tagging writes printed mechanics to `cards.mtgjson_tags`.
3. Moxfield and Archidekt pipelines write deck-theme evidence independently.
4. Functional stage retrieval generates candidates from local/MTGJSON role evidence.
5. Source evidence and commander top-deck evidence rerank only stage-eligible candidates.
6. Theme retrieval continues to resolve shared groups through `theme_service`.

## Regression Tests

- Tag search SQL includes local `cards.tags` and does not use `hub_tags` as functional truth.
- Fetched candidate `tags` contains local functional tags.
- A theme-associated card without the requested role is excluded from a functional stage.
- A role-qualified card with source evidence receives the source boost.
- Theme-stage group scoring remains unchanged.

## Success Criteria

- Ramp, draw, and interaction results must pass the existing functional role classifier.
- Moxfield/Archidekt evidence improves ordering without bypassing role eligibility.
- No manual per-card reclassification is required.
- Theme suggestions continue to use the multi-source pipeline.
