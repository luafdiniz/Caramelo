# Data Model v1 — Pudim Caramelo Google Sheets

## Architecture

```
┌─────────────────────────────────────────────────────┐
│            INPUT CHANNELS (future)                   │
│  Telegram Bot · WhatsApp · Google Form · Manual      │
└──────────────────────┬──────────────────────────────┘
                       │ Google Sheets API
                       ▼
┌─────────────────────────────────────────────────────┐
│           DATA TABS (structured tables)               │
│                                                       │
│  Produtos · Fornecedores · Compras · Fornadas         │
└──────────────────────┬──────────────────────────────┘
                       │ Formulas (VLOOKUP / QUERY / FILTER)
                       ▼
┌─────────────────────────────────────────────────────┐
│         CALCULATION & VIEW TABS                       │
│                                                       │
│  Fichas Técnicas · Calculadora · Produção · Dashboard │
└─────────────────────────────────────────────────────┘
```

**Rule:** Data tabs have rigid table format (header row 1, one record per row, no merged cells). Calculation tabs only READ from data tabs — never edited directly.

---

## ID Convention

Products are coded by category with independent numbering:

| Prefix | Category | Range | Example |
|--------|----------|-------|---------|
| `ALI-` | Alimentos (food ingredients) | ALI-001 onwards | ALI-001 = Leite Condensado 395g |
| `FOR-` | Formas (molds) | FOR-001 onwards | FOR-001 = Forma Pudim Grande 500ml |
| `EMB-` | Embalagens (packaging) | EMB-001 onwards | EMB-001 = Sacola Kraft GG |
| `EQP-` | Equipamentos (equipment) | EQP-001 onwards | EQP-001 = Grade Metal |

Other entities:

| Prefix | Entity | Example |
|--------|--------|---------|
| `FORN-` | Fornecedores (suppliers) | FORN-001 = Apoio Mineiro |
| `TAM-` | Tamanhos (pudding sizes) | TAM-001 = Médio 500g |
| `FN-` | Fornadas (batches) | FN-001 = Fornada 01 |
| `C-` | Compras (purchases) | C-001 = first purchase log entry |
| `FC-` | Fluxo de Caixa (cash flow) | FC-001 = first cash flow entry |

---

## DATA TABS

### 1. Produtos

Master product list. One row per unique product, regardless of supplier. ID prefix determines category.

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `ALI-001` | Prefix by category, never changes |
| B | Nome | text | `LEITE CONDENSADO 395G` | Canonical product name |
| C | Unidade | text | `UN` | KG, L, UN, M, Pente, Folha |
| D | Notas | text | `Usado na calda` | Optional |

Note: Categoria is derived from the ID prefix — no need for a separate column.

**Migration from current sheet:**

#### Alimentos (ALI-)

| Current codes | New ID | Nome | Unidade |
|---|---|---|---|
| A-002, A-005, A-007 | ALI-001 | LEITE CONDENSADO 395G | UN |
| A-001, A-010 | ALI-002 | AÇÚCAR REFINADO 1KG | KG |
| A-003, A-008 | ALI-003 | LEITE INTEGRAL 1L | L |
| A-004, A-006, A-009 | ALI-004 | OVO (UNIDADE) | UN |

#### Formas (FOR-)

| Current codes | New ID | Nome | Unidade |
|---|---|---|---|
| F-001, F-007, F-008 | FOR-001 | FORMA PUDIM GRANDE 500ML | UN |
| F-002, F-005, F-009 | FOR-002 | FORMA PUDIM FAMÍLIA 1,1L | UN |
| F-003 | FOR-003 | FORMA PUDIM MÉDIA 250ML | UN |
| F-004 | FOR-004 | FORMA PUDIM PEQUENA 150ML | UN |
| F-006 | FOR-005 | FORMA QUADRADA 220ML | UN |

#### Embalagens (EMB-)

