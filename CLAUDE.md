# Caramelo — Project Conventions

## What is this

Automations and tools for **Pudim Caramelo**, a small artisanal pudding business.
The owner (Luiza's husband) produces traditional pudding in batches ("fornadas") and
sells in different sizes (500g, 1kg, 200g).

## Language

This project may use **Portuguese or English** at the user's discretion.
Code comments, variable names, and git messages should be in English.
Data labels, product names, and user-facing content are in Portuguese (the business operates in Brazil).

## Current State

**Stage 1 (Data Foundation): DONE** — Google Sheets at `1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE` has all 12 tabs populated, formulas working, formatting applied. Created via GWS CLI on 2026-04-10.

**Stage 5 (Bot — fast-tracked): IN PROGRESS** — Code written in `bot/`, awaiting user setup of Telegram bot, Gemini API key, GCP service account, and Vercel deploy. See `bot/SETUP.md`.

Stages 2-4 were deprioritized; the bot replaces "Stage 2: Easy Purchase Logging" directly.

### Stages roadmap

1. **Data Foundation** ✅ — Google Sheets structure (Produtos, Fornecedores, Compras, etc.)
2. ~~Easy Purchase Logging via Form~~ — superseded by bot
3. **Pricing Calculator** ✅ — done as part of Stage 1
4. **Batch Management & Cash Flow** — basic version done in Stage 1; richer reports TBD
5. **Bot Integration (Telegram)** 🚧 — receipt photo → Gemini Vision → Sheets

## Architecture

```
Input Channels (future) → Google Sheets API → DATA TABS → Formulas → CALCULATION TABS
```

- **Data tabs**: rigid table format, header in row 1, no merged cells, append-only where applicable
- **Calculation tabs**: read-only, formula-driven, never edited directly
- See `plans/data-model-v1.md` for full schema

## Tech Stack

- **Google Sheets** — primary data store and UI (Stage 1-3)
- **Google Apps Script** — automation within Sheets (Stage 2-3)
- **Vercel** — serverless hosting for bot (Stage 5)
- **Telegram Bot API** — user input channel (Stage 5)
- **Claude/OpenAI API** — receipt OCR and natural language parsing (Stage 5)

## Key Constraints

- **Free tier only** — no paid tools until the business justifies it
- **Simple for non-developers** — the end users are not programmers
- **Bot-ready data structure** — all data tabs must be machine-writable (no merged cells, stable IDs, headers in row 1)

## ID Convention

Products use category prefixes with independent numbering:

| Prefix | Category |
|--------|----------|
| `ALI-` | Alimentos (food ingredients) |
| `FOR-` | Formas (molds) |
| `EMB-` | Embalagens (packaging) |
| `EQP-` | Equipamentos (equipment) |
| `FORN-` | Fornecedores (suppliers) |
| `TAM-` | Tamanhos (pudding sizes) |
| `FN-` | Fornadas (batches) |
| `C-` | Compras (purchases) |
| `FC-` | Fluxo de Caixa (cash flow) |

## Session Practices

When ending a session or pausing work:

1. **Update `plans/` with current state** — what was done, what's next, any blockers
2. **Keep README.md current** — reflects actual project state, not aspirational
3. **Keep this CLAUDE.md current** — update "Current State" section as stages progress
4. **Commit clean, working code** — no half-finished changes left uncommitted
5. **Leave breadcrumbs** — if something was tried and didn't work, note it in plans/

## Repository Structure

```
Caramelo/
├── CLAUDE.md                  # This file — project conventions
├── README.md                  # Project overview, setup, usage
├── plans/
│   └── data-model-v1.md       # Data model specification
├── scripts/
│   ├── create_spreadsheet.py  # Generate local xlsx (legacy, GWS CLI now does this)
│   └── deploy_to_sheets.sh    # Deploy to Sheets via GWS CLI (legacy)
├── sheets/
│   └── setup_formulas.gs      # Apps Script (legacy, formulas now via GWS CLI)
├── bot/                       # Telegram bot — Stage 5
│   ├── README.md
│   ├── SETUP.md               # Step-by-step user setup guide
│   ├── api/webhook.py         # Vercel serverless entry
│   ├── lib/                   # Gemini, Sheets, matcher, state, orchestrator
│   └── tests/test_parser.py   # Local parse test
└── output/                    # Generated files (gitignored)
```

## Spreadsheet

- **ID:** `1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE`
- **URL:** https://docs.google.com/spreadsheets/d/1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE/edit
- **Locale:** pt_BR — formulas must use `;` as argument separator, `,` as decimal

## Tools Used

- **GWS CLI (`gws`)** — read/write Google Sheets from terminal (replaces Apps Script for most ops)
- **Python + openpyxl** — generate offline xlsx if needed
- **Vercel** — deployment target for the Telegram bot
