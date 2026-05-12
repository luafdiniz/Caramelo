#!/bin/bash
# =============================================================================
# Deploy Pudim Caramelo v2 to Google Sheets via GWS CLI
#
# Creates a new spreadsheet with all data tabs populated and calculation tabs
# with Google Sheets-native formulas.
#
# Usage: bash scripts/deploy_to_sheets.sh
# =============================================================================

set -e

echo "=== Pudim Caramelo v2 — Deploy to Google Sheets ==="
echo ""

# --- Step 1: Create spreadsheet with all tabs ---
echo "[1/6] Creating spreadsheet with tabs..."

SHEET_NAMES='["Produtos","Fornecedores","Compras","Tamanhos","Receita","Embalagens_Por_Tamanho","Fornadas","Fluxo_Caixa","Ficha_Tecnica","Calculadora","Produção","Comparativo_Fornecedores"]'

# Build sheets array for create request
SHEETS_JSON=$(python3 -c "
import json
names = $SHEET_NAMES
sheets = []
for i, name in enumerate(names):
    sheets.append({
        'properties': {
            'sheetId': i,
            'title': name,
            'index': i
        }
    })
print(json.dumps({'properties': {'title': 'Pudim Caramelo v2 — Estruturado'}, 'sheets': sheets}))
")

RESULT=$(gws sheets spreadsheets create --json "$SHEETS_JSON" 2>&1)
SPREADSHEET_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['spreadsheetId'])")

echo "   Created: $SPREADSHEET_ID"
echo "   URL: https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID"
echo ""

# Save ID for reference
echo "$SPREADSHEET_ID" > "$(dirname "$0")/../output/spreadsheet_id.txt"

# Helper function to append rows
append_rows() {
    local sheet_name="$1"
    local json_values="$2"
    # Escape the ! in sheet names for the shell
    gws sheets spreadsheets values append \
        --params "{\"spreadsheetId\": \"$SPREADSHEET_ID\", \"range\": \"'${sheet_name}'!A1\", \"valueInputOption\": \"USER_ENTERED\"}" \
        --json "{\"values\": $json_values}" 2>&1 | tail -1
}

# --- Step 2: Populate Produtos ---
echo "[2/6] Populating data tabs..."
echo "   - Produtos..."

append_rows "Produtos" '[
  ["ID", "Nome", "Unidade", "Notas"],
  ["ALI-001", "LEITE CONDENSADO 395G", "UN", ""],
  ["ALI-002", "AÇÚCAR REFINADO 1KG", "KG", ""],
  ["ALI-003", "LEITE INTEGRAL 1L", "L", ""],
  ["ALI-004", "OVO (UNIDADE)", "UN", "Comprado em pente de 30"],
  ["FOR-001", "FORMA PUDIM GRANDE 500ML", "UN", "Plastilânia"],
  ["FOR-002", "FORMA PUDIM FAMÍLIA 1,1L", "UN", ""],
  ["FOR-003", "FORMA PUDIM MÉDIA 250ML", "UN", "Plastilânia"],
  ["FOR-004", "FORMA PUDIM PEQUENA 150ML", "UN", "Plastilânia"],
  ["FOR-005", "FORMA QUADRADA 220ML", "UN", "Plastilânia"],
  ["EMB-001", "SACOLA KRAFT GG (35X30X18)", "UN", ""],
  ["EMB-002", "SACOLA KRAFT G (31X26X13)", "UN", ""],
  ["EMB-003", "SACO CELOFANE GG (45X59)", "UN", ""],
  ["EMB-004", "SACO CELOFANE G (30X44)", "UN", ""],
  ["EMB-005", "FITA PRODUTO ARTESANAL", "M", ""],
  ["EMB-006", "COLHER ROXA", "UN", ""],
  ["EMB-007", "SAQUINHO P/ COLHER", "UN", ""],
  ["EMB-008", "ETIQUETA REDONDA TAMPA VINIL (7,5x7,5)", "FOLHA", ""],
  ["EMB-009", "ADESIVO CACHORRO CARAMELO", "FOLHA", ""],
  ["EMB-010", "ADESIVO BANDEIRA CARAMELO", "FOLHA", ""],
  ["EMB-011", "ADESIVO ME VÊ 2 FATIAS", "FOLHA", ""],
  ["EMB-012", "SACOLA KRAFT (24X15X25)", "UN", ""],
  ["EMB-013", "SACO PLÁSTICO POLIPROPILENO (30X44)", "UN", ""],
  ["EMB-014", "FITA CETIM 15MM ROXO", "M", ""],
  ["EMB-015", "FITA CETIM 15MM LILÁS", "M", ""],
  ["EMB-016", "BARBANTE SISAL", "M", ""],
  ["EMB-017", "BARBANTE VERMELHO E BRANCO", "M", ""],
  ["EMB-018", "ETIQUETA REDONDA TAMPA PAPEL (7,5x7,5)", "FOLHA", ""],
  ["EMB-019", "SACOLA KRAFT (31X17X30)", "UN", ""],
  ["EMB-020", "SACO PLÁSTICO POLIPROPILENO (35X50)", "UN", ""],
  ["EQP-001", "GRADE METAL 46X26X3", "UN", ""],
  ["EQP-002", "LUVA SILICONE", "UN", ""],
  ["EQP-003", "PANELINHA MAX TRANSP C/TAMPA", "UN", ""],
  ["EQP-004", "GRADE DE RESFRIAMENTO", "UN", ""]
]'

