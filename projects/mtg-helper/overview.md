# MTG Helper — Project Overview

## What It Is

An AI-powered Commander deck-building assistant. You set a commander, describe your strategy in natural language, and the AI builds a deck in stages — giving you control at every step.

## Problem It Solves

Building Commander decks is fun but time-consuming. You need to balance mana curves, find synergies across 27,000+ legal cards, and match a target power level. MTG Helper automates the research and card selection while keeping the human in the loop for creative decisions.

## Target User

Commander players who want help building decks that match a specific strategy, tone, and power level — without losing creative control.

## Core Value Proposition

- **Natural language deck building** — Describe what you want ("Hazel of the Rootbloom with token copies and big X spells as finishers") and get a structured deck
- **Interactive refinement** — Start with a partial list, ask for targeted suggestions, and iterate
- **Preference learning** — The AI remembers what you like and dislike, both per-deck and globally
- **Power level awareness** — Build for bracket 2 (casual) or bracket 3 (strong) intentionally
- **Full card accuracy** — Local Scryfall database ensures every suggestion is a real, legal card

## Non-Goals (For Now)

- Multi-user / authentication
- Cloud deployment (Docker Compose local first)
- Deck playtesting or goldfish simulation
- Price optimization
- Collection tracking (delegate to Moxfield)
