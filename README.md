# Caramelo

Automations and tools for **Pudim Caramelo** — a small artisanal pudding business based in Belo Horizonte, Brazil.

## About the business

- Single product: traditional pudding (pudim tradicional)
- Three sizes: 500g (fornada only), 1kg and 200g (pronta entrega)
- Sales model: batch announcements ("fornadas") + ready delivery stock

## Current state

**Stage 1 — Data Foundation: done.** Google Sheets at:
https://docs.google.com/spreadsheets/d/1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE/edit

12 tabs covering products, suppliers, purchases, recipes, batches, cash flow,
plus calculation tabs (Ficha Técnica, Calculadora, Produção, Comparativo de Fornecedores).

**Stage 5 — Telegram Bot: deployed.**
Send a photo of a receipt → bot extracts items via Gemini Vision → adds to the
spreadsheet. See [`bot/SETUP.md`](bot/SETUP.md).

**Stage 6 — Web Dashboard (Streamlit): code ready.**
Streamlit app for managing the business without editing the spreadsheet
directly. Pages: Tamanhos (with live cost calculations), Produtos (price
history + supplier analysis), Calculadora, Produção (fornadas), Compras
(monthly history). See [`app/SETUP.md`](app/SETUP.md).

## Roadmap

1. ✅ Data Foundation — normalized Google Sheets
2. — superseded by Stage 5 + Stage 6
3. ✅ Pricing Calculator (sheet + app)
4. ✅ Batch Management & Cash Flow (basic — app has registro de fornadas)
5. ✅ Bot Integration (Telegram + Vercel + Gemini, with alias memory)
6. ✅ Web Dashboard (Streamlit) — pending user deploy

## Repository structure

See [`CLAUDE.md`](CLAUDE.md) for full conventions and structure.

```
Caramelo/
├── plans/                # Design docs
├── scripts/              # Spreadsheet generation scripts
├── sheets/               # Apps Script (legacy)
├── bot/                  # Telegram bot (Vercel deployment)
└── output/               # Generated files (gitignored)
```
