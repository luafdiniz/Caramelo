# Caramelo

Automations and tools for **Pudim Caramelo** — a small artisanal pudding business based in Belo Horizonte, Brazil.

## About the business

- Single product: traditional pudding (pudim tradicional)
- Three sizes: 500g (fornada only), 1kg and 200g (pronta entrega)
- Sales model: batch announcements ("fornadas") + ready delivery stock

## Live services

| Service | URL | What |
|---|---|---|
| 🤖 Telegram bot | [@pudim_caramelo_bot](https://t.me/pudim_caramelo_bot) | Send photo of receipt → auto-extract → add to Compras |
| 📊 Streamlit dashboard | [caramelo-do-fila.streamlit.app](https://caramelo-do-fila.streamlit.app) | Manage Tamanhos, Insumos, Calculadora, Produção, Compras (password protected) |
| 📑 Source of truth | [Google Sheet](https://docs.google.com/spreadsheets/d/1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE) | All data — both services read/write here |

## Status

✅ **Done**
1. Data foundation — normalized Google Sheets (Produtos, Fornecedores, Compras, Tamanhos, Receita, Embalagens, Fornadas, Fluxo de Caixa, etc.)
2. Pricing calculator — Ficha Técnica auto-updates from latest Compras
3. Telegram bot — Gemini Vision receipt parsing, alias memory, interactive resolution
4. Streamlit dashboard — full CRUD, brand styling, sort/filter, analytics

⏳ **Possible next**
- `/novo` command in bot to add insumo without a receipt
- Active stock tracking (currently only purchases, no consumption deduction)
- Aliases management UI in app
- Production planning advanced features

## Repository structure

```
Caramelo/
├── CLAUDE.md                 # Project conventions for Claude Code
├── README.md                 # This file
├── plans/                    # Design docs and session notes
│   ├── data-model-v1.md
│   └── session-2026-05-12.md # Latest session handoff
├── scripts/                  # Sheet generation/migration scripts
├── sheets/                   # Apps Script (legacy)
├── bot/                      # Telegram bot (Vercel)
│   ├── api/webhook.py
│   ├── lib/                  # Gemini, Sheets, matcher, aliases, etc.
│   ├── tests/
│   └── SETUP.md
├── app/                      # Streamlit dashboard
│   ├── Home.py
│   ├── pages/
│   ├── lib/
│   └── SETUP.md
└── output/                   # Generated files (gitignored)
```

## Quick start (local dev)

```bash
# Bot tests
cd bot && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=... SPREADSHEET_ID=... GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
python tests/test_parser.py

# Streamlit app
cd app && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SPREADSHEET_ID=... GOOGLE_SERVICE_ACCOUNT_JSON=$(cat ~/Documents/Credenciais/caramelo-bot-key.json) APP_PASSWORD=...
streamlit run Home.py
```

Setup full deploy: see [`bot/SETUP.md`](bot/SETUP.md) and [`app/SETUP.md`](app/SETUP.md).
