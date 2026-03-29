# Architecture

## System Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────┐
│                  │     │                      │     │              │
│   Next.js App    │────▶│   FastAPI Backend     │────▶│  PostgreSQL  │
│   (Frontend)     │◀────│   (API + AI Layer)    │◀────│  (Cards, DB) │
│                  │     │                      │     │              │
└─────────────────┘     └──────────┬───────────┘     └──────────────┘
                                   │
                        ┌──────────┴───────────┐
                        │                      │
                   ┌────▼─────┐         ┌──────▼──────┐
                   │ Claude   │         │  Scryfall   │
                   │ API      │         │  Bulk Data  │
                   └──────────┘         └─────────────┘
```

## Design Principles

### API-First

The FastAPI backend exposes a clean REST API. The Next.js frontend is one consumer; a CLI or mobile app could replace it without touching the backend.

### AI as a Service Layer

The AI (Claude) is behind a service abstraction. Prompt construction, conversation history, and preference injection happen in the backend — the frontend just sends user intent and receives structured responses.

### Local Card Database

Scryfall bulk data is imported into PostgreSQL. Card validation, color identity checks, legality filtering, and text search all happen locally. Scryfall's API is only used for bulk data refreshes — card images are served via Scryfall CDN URLs stored in the DB.

## Components

### Frontend (Next.js)

- Deck builder UI with card images (Scryfall CDN)
- Chat-like interface for AI interaction
- Deck list view with categories (lands, creatures, spells, etc.)
- Thumbs up/down on card suggestions
- Preference management (pet cards, avoid list)

### Backend (FastAPI)

- **API Layer** — REST endpoints for decks, suggestions, preferences, card search
- **AI Service** — Claude API integration, prompt construction, conversation history management
- **Card Service** — Local card search, color identity filtering, legality checks
- **Deck Service** — CRUD operations, deck stage management, Moxfield export
- **Preference Service** — Account-level and deck-level preferences
- **Data Pipeline** — Scryfall bulk data import and periodic refresh

### Database (PostgreSQL)

- Cards table (from Scryfall bulk data)
- Decks and deck cards
- Conversation history per deck
- Preferences (account-level + deck-level)
- Card feedback (thumbs up/down)

## Infrastructure

### Local Development

```
docker-compose.yml
├── frontend    (Next.js, port 3000)
├── backend     (FastAPI, port 8000)
└── postgres    (PostgreSQL, port 5432)
```

### Future: GCP Deployment

Cloud SQL for PostgreSQL, Cloud Run for backend and frontend. Migration path is straightforward from Docker Compose since each service is already containerized.