# --- Fornecedores ---
echo "   - Fornecedores..."

append_rows "Fornecedores" '[
  ["ID", "Nome", "Tipo", "Localização", "Notas"],
  ["FORN-001", "Apoio Mineiro", "Supermercado", "", ""],
  ["FORN-002", "Supernosso", "Supermercado", "", ""],
  ["FORN-003", "Maria Chocolate", "Loja", "", ""],
  ["FORN-004", "1001 Festas", "Loja", "", ""],
  ["FORN-005", "Impacto", "Loja", "", ""],
  ["FORN-006", "Feira", "Feira", "", ""],
  ["FORN-007", "iFood", "Online", "", ""],
  ["FORN-008", "QualiGraf", "Gráfica", "", ""],
  ["FORN-009", "Distribuidora Belopack", "Loja", "", ""],
  ["FORN-010", "Mercado Livre (EmbalaiadoSP)", "Online", "", ""],
  ["FORN-011", "Gato Preto (Mercado Central)", "Loja", "", ""]
]'

# --- Compras ---
echo "   - Compras..."

append_rows "Compras" '[
  ["ID", "Data", "Produto_ID", "Fornecedor_ID", "Marca", "Qtde_Embalagens", "Unidades_por_Embalagem", "Total_Unidades", "Preco_Total", "Preco_Unitario", "Notas"],
  ["C-001", "2025-01-01", "ALI-002", "FORN-003", "UNIÃO", 1, 1, "=F2*G2", 6.50, "=IF(H2>0,I2/H2,0)", "Migrado da planilha original"],
  ["C-002", "2025-01-01", "ALI-001", "FORN-002", "CEMIL", 1, 1, "=F3*G3", 6.29, "=IF(H3>0,I3/H3,0)", "Migrado da planilha original"],
  ["C-003", "2025-01-01", "ALI-003", "FORN-002", "ITAMBÉ", 1, 1, "=F4*G4", 4.79, "=IF(H4>0,I4/H4,0)", "Migrado da planilha original"],
  ["C-004", "2025-01-01", "ALI-004", "FORN-002", "ASA", 1, 30, "=F5*G5", 22.99, "=IF(H5>0,I5/H5,0)", "Ovo branco"],
  ["C-005", "2025-01-01", "ALI-001", "FORN-004", "CEMIL", 1, 1, "=F6*G6", 5.99, "=IF(H6>0,I6/H6,0)", "Migrado da planilha original"],
  ["C-006", "2025-01-01", "ALI-004", "FORN-006", "FEIRA", 1, 30, "=F7*G7", 35.00, "=IF(H7>0,I7/H7,0)", "Ovo vermelho"],
  ["C-007", "2025-01-01", "ALI-001", "FORN-001", "CEMIL", 1, 1, "=F8*G8", 5.49, "=IF(H8>0,I8/H8,0)", "Migrado da planilha original"],
  ["C-008", "2025-01-01", "ALI-003", "FORN-001", "PORTO ALEGRE", 1, 1, "=F9*G9", 3.59, "=IF(H9>0,I9/H9,0)", "Migrado da planilha original"],
  ["C-009", "2025-01-01", "ALI-004", "FORN-006", "FEIRA", 1, 30, "=F10*G10", 30.00, "=IF(H10>0,I10/H10,0)", "Ovo vermelho - Promoção"],
  ["C-010", "2025-01-01", "ALI-002", "FORN-007", "UNIÃO", 1, 1, "=F11*G11", 5.91, "=IF(H11>0,I11/H11,0)", "Migrado da planilha original"],
  ["C-011", "2025-01-01", "FOR-001", "FORN-003", "PLASTILÂNIA", 1, 6, "=F12*G12", 21.90, "=IF(H12>0,I12/H12,0)", "Migrado da planilha original"],
  ["C-012", "2025-01-01", "FOR-002", "FORN-005", "PLASTILÂNIA", 1, 5, "=F13*G13", 34.80, "=IF(H13>0,I13/H13,0)", "Migrado da planilha original"],
  ["C-013", "2025-01-01", "FOR-003", "FORN-005", "PLASTILÂNIA", 1, 8, "=F14*G14", 21.90, "=IF(H14>0,I14/H14,0)", "Migrado da planilha original"],
  ["C-014", "2025-01-01", "FOR-004", "FORN-005", "PLASTILÂNIA", 1, 10, "=F15*G15", 13.50, "=IF(H15>0,I15/H15,0)", "Migrado da planilha original"],
  ["C-015", "2025-01-01", "FOR-002", "FORN-003", "BLUE STAR", 1, 5, "=F16*G16", 37.00, "=IF(H16>0,I16/H16,0)", "Migrado da planilha original"],
  ["C-016", "2025-01-01", "FOR-005", "FORN-003", "PLASTILÂNIA", 1, 10, "=F17*G17", 14.90, "=IF(H17>0,I17/H17,0)", "Migrado da planilha original"],
  ["C-017", "2025-01-01", "FOR-001", "FORN-009", "PLASTILÂNIA", 1, 6, "=F18*G18", 23.90, "=IF(H18>0,I18/H18,0)", "Migrado da planilha original"],
  ["C-018", "2025-01-01", "FOR-001", "FORN-010", "PLASTILÂNIA", 1, 120, "=F19*G19", 395.00, "=IF(H19>0,I19/H19,0)", "Compra em volume"],
  ["C-019", "2025-01-01", "FOR-002", "FORN-010", "PLASTILÂNIA", 1, 50, "=F20*G20", 316.29, "=IF(H20>0,I20/H20,0)", "Compra em volume"],
  ["C-020", "2025-01-01", "EMB-001", "FORN-005", "VINCO", 1, 25, "=F21*G21", 54.75, "=IF(H21>0,I21/H21,0)", "Migrado da planilha original"],
  ["C-021", "2025-01-01", "EMB-002", "FORN-005", "VINCO", 1, 25, "=F22*G22", 49.80, "=IF(H22>0,I22/H22,0)", "Migrado da planilha original"],
  ["C-022", "2025-01-01", "EMB-003", "FORN-003", "", 1, 25, "=F23*G23", 27.00, "=IF(H23>0,I23/H23,0)", "Migrado da planilha original"],
  ["C-023", "2025-01-01", "EMB-004", "FORN-003", "CROMUS", 1, 25, "=F24*G24", 14.60, "=IF(H24>0,I24/H24,0)", "Migrado da planilha original"],
  ["C-024", "2025-01-01", "EMB-005", "FORN-003", "PROGRESSO", 1, 10, "=F25*G25", 9.50, "=IF(H25>0,I25/H25,0)", "Migrado da planilha original"],
  ["C-025", "2025-01-01", "EMB-006", "FORN-005", "CROPAC", 1, 50, "=F26*G26", 8.90, "=IF(H26>0,I26/H26,0)", "Migrado da planilha original"],
  ["C-026", "2025-01-01", "EMB-007", "FORN-005", "", 1, 100, "=F27*G27", 1.99, "=IF(H27>0,I27/H27,0)", "Migrado da planilha original"],
  ["C-027", "2025-01-01", "EMB-008", "FORN-008", "VINIL BRILHO", 1, 20, "=F28*G28", 20.00, "=IF(H28>0,I28/H28,0)", "Migrado da planilha original"],
  ["C-028", "2025-01-01", "EMB-009", "FORN-008", "VINIL FOSCO", 1, 40, "=F29*G29", 22.00, "=IF(H29>0,I29/H29,0)", "Migrado da planilha original"],
  ["C-029", "2025-01-01", "EMB-010", "FORN-008", "VINIL FOSCO", 1, 62, "=F30*G30", 22.00, "=IF(H30>0,I30/H30,0)", "Migrado da planilha original"],
  ["C-030", "2025-01-01", "EMB-011", "FORN-008", "VINIL FOSCO", 1, 47, "=F31*G31", 22.00, "=IF(H31>0,I31/H31,0)", "Migrado da planilha original"],
  ["C-031", "2025-01-01", "EMB-012", "FORN-011", "", 1, 50, "=F32*G32", 72.00, "=IF(H32>0,I32/H32,0)", "Migrado da planilha original"],
  ["C-032", "2025-01-01", "EMB-013", "FORN-009", "", 1, 100, "=F33*G33", 19.50, "=IF(H33>0,I33/H33,0)", "Migrado da planilha original"],
  ["C-033", "2025-01-01", "EMB-014", "FORN-009", "PROGRESSO", 1, 10, "=F34*G34", 6.25, "=IF(H34>0,I34/H34,0)", "Migrado da planilha original"],
  ["C-034", "2025-01-01", "EMB-015", "FORN-009", "PROGRESSO", 1, 10, "=F35*G35", 6.25, "=IF(H35>0,I35/H35,0)", "Migrado da planilha original"],
  ["C-035", "2025-01-01", "EMB-016", "FORN-004", "TUUT", 1, 36.5, "=F36*G36", 11.99, "=IF(H36>0,I36/H36,0)", "Migrado da planilha original"],
  ["C-036", "2025-01-01", "EMB-017", "FORN-004", "TUUT", 1, 100, "=F37*G37", 13.99, "=IF(H37>0,I37/H37,0)", "Migrado da planilha original"],
  ["C-037", "2025-01-01", "EMB-018", "FORN-008", "PAPEL", 1, 20, "=F38*G38", 16.00, "=IF(H38>0,I38/H38,0)", "Migrado da planilha original"],
  ["C-038", "2025-01-01", "EMB-019", "FORN-011", "", 1, 50, "=F39*G39", 136.00, "=IF(H39>0,I39/H39,0)", "Migrado da planilha original"],
  ["C-039", "2025-01-01", "EMB-020", "FORN-009", "", 1, 100, "=F40*G40", 20.00, "=IF(H40>0,I40/H40,0)", "Migrado da planilha original"],
  ["C-040", "2025-01-01", "EQP-001", "FORN-003", "", 1, 1, "=F41*G41", 69.00, "=IF(H41>0,I41/H41,0)", "Migrado da planilha original"],
  ["C-041", "2025-01-01", "EQP-002", "FORN-003", "", 1, 1, "=F42*G42", 48.00, "=IF(H42>0,I42/H42,0)", "Migrado da planilha original"],
  ["C-042", "2025-01-01", "EQP-003", "FORN-003", "", 1, 2, "=F43*G43", 23.90, "=IF(H43>0,I43/H43,0)", "Migrado da planilha original"],
  ["C-043", "2025-01-01", "EQP-004", "FORN-004", "", 1, 2, "=F44*G44", 24.90, "=IF(H44>0,I44/H44,0)", "Migrado da planilha original"]
]'

