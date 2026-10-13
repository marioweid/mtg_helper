# Local Scryfall publication staging

This is an isolated, local-only deployment of the **publication foundation**, not the completed
Scryfall-only label migration. Existing label consumers and legacy maintenance jobs still remain.
Do not deploy this over the application database or interpret its recommendations as migration proof.

## Verified deployment

On October 13, 2026, both production container builds and staging startup succeeded. The staging-only
Admin Sync Scryfall request returned `202`, completed with status `ok` in 29.32 seconds, and reported
matching card/tag generations: **32,165 cards, 4,577 tags and 236,717 direct memberships**. SQL counts
matched the publication status. Upstream memberships had changed since the earlier disposable test.

Frontend sign-in returned `200`; unauthenticated Admin access redirected to sign-in; unauthenticated
backend Admin access returned `401`. Google provider URLs use `localhost:3000`. Completing Google
sign-in and checking the authenticated browser UI still requires the user's interactive login.
Twelve focused frontend tests, project lint/typecheck, explicit config lint, and formatting passed.
Both final container builds completed without warnings; the narrowly documented JOSE Edge warning
ignore does not change authentication runtime or suppress unrelated warnings.

The original `mtg_helper-postgres-1` remains stopped, on its existing `mtg_helper_pgdata` volume.
Staging uses `mtg-helper-label-staging_staging-pgdata`; it has no application-data mounts or host
PostgreSQL port. No existing application database was started, migrated, synced or copied here.

## Open it

Visit **http://localhost:3000/admin**, sign in with the usual allowlisted Google account, and check
**Matching card/tag generation**. A fresh staging account has no existing decks or inventory.
Use **Sync Scryfall** for this check, not Refresh All or the legacy label-sync/tag actions.

Ports are loopback-only: frontend `3000`, backend `8001`. A dummy OpenAI key prevents billable AI
calls; tracing is disabled. AI-dependent tools are intentionally unavailable. Do not replace the
key with a real provider key for this publication check. Only the existing Google OAuth credentials
and admin allowlist are reused; database, internal API and session secrets are staging-specific.

## Recreate or restart

The root ignored `.env` must contain `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` and `ADMIN_EMAILS`, with
Google's allowed redirect URI `http://localhost:3000/api/auth/callback/google`. Keep port `3000` free;
do not stop another deployment or change its OAuth configuration blindly.

Runtime secrets are already generated locally in ignored `backend/.cache/staging/runtime.env`.
For a new checkout, generate them **once**, before creating the staging database volume:

```bash
python - <<'PY'
from pathlib import Path
import secrets

path = Path("backend/.cache/staging/runtime.env")
if path.exists():
    raise SystemExit("Reuse existing staging secrets; do not rotate over an existing volume.")
path.parent.mkdir(parents=True, exist_ok=True)
password = secrets.token_hex(32)
values = {
    "STAGING_DATABASE_PASSWORD": password,
    "STAGING_DATABASE_URL": (
        f"postgresql://staging:{password}@postgres:5432/mtg_helper_label_staging"
    ),
    "STAGING_INTERNAL_API_TOKEN": secrets.token_hex(32),
    "STAGING_AUTH_SECRET": secrets.token_urlsafe(48),
}
path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
print("Created ignored staging secrets; no credentials printed.")
PY
```

Run from the repository root. Do not print the runtime file or expanded Compose configuration;
both contain secrets.

```bash
docker compose -f docker-compose.staging.yml \
  --env-file .env --env-file backend/.cache/staging/runtime.env config --quiet

docker compose -f docker-compose.staging.yml \
  --env-file .env --env-file backend/.cache/staging/runtime.env up -d --build

docker compose -f docker-compose.staging.yml \
  --env-file .env --env-file backend/.cache/staging/runtime.env ps
```

Backend builds use the checked-in Python lockfile; frontend installs include the existing approved
native-build allowlist. Neither build context includes runtime environment files.

To stop **only staging**, retaining its database:

```bash
docker compose -f docker-compose.staging.yml \
  --env-file .env --env-file backend/.cache/staging/runtime.env down
```

Do not add `--volumes` unless intentionally discarding staging data. Stop/start the container runtime
as usual; no production or default Compose stack is needed for this staging project.
