# Deploy do app no Streamlit Community Cloud

Streamlit Community Cloud roda apps Streamlit **grátis**. Você só precisa de
uma conta (link com GitHub).

## Pré-requisitos

- Repo no GitHub (já temos: `luafdiniz/Caramelo`)
- Service account JSON (já temos do bot)
- Senha do app (você escolhe)

---

## Passo a passo

### 1. Criar conta no Streamlit Cloud

1. Abre `https://share.streamlit.io`
2. Clica em **Sign up** → **Continue with GitHub**
3. Autoriza acesso à sua conta pessoal (`luafdiniz`)

### 2. Criar o app

1. No dashboard do Streamlit Cloud, clica em **Create app** → **Deploy a public app from GitHub**
2. Preenche:
   - **Repository:** `luafdiniz/Caramelo`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`
   - **App URL** (sub-domínio): escolhe um nome tipo `pudim-caramelo` → `pudim-caramelo.streamlit.app`

3. Clica em **Advanced settings**:
   - **Python version:** `3.11` (recomendado)
   - **Secrets:** clica em **Edit secrets** e cola (formato TOML):

```toml
SPREADSHEET_ID = "1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE"
APP_PASSWORD = "escolhe_uma_senha_forte_aqui"

GOOGLE_SERVICE_ACCOUNT_JSON = """
{
  "type": "service_account",
  "project_id": "caramelo-v2",
  ... (cole o JSON inteiro do arquivo do service account aqui) ...
}
"""
```

⚠️ **Atenção ao JSON:** as aspas triplas (`"""`) são importantes pra manter o JSON multi-linha. Cola exatamente o conteúdo do arquivo `caramelo-bot-key.json` entre as `"""`.

4. Clica em **Deploy**

### 3. Esperar build

Vai levar 1-3 minutos. O Streamlit:
- Clona o repo
- Instala `app/requirements.txt`
- Sobe o app

Quando ficar verde, acessa a URL.

### 4. Primeiro acesso

- Cola a senha que você definiu em `APP_PASSWORD`
- Vai pro dashboard

---

## Trocar a senha depois

1. Dashboard do Streamlit Cloud → **Settings** do app → **Secrets**
2. Edita `APP_PASSWORD`
3. App reinicia sozinho (~30 seg)

## Atualizar o código

Streamlit Cloud auto-deploya: cada `git push origin main` que afetar `app/` dispara redeploy. Não precisa fazer nada.

## Recursos do free tier

- **Apps:** ilimitados (públicos)
- **Recursos:** 1 GB RAM, 1 CPU compartilhado, sem limite de horas
- **Sleep:** apps sem uso por 7 dias hibernam (reativam automaticamente no próximo acesso)

Pra Pudim Caramelo (uso pessoal/familiar) é mais que suficiente.

## Limitações pra saber

- **Apps são públicos por URL** — qualquer pessoa que descobrir a URL chega na tela de senha. A senha é a proteção.
- **Logs ficam visíveis** pra você no dashboard — útil pra debug.
- **Não tem persistência** dentro do app (não tem disco). Tudo que precisa ser salvo vai pra planilha.

## Troubleshooting

### "Module not found" no deploy
- Confere se a lib tá em `app/requirements.txt`
- Streamlit Cloud só lê o `requirements.txt` que tá na pasta do app

### App não consegue ler a planilha
- Confere se o `GOOGLE_SERVICE_ACCOUNT_JSON` foi colado certo (aspas triplas em TOML)
- Confere se a planilha está compartilhada com o email do service account (`caramelo-bot@caramelo-v2.iam.gserviceaccount.com`)

### App tá lento
- Cache TTL atual é 30s. Pode ser ajustado em `app/lib/data.py`
- Primeira carga após hibernação leva 20-30s (normal)