| Current codes | New ID | Nome | Unidade |
|---|---|---|---|
| EMB-001 | EMB-001 | SACOLA KRAFT GG (35X30X18) | UN |
| EMB-002 | EMB-002 | SACOLA KRAFT G (31X26X13) | UN |
| EMB-003 | EMB-003 | SACO CELOFANE GG (45X59) | UN |
| EMB-004 | EMB-004 | SACO CELOFANE G (30X44) | UN |
| EMB-005 | EMB-005 | FITA PRODUTO ARTESANAL | M |
| EMB-006 | EMB-006 | COLHER ROXA | UN |
| EMB-007 | EMB-007 | SAQUINHO P/ COLHER | UN |
| EMB-008 | EMB-008 | ETIQUETA REDONDA TAMPA VINIL (7,5x7,5) | FOLHA |
| EMB-009 | EMB-009 | ADESIVO CACHORRO CARAMELO | FOLHA |
| EMB-010 | EMB-010 | ADESIVO BANDEIRA CARAMELO | FOLHA |
| EMB-011 | EMB-011 | ADESIVO ME VÊ 2 FATIAS | FOLHA |
| EMB-012 | EMB-012 | SACOLA KRAFT (24X15X25) | UN |
| EMB-013 | EMB-013 | SACO PLÁSTICO POLIPROPILENO (30X44) | UN |
| EMB-014 | EMB-014 | FITA CETIM 15MM ROXO | M |
| EMB-015 | EMB-015 | FITA CETIM 15MM LILÁS | M |
| EMB-016 | EMB-016 | BARBANTE SISAL | M |
| EMB-017 | EMB-017 | BARBANTE VERMELHO E BRANCO | M |
| EMB-018 | EMB-018 | ETIQUETA REDONDA TAMPA PAPEL (7,5x7,5) | FOLHA |
| EMB-019 | EMB-019 | SACOLA KRAFT (31X17X30) | UN |
| EMB-020 | EMB-020 | SACO PLÁSTICO POLIPROPILENO (35X50) | UN |

#### Equipamentos (EQP-)

| Current codes | New ID | Nome | Unidade |
|---|---|---|---|
| EQP-001 | EQP-001 | GRADE METAL 46X26X3 | UN |
| EQP-002 | EQP-002 | LUVA SILICONE | UN |
| EQP-003 | EQP-003 | PANELINHA MAX TRANSP C/TAMPA | UN |
| EQP-004 | EQP-004 | GRADE DE RESFRIAMENTO | UN |

---

### 2. Fornecedores

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `FORN-001` | Unique |
| B | Nome | text | `Apoio Mineiro` | |
| C | Tipo | text | `Supermercado` | Supermercado, Loja, Online, Feira, Gráfica |
| D | Localização | text | `BH - Savassi` | Optional |
| E | Notas | text | `Bom preço de leite condensado` | Optional |

**Known suppliers from current data:**

| ID | Nome | Tipo |
|---|---|---|
| FORN-001 | Apoio Mineiro | Supermercado |
| FORN-002 | Supernosso | Supermercado |
| FORN-003 | Maria Chocolate | Loja |
| FORN-004 | 1001 Festas | Loja |
| FORN-005 | Impacto | Loja |
| FORN-006 | Feira | Feira |
| FORN-007 | iFood | Online |
| FORN-008 | QualiGraf | Gráfica |
| FORN-009 | Distribuidora Belopack | Loja |
| FORN-010 | Mercado Livre (EmbalaiadoSP) | Online |
| FORN-011 | Gato Preto (Mercado Central) | Loja |

---

### 3. Compras

Log of every purchase. This is the **key table** — every time something is bought, a row is added here. This is what the Telegram bot would write to in the future.

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `C-001` | Auto-increment |
| B | Data | date | `2025-11-24` | When purchased |
| C | Produto_ID | text | `ALI-001` | References Produtos (any prefix) |
| D | Fornecedor_ID | text | `FORN-001` | References Fornecedores |
| E | Marca | text | `CEMIL` | Brand of this specific purchase |
| F | Qtde_Embalagens | number | `2` | How many packs bought |
| G | Unidades_por_Embalagem | number | `1` | Units per pack |
| H | Total_Unidades | number (calc) | `2` | =F*G |
| I | Preco_Total | currency | `10.98` | Total paid |
| J | Preco_Unitario | currency (calc) | `5.49` | =I/H |
| K | Notas | text | `Promoção` | Optional |

**Why Marca is here and not in Produtos:** The same product (Leite Condensado 395g) can be bought in different brands (CEMIL, Moça, Italac). The brand is a property of the purchase, not of the product.

---

### 4. Tamanhos