# --- Tamanhos ---
echo "   - Tamanhos..."

append_rows "Tamanhos" '[
  ["ID", "Nome", "Peso_KG", "Volume_ML", "Rendimento", "Canal", "Preco_Venda", "Notas"],
  ["TAM-001", "Médio 500g", 0.5, 500, 2, "Fornada", 40.00, ""],
  ["TAM-002", "Grande 1Kg", 1.0, 1100, 1, "Pronta Entrega", 90.00, ""],
  ["TAM-003", "Quadrado 200g", 0.22, 220, 5, "Pronta Entrega", "", "Preço a definir"]
]'

# --- Receita ---
echo "   - Receita..."

append_rows "Receita" '[
  ["Produto_ID", "Nome_Produto", "Qtde", "Unidade"],
  ["ALI-002", "=VLOOKUP(A2,Produtos!A:B,2,FALSE)", 0.1, "=VLOOKUP(A2,Produtos!A:C,3,FALSE)"],
  ["ALI-001", "=VLOOKUP(A3,Produtos!A:B,2,FALSE)", 1, "=VLOOKUP(A3,Produtos!A:C,3,FALSE)"],
  ["ALI-003", "=VLOOKUP(A4,Produtos!A:B,2,FALSE)", 0.395, "=VLOOKUP(A4,Produtos!A:C,3,FALSE)"],
  ["ALI-004", "=VLOOKUP(A5,Produtos!A:B,2,FALSE)", 4, "=VLOOKUP(A5,Produtos!A:C,3,FALSE)"]
]'

