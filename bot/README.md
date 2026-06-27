# Pudim Caramelo Bot

Telegram bot with two jobs:

1. **Compras (insumos)** — reads receipt photos/PDFs/XML and adds purchases to
   the Google Sheets `Compras` tab.
2. **Modo Feira (vendas)** — tracks pudding sales during a street fair, by text,
   audio, or image, and produces a closing balance.

## How it works

```
Compras:  Telegram (photo/PDF/XML/text) → Gemini parse → match products →
          confirm via inline buttons → write to Compras
Feira:    /feira (or "saindo pra feira, 30 a R$18") opens an event. While open,
          every text/audio/image is read as a SALE (qty + name + payment) and
          logged on the spot, with an undo button. /fechar reconciles the
          balance (sold/returned, cash×pix, who's on credit).
```

### Modo Feira

- **Open:** `/feira` or natural text mentioning "feira" (e.g. *"tamo saindo pra
  feira, levando 30 pudins a R$18"*). Stores qty taken + unit price.
- **Sell:** *"vendi 2 pro fulano"*, *"vendi 2 agora"* (anon), *"vendi 2, a maria
  vai voltar pra pagar"* (fiado), *"vendi 3 pro joão no pix"*. Via text, 🎤 audio
  (auto-transcribed), or 📷 image. Logged immediately + `↩️ Desfazer` button.
- **Close:** `/fechar`, or tell it the totals (*"voltaram 5, recebi 200 no
  dinheiro e 150 no pix"*). Shows the balance and reconciles stock + cash.
- **Persistence:** new tabs `Feiras` (event header) and `VendasFeira` (one row
  per sale), auto-created on first use. Customer names live in the sheet only —
  never committed to the repo.
- Commands: `/feira`, `/feira_status`, `/fechar`, `/cancel`.

## Setup steps

See `SETUP.md` for step-by-step instructions on:
1. Creating a Telegram bot
2. Getting a Gemini API key
3. Creating a Google service account
4. Sharing the spreadsheet
5. Deploying to Vercel

## Local development

```bash
cd bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in .env with your secrets

# Run the parser test (no Telegram needed)
python tests/test_parser.py
```

## Project structure

```
bot/
├── api/
│   └── webhook.py          # Vercel serverless entrypoint
├── lib/
│   ├── gemini.py           # Receipt + audio + feira parsers
│   ├── sheets.py           # Sheets read/write (Compras)
│   ├── matcher.py          # Product matching
│   ├── state.py            # Pending-confirmation state (compras)
│   ├── orchestrator.py     # Compras glue logic
│   ├── feira.py            # Modo Feira data layer + balance
│   ├── feira_flow.py       # Modo Feira Telegram orchestration
│   └── telegram_client.py  # Telegram API client
├── tests/
│   ├── test_parser.py      # Local test with sample receipts
│   └── test_feira.py       # Balance computation (pure, no network)
├── requirements.txt
├── vercel.json
└── .env.example
```

## Cost

- Telegram: free
- Vercel: free (Hobby tier)
- Google Sheets API: free
- Gemini Flash: free tier (1500 req/day) — more than enough

Expected monthly cost: **R$ 0**.
