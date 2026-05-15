# Pudim Caramelo — App

Streamlit dashboard pra gerenciar a planilha do Pudim Caramelo sem mexer
nas células diretamente.

## Páginas

- **🏠 Home** — KPIs do mês, últimas compras, recomendações de fornecedores
- **🍮 Tamanhos** — lista com custo unitário ao vivo, wizard pra criar novo tamanho com embalagens
- **📦 Produtos** — catálogo com filtros, histórico de preço por produto, análise por fornecedor, detector de outliers
- **🧮 Calculadora** — simulador de preço/margem, atualiza preço de venda
- **🏭 Produção** — registra fornadas com distribuição entre tamanhos (vendidos/cortesia/teste)
- **🛒 Compras** — resumo mensal, drill-down detalhado, filtros

## Rodar localmente

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set secrets via env vars
export SPREADSHEET_ID="1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE"
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat ~/Documents/Credenciais/caramelo-bot-key.json)"
export APP_PASSWORD="escolha_uma_senha"

streamlit run 🏠_Home.py
```

Abre em `http://localhost:8501`.

## Deploy no Streamlit Community Cloud

Streamlit Cloud roda apps Streamlit grátis ilimitadamente (apps públicos com senha).

Veja `SETUP.md` pro passo a passo de deploy.

## Como funciona

- Lê e escreve na mesma planilha que o bot já usa (`1hV9zTIMyX3wlULkWAYN_...`)
- Usa o mesmo service account
- Cache de 30s nas leituras pra não martelar API
- Auth por senha simples (env var ou Streamlit Secrets)

## Arquitetura

```
app/
├── 🏠_Home.py        # Home / dashboard
├── pages/
│   ├── 1_🍮_Tamanhos.py
│   ├── 2_📦_Produtos.py
│   ├── 3_🧮_Calculadora.py
│   ├── 4_🏭_Produção.py
│   └── 5_🛒_Compras.py
├── lib/
│   ├── auth.py             # password gate
│   ├── data.py             # cached reads, cost calcs
│   └── ui.py               # currency/percent formatting
├── .streamlit/
│   └── config.toml         # theme
└── requirements.txt
```

Reusa `bot/lib/sheets.py` pra I/O — adicionando esse path via `sys.path` em `data.py`.
