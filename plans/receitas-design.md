# Design — Multi-Receita (Receitas + Receita_Ingredientes)

Status: **code complete, migration not yet applied**.

## Motivação

O schema antigo tinha uma única `Receita` (lista plana de ingredientes) servindo
todos os tamanhos. Hoje a Luiza calibra variações (calda + massa em proporções
distintas, receitas alternativas) e precisa:

1. Cadastrar mais de uma receita (ex: "Tradicional", "Doce de Leite", "Coco").
2. Separar visualmente **calda** (caramelo+água que vai pro fundo da forma) de
   **massa** (leite condensado, ovos, leite — o pudim em si).
3. Escolher qual receita cada tamanho usa, com uma marcada como "padrão" pra
   quem não especificou.

## Schema novo

### `Receitas` (tab nova)
| col | nome | tipo | obs |
|-----|------|------|-----|
| A   | receita_id | string | `REC-NNN` |
| B   | nome | string | "Tradicional", "Doce de leite" |
| C   | padrao | boolean | TRUE em exatamente uma linha |
| D   | notas | string | opcional |

### `Receita_Ingredientes` (tab nova, substitui `Receita`)
| col | nome | tipo | obs |
|-----|------|------|-----|
| A   | receita_id | string | FK pra Receitas.receita_id |
| B   | produto_id | string | FK pra Produtos.id |
| C   | nome | string | snapshot do nome do produto (consistente com Receita antiga) |
| D   | qtde | number | quantidade na receita inteira |
| E   | unidade | string | KG/G/L/ML/UN/DZ/... |
| F   | componente | string | "calda" ou "massa" |

Chave composta: (receita_id, produto_id) — um produto aparece no máximo uma vez
por receita. Para casos onde o mesmo ingrediente conceitual entra em duas
fases (açúcar cristal na calda + açúcar refinado na massa), são produtos
distintos no cadastro (ALI-XXX diferentes), então linhas diferentes.

### `Tamanhos` (mudança aditiva)
Adiciona coluna **I = `receita_id`** (opcional). Vazio → usa a receita padrão.

### `_Receita_old` (rollback)
A migração renomeia a tab `Receita` antiga em vez de deletar — qualquer
correção pode ser feita comparando com essa cópia preservada.

## Migração

Script `scripts/migrate_receitas.py`, espelhando o padrão de
`migrate_categoria.py`:
- Default = **dry-run**. Imprime a classificação completa de cada ingrediente
  em calda/massa e o plano de mudanças. Não escreve nada.
- `--apply` exige confirmação interativa ("yes") quando rodando em tty.
- Recusa rodar de novo se `Receitas` já existe (estado já migrado) ou se está
  em estado meio-migrado (`Receita_Ingredientes` sem `Receitas`).

### Regra de classificação calda/massa

```
nome (lowercase, sem acentos) startswith "acucar"  → calda
nome contém "agua"                                 → calda
caso contrário                                     → massa
```

Justificativa:
- Receita atual do pudim: a **calda** é açúcar cristal + água, derretido no
  fundo da forma. Tudo o que entra na calda começa com "açúcar" ou contém
  "água" no nome.
- O resto (leite condensado, leite, ovos, açúcar refinado se houver, etc.)
  vai na **massa** que é o pudim em si.
- Se essa heurística errar pra algum item específico, basta editar a coluna
  F em `Receita_Ingredientes` depois — ou ajustar a função
  `classify_componente()` antes do `--apply`.

A classificação é impressa na tela antes do write — usuária revisa, depois
roda `--apply`.

## Camada de dados (`app/lib/data.py`)

- `get_receitas()` — lê tab `Receitas`. Normaliza `padrao` pra `bool`.
- `get_receita_ingredientes(receita_id=None)` — lê `Receita_Ingredientes` com
  filtro opcional. **Shim de transição**: se a tab nova não existe ainda, lê
  silenciosamente da `Receita` antiga sintetizando `receita_id="REC-001"` e
  `componente=""`. Comentário no código sinaliza que esse shim pode ser
  removido depois que toda instância tiver rodado a migração.
- `get_receita()` — wrapper back-compat (retorna formato antigo: produto_id |
  nome | qtde | unidade) consumindo a receita padrão. Mantido pra não
  quebrar callers internos.
- `resolve_receita_id_for_tamanho(row)` — escolhe qual receita_id usar:
  1. coluna `receita_id` do tamanho se preenchida
  2. receita marcada `padrao=TRUE`
  3. primeira receita disponível
  4. fallback final `REC-001` (pré-migração)
- `calc_custo_alimento_unid(tamanho_id)` — usa
  `get_receita_ingredientes(resolved_id)` em vez de `get_receita()`.

`get_tamanhos()` agora lê até a coluna I e expõe `receita_id`.
`get_tamanho_costs()` passa `receita_id` adiante pro consumidor.

## Páginas

### `📜 Receitas` (nova, `app/pages/7_📜_Receitas.py`)

