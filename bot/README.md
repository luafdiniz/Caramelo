# Pudim Caramelo Bot

Telegram bot that reads receipt photos and adds purchases to the Google Sheets
spreadsheet (Compras tab).

## How it works

```
Telegram (photo) → Vercel webhook → Gemini Vision (parse) →
Match products → Confirm via inline buttons → Write to Sheets
```

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
│   ├── gemini.py           # Receipt parser
│   ├── sheets.py           # Sheets read/write
│   ├── matcher.py          # Product matching
│   ├── state.py            # Pending-confirmation state
│   ├── orchestrator.py     # Glue logic
│   └── telegram_client.py  # Telegram API client
├── tests/
│   └── test_parser.py      # Local test with sample receipts
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
