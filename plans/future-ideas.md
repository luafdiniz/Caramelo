# Ideias futuras (não escopadas)

Lista de ideias mencionadas em conversa que ainda não viraram tarefa. Cada item
inclui o "porquê adiamos" pra evitar revisitar a discussão do zero.

## Planilha simplificada espelho

**Pedido:** Manter uma segunda planilha mais simples que serve como interface
de edição de fallback caso o Streamlit saia do ar ou seja preciso editar dados
sem tocar na planilha-fonte (`1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE`).
A planilha espelho alimentaria a original e vice-versa.

**Por que está adiado:**
- Sincronização bidirecional entre planilhas é cara — precisa de conflict
  resolution (qual ganha quando as duas mudam?), drift de schema, e timing
  (cada edição dispara qual lado?).
- Estado atual já tem fallback razoável: backup diário em CSV no repo
  privado `Caramelo-backups` (cada CSV é editável manualmente e reimportável).
- Antes de implementar, vale entender se o caso de uso real seria:
  (a) cópia "read-only" alternativa para consulta — backup já cobre, ou
  (b) edição de emergência que sincroniza de volta — aí sim precisa do
      espelho bidirecional.

**Se for retomar:** comece definindo qual lado é mestre. Sugestão de design
mais simples: planilha espelho é write-only (substitui a original em caso de
desastre), não tenta sync bidirecional. Sync unidirecional é trivial via
GitHub Actions.

## Comando `/novo` no bot

**Pedido:** Cadastrar insumo direto pelo Telegram sem precisar de nota.

**Por que está adiado:** Foi tentado durante a sessão de 2026-05-12 e
revertido por estar incompleto. Demanda fluxo de conversa (nome → categoria
→ unidade → confirmar) que não estava maduro o suficiente pra deploy. Tem
um placeholder em `plans/session-2026-05-12.md`.

## Estoque com baixa por consumo

**Pedido:** Hoje só registramos entradas (compras). Pra ter estoque real,
faltaria registrar saídas (consumo nas fornadas, perda).

**Por que está adiado:** Receita + Embalagens_Por_Tamanho já permitem
calcular consumo teórico por fornada — basta multiplicar. Implementar
"estoque atual = compras − consumo teórico" é viável mas adiciona
modelagem de perda, validade e ajustes manuais que aumentam o escopo
significativamente.

## UI para gerenciar Aliases

**Pedido:** Página no Streamlit pra ver/deletar/editar aliases aprendidos
pelo bot (hoje é direto na aba `Aliases` da planilha).

**Por que está adiado:** Baixo volume de aliases (3 até agora). Editar
manualmente na planilha é viável enquanto não houver dezenas.

## Fornadas avançado

**Pedido:** Cálculo de quantos insumos foram consumidos por fornada,
alertas de baixo estoque, comparação real × teórico, etc.

**Por que está adiado:** Depende de estoque real (item acima) e de
analisar quanto a margem de erro entre receita teórica e real importa
no dia-a-dia.