Estrutura igual à 🍮 Tamanhos:
- Guard antes do conteúdo: se `Receitas` não existe ainda, mostra warning
  com o comando exato pra rodar a migração e `st.stop()`.
- Tabs "📋 Receitas cadastradas" / "➕ Nova receita".
- Cada card: nome + badge REC-NNN + meta "padrão" se for. Duas colunas com
  ingredientes da Calda e da Massa em tabelas estáticas mostrando produto,
  qtde, unidade e custo ao vivo (com base no último `preco_unitario` em
  Compras). KPI compacto pro subtotal de cada componente + KPI pro total.
- Expander **✏️ Editar receita**: nome, checkbox padrão, multiselect pra
  adicionar produtos novos por componente (ALI filtrado, ordenado), e
  número-input + selectbox de unidade pra cada existente, com 🗑️ pra
  remover. Submit invalida cache. Marcar padrão desmarca os outros via
  `_ensure_single_padrao`.
- Expander **🗑️ Deletar receita**: refusa deletar se é padrão (precisa
  marcar outra antes). Confirmação dupla. Deleta da `Receitas` + apaga
  todos os ingredientes vinculados.
- Tab "Nova receita": nome, checkbox padrão, observações, dois blocos
  multiselect pra calda/massa com qtde+unidade. Cria com próximo
  `REC-NNN` via `_next_id_for_prefix`.

### `🍮 Tamanhos` (mudança aditiva)

- Meta line dos cards mostra "Receita: X" só quando o tamanho usa uma receita
  **diferente** da padrão (evita ruído visual).
- Form de edição: selectbox "Receita" embaixo de Preço/Rendimento (coluna
  esquerda), com opção `(padrão) — <nome>` no topo (valor vazio). Salvar
  com `(padrão)` escreve string vazia em `Tamanhos!I{n}` — assim qualquer
  mudança futura da padrão flui automaticamente.
- Heading do expander "Ver composição completa" agora mostra o nome da
  receita em uso ("Ingredientes da receita (Tradicional)").
- Toda a integração é defensiva: se `Receitas` não existe (`receitas_df`
  vazio), o selectbox não aparece e o save não toca na coluna I.

## Helpers compartilhados

`qty_input_params(produto_id, produtos_df)` foi promovido a função pública
em `app/lib/ui.py` (era `_qty_input_params` privado em Tamanhos). Mesma
lógica — retorna `(min, step, format, is_int)` baseado na unidade do
produto. A Receitas reusa.

A versão privada em Tamanhos continua existindo como thin alias pra evitar
mexer no resto do arquivo.

## Pontos de atenção / decisões

1. **Não APPLY pelo agente.** A migração foi entregue pronta mas a Luiza
   é quem roda no terminal local. Sandbox bloqueia escritas mesmo.
2. **Não toquei no bot.** Bot continua sem registrar receitas — escopo
   é só app por enquanto.
3. **Shim silencioso.** `get_receita_ingredientes` lê a tab antiga sem
   warning se a nova não existe. Decisão deliberada: o app continua
   funcionando "como antes" até a migração rodar; ninguém precisa
   adivinhar que tem um shim ativo. Comentário no código explica
   quando deletar.
4. **Coluna I em `Tamanhos`.** A migração cria o cabeçalho mas deixa
   valores vazios — todos os tamanhos existentes seguem usando a padrão
   (que após a migração é REC-001 / Tradicional). Sem efeito colateral
   no custo calculado.
5. **`padrao` como booleano de planilha.** Escrevemos `True`/`False`
   Python com `USER_ENTERED` — Sheets aceita e armazena como TRUE/FALSE.
   O reader normaliza qualquer variante (`TRUE`, `true`, `1`, `sim`) pra
   bool Python.

## Como aplicar a migração (passo a passo pra Luiza)

```bash
cd ~/ClaudeCode/Caramelo

# 1. Ativar venv e exportar env vars (mesma config do bot)
source bot/.venv/bin/activate
export SPREADSHEET_ID=1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE
export GOOGLE_SERVICE_ACCOUNT_JSON=~/ClaudeCode/Caramelo/Caramelo-bot-key_caramelo-v2-692ac2b31508.json

# 2. Dry-run — REVISAR a classificação calda/massa de cada ingrediente
python scripts/migrate_receitas.py

# Saída esperada: tabela com produto_id | nome | qtde | unidade | componente
# Se algum ingrediente foi classificado errado, ajuste depois manualmente
# na coluna F de Receita_Ingredientes, ou edite a regra em
# classify_componente() antes do --apply.

# 3. Apply — vai pedir "yes" antes de escrever
python scripts/migrate_receitas.py --apply

# 4. Recarregar app e abrir 📜 Receitas pra conferir.
#    Cache do Streamlit limpa em ~30s, ou clica 🔄 Atualizar.
```

Rollback (se algo der errado):
- A tab original sobreviveu como `_Receita_old`.
- Renomeia `_Receita_old` → `Receita` (UI da planilha), deleta `Receitas` e
  `Receita_Ingredientes`. App volta a usar o shim.