Defines each pudding size/format and its sales channel.

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `TAM-001` | Unique |
| B | Nome | text | `Médio 500g` | |
| C | Peso_KG | number | `0.5` | Weight in KG |
| D | Volume_ML | number | `500` | Form volume in ML |
| E | Rendimento | number | `2` | Units per recipe |
| F | Canal | text | `Fornada` | Fornada, Pronta Entrega |
| G | Preco_Venda | currency | `40.00` | Current sale price |
| H | Notas | text | | Optional |

**Data:**

| ID | Nome | Peso | Volume | Rendimento | Canal | Preço |
|---|---|---|---|---|---|---|
| TAM-001 | Médio 500g | 0.5 | 500 | 2 | Fornada | 40.00 |
| TAM-002 | Grande 1Kg | 1.0 | 1100 | 1 | Pronta Entrega | 90.00 |
| TAM-003 | Quadrado 200g | 0.22 | 220 | 5 | Pronta Entrega | TBD |

---

### 5. Receita

Ingredients for ONE recipe of pudding (same base recipe for all sizes).

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | Produto_ID | text | `ALI-001` | References Produtos |
| B | Nome_Produto | text (calc) | `LEITE CONDENSADO 395G` | =VLOOKUP from Produtos |
| C | Qtde | number | `1` | Quantity used in one recipe |
| D | Unidade | text (calc) | `UN` | =VLOOKUP from Produtos |

**Data (from current Receita tab):**

| Produto_ID | Qtde | Notes |
|---|---|---|
| ALI-002 | 0.1 | Açúcar (100g) |
| ALI-001 | 1 | 1 caixa de leite condensado |
| ALI-003 | 0.395 | 395ml de leite |
| ALI-004 | 4 | 4 ovos |

---

### 6. Embalagens_Por_Tamanho

Which packaging items (forms + packaging) are used for each pudding size.

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | Tamanho_ID | text | `TAM-001` | References Tamanhos |
| B | Produto_ID | text | `FOR-001` | References Produtos (FOR- or EMB-) |
| C | Nome_Produto | text (calc) | `FORMA PUDIM GRANDE 500ML` | VLOOKUP |
| D | Qtde_Por_Unidade | number | `1` | How many of this per pudding |

**Data for TAM-001 (Médio 500g):**

| Tamanho_ID | Produto_ID | Qtde | Description |
|---|---|---|---|
| TAM-001 | FOR-001 | 1 | Forma 500ml |
| TAM-001 | EMB-012 | 1 | Sacola kraft |
| TAM-001 | EMB-013 | 1 | Saco plástico |
| TAM-001 | EMB-017 | 0.45 | Barbante |
| TAM-001 | EMB-018 | 1 | Etiqueta papel |
| TAM-001 | EMB-009 | 1 | Adesivo cachorro |
| TAM-001 | EMB-010 | 1 | Adesivo bandeira |
| TAM-001 | EMB-011 | 1 | Adesivo me vê 2 fatias |

**Data for TAM-002 (Grande 1Kg):**

| Tamanho_ID | Produto_ID | Qtde | Description |
|---|---|---|---|
| TAM-002 | FOR-002 | 1 | Forma família 1,1L |
| TAM-002 | EMB-019 | 1 | Sacola kraft grande |
| TAM-002 | EMB-003 | 1 | Celofane GG |
| TAM-002 | EMB-017 | 0.45 | Barbante |
| TAM-002 | EMB-018 | 1 | Etiqueta papel |
| TAM-002 | EMB-009 | 1 | Adesivo cachorro |
| TAM-002 | EMB-010 | 1 | Adesivo bandeira |

**Data for TAM-003 (Quadrado 200g):**

| Tamanho_ID | Produto_ID | Qtde | Description |
|---|---|---|---|
| TAM-003 | FOR-005 | 1 | Forma quadrada 220ml |
| TAM-003 | EMB-012 | 1 | Sacola kraft |
| TAM-003 | EMB-013 | 1 | Saco plástico |
| TAM-003 | EMB-017 | 0.45 | Barbante |
| TAM-003 | EMB-018 | 1 | Etiqueta papel |
| TAM-003 | EMB-009 | 1 | Adesivo cachorro |
| TAM-003 | EMB-010 | 1 | Adesivo bandeira |
| TAM-003 | EMB-011 | 1 | Adesivo me vê 2 fatias |

---

