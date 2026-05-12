# Bot Setup Guide

Step-by-step. Total time: ~30 minutes.

---

## 1. Create the Telegram bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "Pudim Caramelo Bot")
4. Choose a username (must end in `bot`, e.g., `pudim_caramelo_bot`)
5. **Save the token** BotFather gives you — looks like `1234567890:ABC...`
6. Open your bot and send `/start` — you'll see the welcome message after deploy

### Get your chat ID
Once the bot is deployed, send `/whoami` to it. The bot replies with your `chat_id`.
Add that ID to `TELEGRAM_ALLOWED_CHAT_IDS` env var (otherwise anyone who finds your
bot can write to your sheet).

---

## 2. Get a Gemini API key

1. Open `https://aistudio.google.com/apikey`
2. Sign in with your personal Google account (NOT work)
3. Click **Create API key**
4. Pick the `caramelo-v2` GCP project (or any project)
5. **Save the key** — looks like `AIzaSy...`

Free tier: 1,500 requests/day on Gemini 2.0 Flash. Plenty for this use case.

---

## 3. Create a Google service account

The bot needs to write to your spreadsheet. A service account is like a robot user.

1. Open `https://console.cloud.google.com/iam-admin/serviceaccounts?project=caramelo-v2`
2. Click **Create Service Account**
3. Name it `caramelo-bot`
4. Skip the optional steps, click **Done**
5. Click on the new service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
6. A JSON file downloads. **Save it** (we'll paste its content into Vercel).

### Share the spreadsheet with the service account

1. Open the JSON file — find the `client_email` field (looks like `caramelo-bot@caramelo-v2.iam.gserviceaccount.com`)
2. Open your spreadsheet in Google Sheets
3. Click **Share** → paste the service account email → give **Editor** access → uncheck "Notify people" → Share

The spreadsheet ID is in the URL:
`https://docs.google.com/spreadsheets/d/`**THIS_PART_IS_THE_ID**`/edit`

For Pudim Caramelo v2: `1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE`

---

## 4. Test locally (optional but recommended)

```bash
cd bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set secrets
export GEMINI_API_KEY="AIzaSy..."
export SPREADSHEET_ID="1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE"
export GOOGLE_SERVICE_ACCOUNT_JSON="/path/to/downloaded-key.json"

# Test with the 3 sample receipts
python tests/test_parser.py
```

You should see each receipt parsed, matched against products, and the resulting
preview that the bot would show in Telegram.

---

## 5. Deploy to Vercel

### a) Sign up at Vercel
1. Open `https://vercel.com`
2. Sign in with GitHub (free Hobby plan)
3. Connect your `luafdiniz/Caramelo` repo

### b) Configure the project
1. **Root directory**: `bot/`
2. **Framework preset**: Other
3. **Build command**: leave empty
4. **Output directory**: leave empty
5. **Install command**: leave default

### c) Add environment variables
In the project settings, add these:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Your chat ID (after first /whoami) |
| `GEMINI_API_KEY` | Key from AI Studio |
| `SPREADSHEET_ID` | `1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Paste the **entire content** of the JSON file |

### d) Deploy
Click **Deploy**. Wait ~1 minute. You get a URL like `https://caramelo-bot.vercel.app`.

### e) Tell Telegram where to send updates

Replace `TOKEN` and `URL` and run this in your terminal:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://<YOUR_URL>.vercel.app/api/webhook"
```

You should see `{"ok":true,"result":true,"description":"Webhook was set"}`.

---

## 6. Test the bot

1. Open your bot in Telegram
2. Send `/start` — should reply with welcome
3. Send `/whoami` — note your chat_id
4. (If you didn't set `TELEGRAM_ALLOWED_CHAT_IDS` before deploy, add it now and redeploy)
5. Send a photo of a receipt
6. Bot replies with extraction → click Confirm → check the Compras tab in your sheet

---

## Troubleshooting

### Bot doesn't reply
- Check Vercel logs (Project → Logs)
- Verify webhook is set: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`

### "Failed to write to spreadsheet"
- Did you share the spreadsheet with the service account email? (Step 3)
- Is `SPREADSHEET_ID` correct?

### Gemini errors
- Free tier limits: 1,500 req/day. If exceeded, wait 24h or upgrade.

### Bot replies "Não autorizado"
- Add your `chat_id` to `TELEGRAM_ALLOWED_CHAT_IDS` in Vercel env vars
