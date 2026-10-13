# Scryfall publication production release

## Now

**Production publication deployed and verified on October 13, 2026**, via the documented
SSH/Compose fallback for the existing homeserver/Portainer stack. [Release PR #18](https://github.com/marioweid/mtg_helper/pull/18)
is based on `origin/main` and excludes the separate admission/review experiments. Owner checks and
actual-data rehearsal passed; independent publication review found no blockers and ran 33 offline
tag tests plus scoped lint/format checks. Owner checks include 207 Linux backend tests, 138 additional scoped
offline checks, 12 frontend tests, lint/types/format, warning-free homeserver image builds, and a
clean offline zizmor workflow audit. Database/build/live-sync evidence was not independently rerun.
The focused rollout review found an admission/drain race. The owner repaired it by closing admission
before waiting, then rechecking leases after backend stop and before candidate startup. Runnable
failure-path checks verify drain timeout and post-stop active leases prevent backup/migration.

This ships the canonical publication foundation only. Old label consumers, maintenance streams,
legacy columns and prompts remain. No sole-source cutover or recommendation-accuracy claim is made.

## Actual-data rehearsal

A restricted custom-format PostgreSQL backup was created on the homeserver, copied into ignored local
operational storage, hash-verified, and successfully restored into isolated PostgreSQL databases.
The application database and its bind-mounted storage were not used as rehearsal destinations.

The release backend was built using the checked-in lockfile and executed against the restored copy:

- Schema applied twice: all 25 personal-data tables and all authoritative card facts preserved.
- Complete application startup: exact personal-row fingerprints preserved.
- Explicit Oracle identity repair: zero commander, deck-card or plan groups changed.
- Live Scryfall publication plus its identity repair: exact personal-row fingerprints preserved.
- Existing historical source snapshot bytes, kinds and publication timestamps preserved.
- Matching card/tag generation: 4,577 tags and 236,717 direct memberships.
- Existing application card rows remain 32,523. Source export processing counts are not the total
  stored-card count; retained older printings are not deleted by this publication slice.

The inherited schema backfill changes `cards.mtgjson_tags` for 1,514 existing global-label rows.
Every card column was independently compared with a second untouched restoration: this was the only
column changed by schema application. This is existing startup behavior, **not** personal-data loss,
Scryfall classification, or completion of legacy-label retirement. Do not claim all global rows are
byte-unchanged or hide this exception by dropping personal fields from the preservation checks.

Raw backups, runtime environments, row fingerprints and operational scripts remain private, ignored
and excluded from Docker build contexts. Public documentation contains no personal row content.
No paid model requests are part of rehearsal or deployment verification.

## Production verification

- Admission closed first; admin work/model leases drained before backend stop and final backup.
- Final restricted backup: homeserver `backups/scryfall-publication/`
  `before-production-20261013T184810Z.dump`; runtime data and fingerprints remain private.
- Actual startup and live sync preserved all 25 personal tables, including 14 decks and 948 card rows,
  plus all six pre-existing historical source snapshots. PostgreSQL's image and data mount unchanged.
- Authenticated maintenance sync succeeded: matching generation, 4,577 tags and 236,717 memberships;
  persisted row counts match. Publication timestamp `2026-10-13T18:49:33.012439+00:00`.
- Backend unauthenticated Admin request returned `401`. Frontend sign-in returned `200` locally;
  Google provider URLs retain `https://mtg.marioweid.com` and the original credentials/session secret.
- Frontend reopened only after preservation checks; the original sync worker resumed afterwards.
  Qdrant, PostgreSQL, Portainer and unrelated applications were not recreated.
- An unauthenticated public `/signin` probe returned `403`; automated checks do not bypass that ingress
  access layer. Interactive public access/Google sign-in remains the user's browser confirmation.
- Old backend/frontend images retain `before-scryfall-publication` rollback tags. No paid model endpoint
  was invoked, no database volume removed, and no personal categories or saved intent remapped.

The reviewed PR is merged only after this verification so subsequent Portainer Git polling receives
this same release without reopening writers during the write freeze. Check status after GitOps restarts.

## Deployment sequence and rollback boundary

1. Finish scoped checks and independent review. Build/test the exact release; open a branch/PR,
   never push directly to `main`. Existing research work remains preserved in its own worktree.
2. Preserve the currently running backend/frontend image IDs under explicit rollback tags. Build
   replacement images before the maintenance interval; do not recreate PostgreSQL, Qdrant, Portainer
   or other homeserver applications. Retain the existing runtime environment, data directory,
   frontend port/binding, public OAuth URL, credentials, admin allowlist and tracing configuration.
3. Close admission by stopping only the MTG Helper sync worker and frontend. Keep the backend alive
   while waiting for admin jobs and model leases to drain; fail closed if this cannot be established.
   Then stop the backend and recheck no active leases before backup or candidate startup.
   Take another restricted production backup and capture fresh personal-table
   fingerprints and historical-source fingerprints. Rehearsal counts are not the final baseline if
   users have changed data since the first backup.
4. Deploy the reviewed commit with passing PR checks via the documented SSH/Compose fallback.
   Keep `main` unchanged during the write freeze so Portainer Git polling cannot start the frontend
   early; no repository push webhooks are configured. Backend/frontend use the same release, but
   start the backend first while the frontend and sync worker remain stopped. Use an explicit image
   override for the prebuilt candidate images, and `--no-deps --no-build`, preserving runtime values.
   Production starts from frozen installed dependencies (`--no-sync`).
5. Verify backend health and enabled authentication. Confirm saved-state fingerprints after startup;
   stop if any personal state differs. Trigger only Admin Sync Scryfall, not paid AI endpoints.
6. Confirm successful sync, matching card/tag generations, actual persisted tag/membership counts,
   preserved personal data and historical source snapshots. Only then start the matching frontend,
   check sign-in routing, and resume the existing sync worker. Do not add a maintenance stream.
7. Merge the already reviewed PR after production verification, then verify any Portainer GitOps
   redeployment uses the same release. Record release/PR, verification and restricted backup locations. Interactive Google sign-in and
   browser inspection can be confirmed by the user; automation must not impersonate their account.

For failed startup or verification, stop the affected MTG Helper writers and retain all evidence.
Old images can run with the additive publication schema. Do not blindly restore a whole database
once new user writes are allowed: a restore would discard those writes. Restore the final backup
only within the frozen interval, with an explicit rollback reason and verified target identity.
Never remove database volumes or prune the rollback images/backups as deployment cleanup.