### 7. Fornadas

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `FN-001` | FN = Fornada |
| B | Data_Inicio | date | `2025-11-24` | |
| C | Data_Fim | date | `2025-11-28` | |
| D | Tamanho_ID | text | `TAM-001` | References Tamanhos |
| E | Qtde_Produzida | number | `14` | Total produced |
| F | Qtde_Vendida | number | `13` | Sold |
| G | Qtde_Cortesia | number | `1` | Influencer/family |
| H | Preco_Venda_Unit | currency | `40.00` | Price per unit this batch |
| I | Receita_Total | currency (calc) | `520.00` | =F*H |
| J | Custo_Unit | currency (calc) | | From Ficha Técnica for this Tamanho |
| K | Custo_Total | currency (calc) | | =J*E |
| L | Lucro | currency (calc) | | =I-K |
| M | Notas | text | `Fornada especial de Natal` | |

---

### 8. Fluxo_Caixa

Simple cash flow log. Can be partially auto-generated from Compras (exits) and Fornadas (entries), but also allows manual entries (e.g., transport costs).

| Column | Name | Type | Example | Notes |
|--------|------|------|---------|-------|
| A | ID | text | `FC-001` | Auto-increment |
| B | Data | date | `2025-11-24` | |
| C | Tipo | text | `Entrada` | Entrada, Saída |
| D | Valor | currency | `520.00` | Always positive |
| E | Categoria | text | `Venda` | Venda, Compra Insumos, Compra Embalagem, Transporte, Outro |
| F | Referencia | text | `FN-001` | Optional: links to Fornada or Compra |
| G | Descricao | text | `Venda 13 pudins fornada 01` | |

---

## CALCULATION TABS (read-only, formula-driven)

### Ficha_Tecnica

One section per Tamanho that calculates:

**Section 1 — Ingredients cost per unit:**
- For each ingredient in Receita, pulls the **latest price** from Compras (most recent purchase of that Produto_ID)
- Cost per recipe = SUM of (qty × latest unit price)
- Cost per unit = Cost per recipe / Rendimento

**Section 2 — Packaging cost per unit:**
- For each item in Embalagens_Por_Tamanho for this size, pulls latest price from Compras
- Cost per unit = SUM of (qty × latest unit price)

**Section 3 — Summary:**
- Total cost per unit = ingredients + packaging
- Sale price (from Tamanhos)
- Profit per unit
- Margin %

**Key formula — latest unit price for a product:**
```
=IFERROR(
  INDEX(SORT(FILTER(Compras!J:J, Compras!C:C=produto_id, Compras!B:B<>""), FILTER(Compras!B:B, Compras!C:C=produto_id, Compras!B:B<>""), FALSE), 1, 1),
  "SEM PREÇO"
)
```

### Calculadora

- Dropdown to select Tamanho
- Pulls cost from Ficha_Tecnica
- Shows margin simulations for different sale prices
- Shows "what price do I need for X% margin?"

### Produção

- Input: Tamanho + quantity desired
- Calculates: recipes needed, ingredient quantities, packaging quantities
- Could show which items are below needed quantity (if stock tracking is maintained)

### Comparativo_Fornecedores

- For each Produto, shows all suppliers ever used
- Latest price, best price, average price per supplier
- Highlights cheapest current option

---

## FUTURE BOT INTEGRATION NOTES

The data tabs are designed for programmatic access:
- **Row 1 = headers, always** (bot knows column positions)
- **No merged cells** in data tabs
- **ID columns are stable** (bot can reference by ID)
- **Category prefixes in IDs** help the bot validate (a receipt item should map to ALI- or FOR- or EMB-)
- **Compras tab is append-only** (bot adds new rows at the bottom)
- **Fornadas tab is append-only**

### Telegram bot flow (future):

**Receipt photo:**
1. User sends photo → bot extracts text via AI
2. AI maps items to product IDs (ALI-xxx, FOR-xxx, EMB-xxx) and FORN-xxx
3. Bot appends rows to Compras tab via Google Sheets API
4. Bot confirms: "Added 3 items from Apoio Mineiro to Compras"

**Voice/text batch registration:**
1. User sends "Fiz 12 pudins de 500g, vendidos todos a R$40"
2. AI parses → bot appends to Fornadas tab
3. Bot confirms with calculated profit

**Queries:**
1. "Quanto tá custando o pudim de 500g?" → bot reads Ficha_Tecnica
2. "Qual o fornecedor mais barato pra leite condensado?" → bot reads Comparativo_Fornecedores
