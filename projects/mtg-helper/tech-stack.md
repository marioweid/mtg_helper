# Tech stack

Installed versions are pinned in [backend/pyproject.toml](../../backend/pyproject.toml),
[frontend/package.json](../../frontend/package.json), and their lockfiles.

| Area | Current technology |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic V2, pydantic-settings |
| Database | PostgreSQL 16, asyncpg, parameterized plain SQL (no ORM) |
| AI | OpenAI Responses through Pydantic AI; bounded workflows and structured output |
| HTTP | HTTPX, curl_cffi for supporting source integrations |
| Tracing | Optional Assay SDK / OpenTelemetry integration |
| Frontend | Next.js 15 App Router, React 19, TypeScript |
| Authentication | Auth.js / next-auth with Google; backend Google ID-token verification |
| UI | Tailwind CSS 4, React state/hooks, dnd-kit |
| Python tooling | uv, Ruff, ty, pytest / pytest-asyncio |
| Frontend tooling | pnpm, oxlint, oxfmt, Vitest, TypeScript |
| Development | Docker Compose with hot reload; isolated default or explicit live-data override |
| Production | Portainer Compose, external shared PostgreSQL, existing proxy/Cloudflare ingress |

Scryfall provides card facts/images and canonical tag publication. Legacy consumers still
use MTGJSON, Moxfield, and Archidekt metadata/evidence; Commander Spellbook supplies combo
data. The [Scryfall-only label migration](../../docs/scryfall-only-label-migration-plan.md)
is not complete. There is no vector database service or Anthropic/Gemini runtime integration.

Use [VERIFY.md](../../VERIFY.md) for development commands and database safety, and
[OPERATIONS.md](../../OPERATIONS.md) for deployment and sync operations.
