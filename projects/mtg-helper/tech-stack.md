# Tech Stack

## Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI | Async REST API |
| Python | 3.13 | Runtime |
| DB Driver | asyncpg | Async PostgreSQL access, plain SQL |
| AI | Claude API (Anthropic SDK) | Deck building, card suggestions |
| HTTP Client | httpx | Scryfall bulk data downloads |
| Validation | Pydantic V2 | Request/response models |
| Package Manager | uv | Dependencies, virtualenv |
| Linting | ruff | Lint + format |
| Type Checking | ty | Static analysis |
| Testing | pytest | Unit + integration tests |

## Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Next.js 14+ (App Router) | UI |
| Language | TypeScript | Type safety |
| Styling | TBD (Tailwind CSS recommended) | Styling |
| State | TBD | Client state management |
| Linting | oxlint | Lint |
| Formatting | oxfmt | Format |

## Database

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Primary DB | PostgreSQL 16 | Cards, decks, preferences, conversations |
| Query Style | Plain SQL via asyncpg | No ORM |
| Future | Qdrant | Vector search for card similarity (if needed) |

## Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Local | Docker Compose | Run all services locally |
| Future Deploy | GCP (Cloud Run + Cloud SQL) | Production hosting |

## External APIs

| Service | Usage | Rate Limiting |
|---------|-------|---------------|
| Scryfall Bulk Data | Card database import | None (bulk download) |
| Scryfall CDN | Card images (URLs stored in DB) | None (public CDN) |
| Claude API | AI deck building + suggestions | Per API plan |