# --- Embalagens_Por_Tamanho ---
echo "   - Embalagens_Por_Tamanho..."

append_rows "Embalagens_Por_Tamanho" '[
  ["Tamanho_ID", "Produto_ID", "Nome_Produto", "Qtde_Por_Unidade"],
  ["TAM-001", "FOR-001", "=VLOOKUP(B2,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-012", "=VLOOKUP(B3,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-013", "=VLOOKUP(B4,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-017", "=VLOOKUP(B5,Produtos!A:B,2,FALSE)", 0.45],
  ["TAM-001", "EMB-018", "=VLOOKUP(B6,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-009", "=VLOOKUP(B7,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-010", "=VLOOKUP(B8,Produtos!A:B,2,FALSE)", 1],
  ["TAM-001", "EMB-011", "=VLOOKUP(B9,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "FOR-002", "=VLOOKUP(B10,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "EMB-019", "=VLOOKUP(B11,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "EMB-003", "=VLOOKUP(B12,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "EMB-017", "=VLOOKUP(B13,Produtos!A:B,2,FALSE)", 0.45],
  ["TAM-002", "EMB-018", "=VLOOKUP(B14,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "EMB-009", "=VLOOKUP(B15,Produtos!A:B,2,FALSE)", 1],
  ["TAM-002", "EMB-010", "=VLOOKUP(B16,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "FOR-005", "=VLOOKUP(B17,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-012", "=VLOOKUP(B18,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-013", "=VLOOKUP(B19,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-017", "=VLOOKUP(B20,Produtos!A:B,2,FALSE)", 0.45],
  ["TAM-003", "EMB-018", "=VLOOKUP(B21,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-009", "=VLOOKUP(B22,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-010", "=VLOOKUP(B23,Produtos!A:B,2,FALSE)", 1],
  ["TAM-003", "EMB-011", "=VLOOKUP(B24,Produtos!A:B,2,FALSE)", 1]
]'

# --- Fornadas ---
echo "   - Fornadas..."

append_rows "Fornadas" '[
  ["ID", "Data_Inicio", "Data_Fim", "Tamanho_ID", "Qtde_Produzida", "Qtde_Vendida", "Qtde_Cortesia", "Preco_Venda_Unit", "Receita_Total", "Custo_Unit", "Custo_Total", "Lucro", "Notas"],
  ["FN-001", "2025-11-24", "2025-11-28", "TAM-001", 13, 13, 0, 40, "=F2*H2", "", "", "", "Fornada 01"],
  ["FN-002", "2025-12-01", "2025-12-05", "TAM-001", 11, 11, 0, 40, "=F3*H3", "", "", "", "Fornada 02"],
  ["FN-003", "2025-12-01", "2025-12-05", "TAM-001", 11, 11, 0, 40, "=F4*H4", "", "", "", "Fornada 03"],
  ["FN-004", "2025-12-01", "2025-12-05", "TAM-001", 11, 11, 0, 40, "=F5*H5", "", "", "", "Fornada 04"],
  ["FN-005", "2025-12-01", "2025-12-05", "TAM-001", 11, 11, 0, 40, "=F6*H6", "", "", "", "Fornada Especial de Natal"]
]'

# --- Fluxo_Caixa ---
echo "   - Fluxo_Caixa..."

append_rows "Fluxo_Caixa" '[
  ["ID", "Data", "Tipo", "Valor", "Categoria", "Referencia", "Descricao"],
  ["FC-001", "2025-11-24", "Entrada", 520, "Venda", "FN-001", "Venda 13 pudins fornada 01"],
  ["FC-002", "2025-11-25", "Saída", 35, "Compra Insumos", "", "Ovos feira"],
  ["FC-003", "2025-12-01", "Saída", 151.50, "Compra Embalagem", "", "Embalagens"],
  ["FC-004", "2025-12-01", "Saída", 106.73, "Compra Embalagem", "", "Embalagens"],
  ["FC-005", "2025-12-01", "Saída", 99, "Compra Embalagem", "", "Embalagens"],
  ["FC-006", "2025-12-01", "Saída", 36, "Transporte", "", "Transporte"]
]'

echo ""

# --- Step 3: Ficha Técnica ---
echo "[3/6] Building Ficha_Tecnica (cost sheets)..."

# Helper for latest price formula
LP='=IFERROR(INDEX(SORT(FILTER(Compras!$J:$J,Compras!$C:$C=A__ROW__,Compras!$B:$B<>""),FILTER(Compras!$B:$B,Compras!$C:$C=A__ROW__,Compras!$B:$B<>""),FALSE),1,1),"SEM PREÇO")'

# Build Ficha Técnica with all 3 sizes
# We'll write it as a single values update
python3 -c "
import json, subprocess, sys

SSID = '$SPREADSHEET_ID'

def lp(row):
    \"\"\"Latest price formula for a given row.\"\"\"
    return f'=IFERROR(INDEX(SORT(FILTER(Compras!\$J:\$J,Compras!\$C:\$C=A{row},Compras!\$B:\$B<>\"\"),FILTER(Compras!\$B:\$B,Compras!\$C:\$C=A{row},Compras!\$B:\$B<>\"\"),FALSE),1,1),\"SEM PREÇO\")'

def cost(row):
    \"\"\"Cost = qty * unit price.\"\"\"
    return f'=IF(ISNUMBER(D{row}),C{row}*D{row},\"\")'

# Ingredients (same for all sizes)
ingredients = [
    ('ALI-002', 0.1),
    ('ALI-001', 1),
    ('ALI-003', 0.395),
    ('ALI-004', 4),
]

# Packaging per size
packaging = {
    'TAM-001': [
        ('FOR-001', 1), ('EMB-012', 1), ('EMB-013', 1), ('EMB-017', 0.45),
        ('EMB-018', 1), ('EMB-009', 1), ('EMB-010', 1), ('EMB-011', 1),
    ],
    'TAM-002': [
        ('FOR-002', 1), ('EMB-019', 1), ('EMB-003', 1), ('EMB-017', 0.45),
        ('EMB-018', 1), ('EMB-009', 1), ('EMB-010', 1),
    ],
    'TAM-003': [
        ('FOR-005', 1), ('EMB-012', 1), ('EMB-013', 1), ('EMB-017', 0.45),
        ('EMB-018', 1), ('EMB-009', 1), ('EMB-010', 1), ('EMB-011', 1),
    ],
}

sizes = [
    ('TAM-001', 'Médio 500g', 2, 'Fornada', 40),
    ('TAM-002', 'Grande 1Kg', 1, 'Pronta Entrega', 90),
    ('TAM-003', 'Quadrado 200g', 5, 'Pronta Entrega', None),
]

rows = []
r = 1  # current row

for tam_id, tam_nome, rendimento, canal, preco in sizes:
    # Title
    rows.append([f'FICHA TÉCNICA — {tam_nome}', '', '', f'Canal: {canal}', ''])
    r += 1

    # Ingredients header
    rows.append(['INGREDIENTES DA RECEITA', '', '', '', ''])
    r += 1
    rows.append(['Produto_ID', 'Nome', 'Qtde/Receita', 'Preço Unit. Atual', 'Custo na Receita'])
    r += 1

    ing_start = r
    for prod_id, qtde in ingredients:
        rows.append([
            prod_id,
            f'=VLOOKUP(A{r},Produtos!A:B,2,FALSE)',
            qtde,
            lp(r),
            cost(r),
        ])
        r += 1
    ing_end = r - 1

    # Subtotal
    rows.append(['', '', '', 'Custo Receita:', f'=SUM(E{ing_start}:E{ing_end})'])
    custo_receita_row = r
    r += 1

    rows.append(['', '', '', 'Custo Alimento/Unid:', f'=E{custo_receita_row}/{rendimento}'])
    custo_ali_row = r
    r += 1

    # Blank
    rows.append(['', '', '', '', ''])
    r += 1

    # Packaging header
    rows.append([f'EMBALAGENS ({tam_nome})', '', '', '', ''])
    r += 1
    rows.append(['Produto_ID', 'Nome', 'Qtde/Unid', 'Preço Unit. Atual', 'Custo/Unid'])
    r += 1

    emb_start = r
    for prod_id, qtde in packaging[tam_id]:
        rows.append([
            prod_id,
            f'=VLOOKUP(A{r},Produtos!A:B,2,FALSE)',
            qtde,
            lp(r),
            cost(r),
        ])
        r += 1
    emb_end = r - 1

    # Subtotal packaging
    rows.append(['', '', '', 'Custo Embalagem/Unid:', f'=SUM(E{emb_start}:E{emb_end})'])
    custo_emb_row = r
    r += 1

    # Blank
    rows.append(['', '', '', '', ''])
    r += 1

    # Summary
    rows.append([f'RESUMO — {tam_nome}', '', '', '', ''])
    r += 1
    rows.append(['Custo Alimento/Unid', f'=E{custo_ali_row}', '', '', ''])
    r += 1
    rows.append(['Custo Embalagem/Unid', f'=E{custo_emb_row}', '', '', ''])
    custo_emb_summary = r
    r += 1
    rows.append(['CUSTO TOTAL/UNID', f'=B{r-2}+B{r-1}', '', '', ''])
    custo_total_row = r
    r += 1
    if preco:
        rows.append(['Preço de Venda', preco, '', '', ''])
    else:
        rows.append(['Preço de Venda', 'A DEFINIR', '', '', ''])
    preco_row = r
    r += 1
    rows.append(['Lucro/Unid', f'=IF(ISNUMBER(B{preco_row}),B{preco_row}-B{custo_total_row},\"\")', '', '', ''])
    r += 1
    rows.append(['Margem', f'=IF(ISNUMBER(B{preco_row}),(B{preco_row}-B{custo_total_row})/B{preco_row},\"\")', '', '', ''])
    r += 1

    # Spacing
    rows.append(['', '', '', '', ''])
    r += 1
    rows.append(['', '', '', '', ''])
    r += 1

print(json.dumps(rows))
" > /tmp/ficha_tecnica_data.json

FICHA_DATA=$(cat /tmp/ficha_tecnica_data.json)

gws sheets spreadsheets values update \
    --params "{\"spreadsheetId\": \"$SPREADSHEET_ID\", \"range\": \"'Ficha_Tecnica'!A1\", \"valueInputOption\": \"USER_ENTERED\"}" \
    --json "{\"values\": $FICHA_DATA}" 2>&1 | tail -1

echo "   Done."
echo ""

# --- Step 4: Calculadora ---
echo "[4/6] Building Calculadora..."

python3 -c "
import json

rows = []
rows.append(['CALCULADORA DE PREÇO E MARGEM', '', '', '', '', '', '', '', ''])
rows.append(['', '', '', '', '', '', '', '', ''])

# For each size, we need to know where CUSTO TOTAL/UNID is in Ficha_Tecnica
# Based on the structure above:
# TAM-001: row starts at 1, CUSTO TOTAL/UNID is at specific row
# We'll reference Ficha_Tecnica directly

sizes = [
    ('Médio 500g', 'Fornada'),
    ('Grande 1Kg', 'Pronta Entrega'),
    ('Quadrado 200g', 'Pronta Entrega'),
]

margins = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
prices = [25, 30, 35, 40, 45, 50, 60, 90]

r = 3
for i, (nome, canal) in enumerate(sizes):
    rows.append([f'{nome} ({canal})', '', '', '', '', '', '', '', ''])
    r += 1

    rows.append(['Custo total/unid:', '', '← Preencher com referência da Ficha_Tecnica', '', '', '', '', '', ''])
    custo_ref = f'B{r}'
    r += 1

    rows.append(['', '', '', '', '', '', '', '', ''])
    r += 1

    # Margin simulation
    header = ['Margem desejada →'] + [f'{int(m*100)}%' for m in margins]
    rows.append(header)
    r += 1

    price_row = ['Preço de venda']
    for m in margins:
        price_row.append(f'=IF(ISNUMBER({custo_ref}),{custo_ref}/(1-{m}),\"\")')
    rows.append(price_row)
    r += 1

    profit_row = ['Lucro/unid']
    for mi, m in enumerate(margins):
        col_letter = chr(66 + mi)  # B, C, D...
        profit_row.append(f'=IF(ISNUMBER({col_letter}{r-1}),{col_letter}{r-1}-{custo_ref},\"\")')
    rows.append(profit_row)
    r += 1

    rows.append(['', '', '', '', '', '', '', '', ''])
    r += 1

    # Custom price simulation
    header2 = ['Preço de venda →'] + [f'R\$ {p}' for p in prices]
    rows.append(header2)
    r += 1

    lucro_row = ['Lucro/unid']
    for p in prices:
        lucro_row.append(f'=IF(ISNUMBER({custo_ref}),{p}-{custo_ref},\"\")')
    rows.append(lucro_row)
    r += 1

    margem_row = ['Margem']
    for p in prices:
        margem_row.append(f'=IF(ISNUMBER({custo_ref}),({p}-{custo_ref})/{p},\"\")')
    rows.append(margem_row)
    r += 1

    rows.append(['', '', '', '', '', '', '', '', ''])
    rows.append(['', '', '', '', '', '', '', '', ''])
    r += 2

print(json.dumps(rows))
" > /tmp/calc_data.json

CALC_DATA=$(cat /tmp/calc_data.json)

gws sheets spreadsheets values update \
    --params "{\"spreadsheetId\": \"$SPREADSHEET_ID\", \"range\": \"'Calculadora'!A1\", \"valueInputOption\": \"USER_ENTERED\"}" \
    --json "{\"values\": $CALC_DATA}" 2>&1 | tail -1

echo "   Done."
echo ""

# --- Step 5: Produção ---
echo "[5/6] Building Produção..."

append_rows "Produção" '[
  ["PLANEJAMENTO DE PRODUÇÃO", "", "", ""],
  ["", "", "", ""],
  ["Tamanho:", "TAM-001", "", ""],
  ["Quantidade desejada:", 14, "", ""],
  ["Rendimento/receita:", "=VLOOKUP(B3,Tamanhos!A:E,5,FALSE)", "", ""],
  ["Receitas necessárias:", "=CEILING(B4/B5)", "", ""],
  ["", "", "", ""],
  ["INGREDIENTES NECESSÁRIOS", "", "", ""],
  ["Produto_ID", "Nome", "Qtde/Receita", "Qtde Total"],
  ["ALI-002", "=VLOOKUP(A10,Produtos!A:B,2,FALSE)", 0.1, "=C10*$B$6"],
  ["ALI-001", "=VLOOKUP(A11,Produtos!A:B,2,FALSE)", 1, "=C11*$B$6"],
  ["ALI-003", "=VLOOKUP(A12,Produtos!A:B,2,FALSE)", 0.395, "=C12*$B$6"],
  ["ALI-004", "=VLOOKUP(A13,Produtos!A:B,2,FALSE)", 4, "=C13*$B$6"],
  ["", "", "", ""],
  ["EMBALAGENS NECESSÁRIAS", "", "", ""],
  ["Produto_ID", "Nome", "Qtde/Unid", "Qtde Total"],
  ["=IFERROR(FILTER(Embalagens_Por_Tamanho!B:B,Embalagens_Por_Tamanho!A:A=$B$3),\"\")", "=IFERROR(FILTER(Embalagens_Por_Tamanho!C:C,Embalagens_Por_Tamanho!A:A=$B$3),\"\")", "=IFERROR(FILTER(Embalagens_Por_Tamanho!D:D,Embalagens_Por_Tamanho!A:A=$B$3),\"\")", "=ARRAYFORMULA(IF(C17:C25<>\"\",C17:C25*$B$4,\"\"))"]
]'

echo "   Done."
echo ""

# --- Step 6: Comparativo Fornecedores ---
echo "[6/6] Building Comparativo_Fornecedores..."

python3 -c "
import json

rows = []
rows.append(['COMPARATIVO DE FORNECEDORES', '', '', '', '', '', '', '', ''])
rows.append(['Preço unitário por produto e fornecedor (última compra, menor e maior históricos)', '', '', '', '', '', '', '', ''])
rows.append(['', '', '', '', '', '', '', '', ''])
rows.append(['Produto_ID', 'Nome', 'Fornecedores', 'Última Marca', 'Última Compra', 'Preço Unit. Atual', 'Menor Preço Hist.', 'Maior Preço Hist.', 'Nº Compras'])

# Row 5 gets the UNIQUE list of products
rows.append([
    '=IFERROR(SORT(UNIQUE(FILTER(Compras!C:C,Compras!C:C<>\"\"))))',
    '', '', '', '', '', '', '', ''
])

# Rows 6-50 get formulas for each product (dynamic based on column A)
for r in range(6, 51):
    rows.append([
        '',  # Col A filled by UNIQUE spill
        f'=IF(A{r}<>\"\",IFERROR(VLOOKUP(A{r},Produtos!A:B,2,FALSE),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(JOIN(\", \",UNIQUE(FILTER(Compras!D:D,Compras!C:C=A{r}))),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(INDEX(SORT(FILTER(Compras!E:E,Compras!C:C=A{r},Compras!B:B<>\"\"),FILTER(Compras!B:B,Compras!C:C=A{r},Compras!B:B<>\"\"),FALSE),1,1),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(MAX(FILTER(Compras!B:B,Compras!C:C=A{r})),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(INDEX(SORT(FILTER(Compras!J:J,Compras!C:C=A{r},Compras!B:B<>\"\"),FILTER(Compras!B:B,Compras!C:C=A{r},Compras!B:B<>\"\"),FALSE),1,1),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(MIN(FILTER(Compras!J:J,Compras!C:C=A{r})),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(MAX(FILTER(Compras!J:J,Compras!C:C=A{r})),\"\"),\"\")',
        f'=IF(A{r}<>\"\",IFERROR(COUNTA(FILTER(Compras!A:A,Compras!C:C=A{r})),\"\"),\"\")',
    ])

print(json.dumps(rows))
" > /tmp/comp_data.json

COMP_DATA=$(cat /tmp/comp_data.json)

gws sheets spreadsheets values update \
    --params "{\"spreadsheetId\": \"$SPREADSHEET_ID\", \"range\": \"'Comparativo_Fornecedores'!A1\", \"valueInputOption\": \"USER_ENTERED\"}" \
    --json "{\"values\": $COMP_DATA}" 2>&1 | tail -1

echo "   Done."
echo ""

# --- Final ---
echo "============================================"
echo "DONE! Spreadsheet ready."
echo ""
echo "ID: $SPREADSHEET_ID"
echo "URL: https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID"
echo ""
echo "Next steps:"
echo "  1. Open the URL above"
echo "  2. In Calculadora tab, link 'Custo total/unid' cells to Ficha_Tecnica"
echo "  3. Review all tabs and validate the data"
echo "============================================"
