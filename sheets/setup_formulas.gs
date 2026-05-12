/**
 * Pudim Caramelo v2 — Google Apps Script
 *
 * Run this ONCE after importing the .xlsx file into Google Sheets.
 * It populates the calculation tabs (Ficha_Tecnica, Calculadora, Produção,
 * Comparativo_Fornecedores) with Google Sheets-native formulas.
 *
 * How to use:
 * 1. Open the imported spreadsheet in Google Sheets
 * 2. Go to Extensions > Apps Script
 * 3. Paste this entire script
 * 4. Click Run > setupAll
 * 5. Authorize when prompted
 * 6. Done! You can delete the Apps Script project after.
 */

function setupAll() {
  setupFichaTecnica();
  setupCalculadora();
  setupProducao();
  setupComparativoFornecedores();
  SpreadsheetApp.getActive().toast('Setup complete! All calculation tabs are ready.', 'Pudim Caramelo', 10);
}

// =============================================================================
// FICHA TÉCNICA
// =============================================================================

function setupFichaTecnica() {
  var ss = SpreadsheetApp.getActive();
  var ws = ss.getSheetByName('Ficha_Tecnica');
  ws.clear();

  // Helper: formula to get latest unit price for a product from Compras
  // Finds the row with the most recent date for that product and returns Preco_Unitario
  function latestPriceFormula(productIdCell) {
    return '=IFERROR(INDEX(SORT(FILTER(Compras!J:J, Compras!C:C=' + productIdCell + ', Compras!B:B<>""), FILTER(Compras!B:B, Compras!C:C=' + productIdCell + ', Compras!B:B<>""), FALSE), 1, 1), "SEM PREÇO")';
  }

  var tamanhos = ss.getSheetByName('Tamanhos').getDataRange().getValues();
  var currentRow = 1;

  // For each Tamanho, create a section
  for (var t = 1; t < tamanhos.length; t++) {
    var tamId = tamanhos[t][0];
    var tamNome = tamanhos[t][1];
    var rendimento = tamanhos[t][4];
    var canal = tamanhos[t][5];
    var precoVenda = tamanhos[t][6];

    // --- TITLE ---
    ws.getRange(currentRow, 1).setValue('FICHA TÉCNICA — ' + tamNome).setFontWeight('bold').setFontSize(13);
    ws.getRange(currentRow, 4).setValue('Canal: ' + canal).setFontStyle('italic');
    currentRow += 1;

    // --- INGREDIENTS SECTION ---
    ws.getRange(currentRow, 1).setValue('INGREDIENTES DA RECEITA').setFontWeight('bold').setFontSize(11);
    currentRow += 1;

    var ingHeaders = ['Produto_ID', 'Nome', 'Qtde/Receita', 'Preço Unit. Atual', 'Custo na Receita'];
    ws.getRange(currentRow, 1, 1, ingHeaders.length).setValues([ingHeaders]).setFontWeight('bold')
      .setBackground('#4A4A8A').setFontColor('white');

    var receita = ss.getSheetByName('Receita').getDataRange().getValues();
    var ingStartRow = currentRow + 1;

    for (var r = 1; r < receita.length; r++) {
      var rr = currentRow + r;
      ws.getRange(rr, 1).setValue(receita[r][0]); // Produto_ID
      ws.getRange(rr, 2).setFormula('=VLOOKUP(A' + rr + ',Produtos!A:B,2,FALSE)'); // Nome
      ws.getRange(rr, 3).setValue(receita[r][2]); // Qtde
      ws.getRange(rr, 4).setFormula(latestPriceFormula('A' + rr)); // Latest price
      ws.getRange(rr, 4).setNumberFormat('R$ #,##0.00');
      ws.getRange(rr, 5).setFormula('=IF(ISNUMBER(D' + rr + '),C' + rr + '*D' + rr + ',"")'); // Cost
      ws.getRange(rr, 5).setNumberFormat('R$ #,##0.00');
    }

    var ingEndRow = currentRow + receita.length - 1;
    currentRow = ingEndRow + 1;

    // Subtotal ingredients
    ws.getRange(currentRow, 4).setValue('Custo Receita:').setFontWeight('bold');
    ws.getRange(currentRow, 5).setFormula('=SUM(E' + ingStartRow + ':E' + ingEndRow + ')').setFontWeight('bold').setNumberFormat('R$ #,##0.00');
    var custoReceitaCell = 'E' + currentRow;
    currentRow += 1;

    // Cost per unit (ingredients)
    ws.getRange(currentRow, 4).setValue('Custo Alimento/Unid:').setFontWeight('bold');
    ws.getRange(currentRow, 5).setFormula('=' + custoReceitaCell + '/' + rendimento).setFontWeight('bold').setNumberFormat('R$ #,##0.00');
    var custoAliUnitCell = 'E' + currentRow;
    currentRow += 2;

    // --- PACKAGING SECTION ---
    ws.getRange(currentRow, 1).setValue('EMBALAGENS (' + tamNome + ')').setFontWeight('bold').setFontSize(11);
    currentRow += 1;

    var embHeaders = ['Produto_ID', 'Nome', 'Qtde/Unid', 'Preço Unit. Atual', 'Custo/Unid'];
    ws.getRange(currentRow, 1, 1, embHeaders.length).setValues([embHeaders]).setFontWeight('bold')
      .setBackground('#4A4A8A').setFontColor('white');

    // Filter embalagens for this tamanho
    var embData = ss.getSheetByName('Embalagens_Por_Tamanho').getDataRange().getValues();
    var embStartRow = currentRow + 1;
    var embCount = 0;

    for (var e = 1; e < embData.length; e++) {
      if (embData[e][0] === tamId) {
        embCount++;
        var er = currentRow + embCount;
        ws.getRange(er, 1).setValue(embData[e][1]); // Produto_ID
        ws.getRange(er, 2).setFormula('=VLOOKUP(A' + er + ',Produtos!A:B,2,FALSE)');
        ws.getRange(er, 3).setValue(embData[e][3]); // Qtde
        ws.getRange(er, 4).setFormula(latestPriceFormula('A' + er));
        ws.getRange(er, 4).setNumberFormat('R$ #,##0.00');
        ws.getRange(er, 5).setFormula('=IF(ISNUMBER(D' + er + '),C' + er + '*D' + er + ',"")');
        ws.getRange(er, 5).setNumberFormat('R$ #,##0.00');
      }
    }

    var embEndRow = currentRow + embCount;
    currentRow = embEndRow + 1;

    // Subtotal packaging
    ws.getRange(currentRow, 4).setValue('Custo Embalagem/Unid:').setFontWeight('bold');
    ws.getRange(currentRow, 5).setFormula('=SUM(E' + embStartRow + ':E' + embEndRow + ')').setFontWeight('bold').setNumberFormat('R$ #,##0.00');
    var custoEmbUnitCell = 'E' + currentRow;
    currentRow += 2;

    // --- SUMMARY ---
    ws.getRange(currentRow, 1).setValue('RESUMO — ' + tamNome).setFontWeight('bold').setFontSize(11)
      .setBackground('#FFF9C4');
    ws.getRange(currentRow, 1, 1, 5).setBackground('#FFF9C4');
    currentRow += 1;

    var summaryStart = currentRow;
    ws.getRange(currentRow, 1).setValue('Custo Alimento/Unid');
    ws.getRange(currentRow, 2).setFormula('=' + custoAliUnitCell).setNumberFormat('R$ #,##0.00');
    currentRow++;

    ws.getRange(currentRow, 1).setValue('Custo Embalagem/Unid');
    ws.getRange(currentRow, 2).setFormula('=' + custoEmbUnitCell).setNumberFormat('R$ #,##0.00');
    currentRow++;

    ws.getRange(currentRow, 1).setValue('CUSTO TOTAL/UNID').setFontWeight('bold');
    ws.getRange(currentRow, 2).setFormula('=B' + (currentRow - 2) + '+B' + (currentRow - 1)).setFontWeight('bold').setNumberFormat('R$ #,##0.00');
    var custoTotalCell = 'B' + currentRow;
    currentRow++;

    ws.getRange(currentRow, 1).setValue('Preço de Venda');
    if (precoVenda) {
      ws.getRange(currentRow, 2).setValue(precoVenda).setNumberFormat('R$ #,##0.00');
    } else {
      ws.getRange(currentRow, 2).setValue('A DEFINIR').setFontStyle('italic');
    }
    var precoVendaCell = 'B' + currentRow;
    currentRow++;

    ws.getRange(currentRow, 1).setValue('Lucro/Unid');
    ws.getRange(currentRow, 2).setFormula('=IF(ISNUMBER(' + precoVendaCell + '),' + precoVendaCell + '-' + custoTotalCell + ',"")').setNumberFormat('R$ #,##0.00');
    currentRow++;

    ws.getRange(currentRow, 1).setValue('Margem');
    ws.getRange(currentRow, 2).setFormula('=IF(ISNUMBER(' + precoVendaCell + '),(' + precoVendaCell + '-' + custoTotalCell + ')/' + precoVendaCell + ',"")').setNumberFormat('0.0%');
    currentRow++;

    // Highlight summary area
    ws.getRange(summaryStart, 1, currentRow - summaryStart, 2).setBackground('#FFF9C4');

    currentRow += 3; // spacing between sizes
  }

  // Auto-resize
  ws.autoResizeColumns(1, 5);
}

// =============================================================================
// CALCULADORA
// =============================================================================

function setupCalculadora() {
  var ss = SpreadsheetApp.getActive();
  var ws = ss.getSheetByName('Calculadora');
  ws.clear();

  ws.getRange('A1').setValue('CALCULADORA DE PREÇO E MARGEM').setFontWeight('bold').setFontSize(14);

  // Get tamanhos
  var tamanhos = ss.getSheetByName('Tamanhos').getDataRange().getValues();
  var currentRow = 3;

  for (var t = 1; t < tamanhos.length; t++) {
    var tamNome = tamanhos[t][1];
    var canal = tamanhos[t][5];

    ws.getRange(currentRow, 1).setValue(tamNome + ' (' + canal + ')').setFontWeight('bold').setFontSize(12);
    currentRow += 1;

    // We need to reference the custo total from Ficha_Tecnica
    // Since positions are dynamic, we use a helper cell
    ws.getRange(currentRow, 1).setValue('Custo total/unid (da Ficha Técnica):');
    ws.getRange(currentRow, 2).setValue('← preencher após rodar script').setFontStyle('italic').setFontColor('#999999');
    var custoRef = 'B' + currentRow;
    currentRow += 1;

    // Margin simulation table
    ws.getRange(currentRow, 1).setValue('Simulação de Margem:').setFontWeight('bold');
    currentRow += 1;

    var margins = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8];
    var headerRow = [''];
    for (var m = 0; m < margins.length; m++) {
      headerRow.push((margins[m] * 100) + '% margem');
    }
    ws.getRange(currentRow, 1, 1, headerRow.length).setValues([headerRow]).setFontWeight('bold')
      .setBackground('#4A4A8A').setFontColor('white');
    currentRow += 1;

    // Price needed row
    ws.getRange(currentRow, 1).setValue('Preço de venda');
    for (var m = 0; m < margins.length; m++) {
      // Price = cost / (1 - margin)
      ws.getRange(currentRow, m + 2).setFormula('=IF(ISNUMBER(' + custoRef + '),' + custoRef + '/(1-' + margins[m] + '),"")');
      ws.getRange(currentRow, m + 2).setNumberFormat('R$ #,##0.00');
    }
    currentRow += 1;

    // Profit row
    ws.getRange(currentRow, 1).setValue('Lucro/unid');
    for (var m = 0; m < margins.length; m++) {
      var priceCell = get_column_letter_(m + 2) + (currentRow - 1);
      ws.getRange(currentRow, m + 2).setFormula('=IF(ISNUMBER(' + priceCell + '),' + priceCell + '-' + custoRef + ',"")');
      ws.getRange(currentRow, m + 2).setNumberFormat('R$ #,##0.00');
    }
    currentRow += 2;

    // Custom price simulation
    ws.getRange(currentRow, 1).setValue('Simular preço customizado:').setFontWeight('bold');
    currentRow += 1;

    var customPrices = [25, 30, 35, 40, 45, 50, 60, 90];
    var priceHeader = [''];
    for (var p = 0; p < customPrices.length; p++) {
      priceHeader.push('R$ ' + customPrices[p]);
    }
    ws.getRange(currentRow, 1, 1, priceHeader.length).setValues([priceHeader]).setFontWeight('bold')
      .setBackground('#4A4A8A').setFontColor('white');
    currentRow += 1;

    ws.getRange(currentRow, 1).setValue('Lucro/unid');
    for (var p = 0; p < customPrices.length; p++) {
      ws.getRange(currentRow, p + 2).setFormula('=IF(ISNUMBER(' + custoRef + '),' + customPrices[p] + '-' + custoRef + ',"")');
      ws.getRange(currentRow, p + 2).setNumberFormat('R$ #,##0.00');
    }
    currentRow += 1;

    ws.getRange(currentRow, 1).setValue('Margem');
    for (var p = 0; p < customPrices.length; p++) {
      ws.getRange(currentRow, p + 2).setFormula('=IF(ISNUMBER(' + custoRef + '),(' + customPrices[p] + '-' + custoRef + ')/' + customPrices[p] + ',"")');
      ws.getRange(currentRow, p + 2).setNumberFormat('0.0%');
    }

    currentRow += 3;
  }

  ws.autoResizeColumns(1, 9);
}

// Helper to convert column number to letter
function get_column_letter_(col) {
  var letter = '';
  while (col > 0) {
    var temp = (col - 1) % 26;
    letter = String.fromCharCode(temp + 65) + letter;
    col = Math.floor((col - 1) / 26);
  }
  return letter;
}

// =============================================================================
// PRODUÇÃO
// =============================================================================

function setupProducao() {
  var ss = SpreadsheetApp.getActive();
  var ws = ss.getSheetByName('Produção');
  ws.clear();

  ws.getRange('A1').setValue('PLANEJAMENTO DE PRODUÇÃO').setFontWeight('bold').setFontSize(14);

  ws.getRange('A3').setValue('Tamanho:').setFontWeight('bold');
  ws.getRange('B3').setValue('TAM-001');

  // Data validation for Tamanho dropdown
  var tamanhos = ss.getSheetByName('Tamanhos').getDataRange().getValues();
  var tamIds = [];
  for (var i = 1; i < tamanhos.length; i++) {
    tamIds.push(tamanhos[i][0]);
  }
  var rule = SpreadsheetApp.newDataValidation().requireValueInList(tamIds).build();
  ws.getRange('B3').setDataValidation(rule);

  ws.getRange('A4').setValue('Quantidade desejada:').setFontWeight('bold');
  ws.getRange('B4').setValue(14);

  ws.getRange('A5').setValue('Rendimento/receita:');
  ws.getRange('B5').setFormula('=VLOOKUP(B3,Tamanhos!A:E,5,FALSE)');

  ws.getRange('A6').setValue('Receitas necessárias:').setFontWeight('bold');
  ws.getRange('B6').setFormula('=CEILING(B4/B5)');

  // Ingredients needed
  ws.getRange('A8').setValue('INGREDIENTES NECESSÁRIOS').setFontWeight('bold').setFontSize(11);
  var ingHeaders = ['Produto_ID', 'Nome', 'Qtde/Receita', 'Qtde Total'];
  ws.getRange(9, 1, 1, 4).setValues([ingHeaders]).setFontWeight('bold')
    .setBackground('#4A4A8A').setFontColor('white');

  var receita = ss.getSheetByName('Receita').getDataRange().getValues();
  for (var r = 1; r < receita.length; r++) {
    var rr = 9 + r;
    ws.getRange(rr, 1).setValue(receita[r][0]);
    ws.getRange(rr, 2).setFormula('=VLOOKUP(A' + rr + ',Produtos!A:B,2,FALSE)');
    ws.getRange(rr, 3).setValue(receita[r][2]);
    ws.getRange(rr, 4).setFormula('=C' + rr + '*$B$6');
  }

  var nextRow = 9 + receita.length + 1;

  // Packaging needed
  ws.getRange(nextRow, 1).setValue('EMBALAGENS NECESSÁRIAS').setFontWeight('bold').setFontSize(11);
  nextRow++;
  var embHeaders = ['Produto_ID', 'Nome', 'Qtde/Unid', 'Qtde Total'];
  ws.getRange(nextRow, 1, 1, 4).setValues([embHeaders]).setFontWeight('bold')
    .setBackground('#4A4A8A').setFontColor('white');
  nextRow++;

  // Use FILTER formula for dynamic packaging based on selected Tamanho
  ws.getRange(nextRow, 1).setFormula('=IFERROR(FILTER(Embalagens_Por_Tamanho!B:B, Embalagens_Por_Tamanho!A:A=$B$3),"")');
  ws.getRange(nextRow, 2).setFormula('=IFERROR(FILTER(Embalagens_Por_Tamanho!C:C, Embalagens_Por_Tamanho!A:A=$B$3),"")');
  ws.getRange(nextRow, 3).setFormula('=IFERROR(FILTER(Embalagens_Por_Tamanho!D:D, Embalagens_Por_Tamanho!A:A=$B$3),"")');
  ws.getRange(nextRow, 4).setFormula('=ARRAYFORMULA(IF(C' + nextRow + ':C' + (nextRow + 20) + '<>"",C' + nextRow + ':C' + (nextRow + 20) + '*$B$4,""))');

  ws.autoResizeColumns(1, 4);
}

// =============================================================================
// COMPARATIVO DE FORNECEDORES
// =============================================================================

function setupComparativoFornecedores() {
  var ss = SpreadsheetApp.getActive();
  var ws = ss.getSheetByName('Comparativo_Fornecedores');
  ws.clear();

  ws.getRange('A1').setValue('COMPARATIVO DE FORNECEDORES').setFontWeight('bold').setFontSize(14);
  ws.getRange('A2').setValue('Preço unitário por produto e fornecedor (última compra, menor histórico, maior histórico)')
    .setFontStyle('italic').setFontColor('#666666');

  // Get unique products from Compras
  var headers = ['Produto_ID', 'Nome', 'Fornecedor', 'Marca', 'Última Compra', 'Preço Unit.', 'Menor Preço Histórico', 'Maior Preço Histórico', 'Nº Compras'];
  ws.getRange(4, 1, 1, headers.length).setValues([headers]).setFontWeight('bold')
    .setBackground('#4A4A8A').setFontColor('white');

  // Use QUERY to generate the comparison dynamically
  // This creates a summary grouped by Product + Supplier
  var queryFormula = '=IFERROR(QUERY(Compras!A2:K, "SELECT C, MAX(E), MAX(B), MIN(J), MAX(J), COUNT(A) WHERE C <>\'\' GROUP BY C, D, E ORDER BY C, D LABEL MAX(E) \'Marca\', MAX(B) \'Última Data\', MIN(J) \'Menor Preço\', MAX(J) \'Maior Preço\', COUNT(A) \'Nº Compras\'", 0), "Sem dados")';

  // Simpler approach: one formula per metric using UNIQUE + INDEX/MATCH
  // For better readability, let's use a structured approach

  // List unique Product-Supplier combinations
  ws.getRange(5, 1).setFormula('=IFERROR(SORT(UNIQUE(FILTER(Compras!C:C, Compras!C:C<>""))),"")');

  // For each row, get product name
  for (var row = 5; row <= 50; row++) {
    ws.getRange(row, 2).setFormula('=IF(A' + row + '<>"",IFERROR(VLOOKUP(A' + row + ',Produtos!A:B,2,FALSE),""),"")');

    // Get all suppliers for this product (comma-separated)
    ws.getRange(row, 3).setFormula('=IF(A' + row + '<>"",IFERROR(JOIN(", ",UNIQUE(FILTER(Compras!D:D, Compras!C:C=A' + row + '))),""),"")');

    // Last brand bought
    ws.getRange(row, 4).setFormula('=IF(A' + row + '<>"",IFERROR(INDEX(SORT(FILTER(Compras!E:E, Compras!C:C=A' + row + ', Compras!B:B<>""), FILTER(Compras!B:B, Compras!C:C=A' + row + ', Compras!B:B<>""), FALSE), 1, 1),""),"")');

    // Last purchase date
    ws.getRange(row, 5).setFormula('=IF(A' + row + '<>"",IFERROR(MAX(FILTER(Compras!B:B, Compras!C:C=A' + row + ')),""),"")');
    ws.getRange(row, 5).setNumberFormat('DD/MM/YYYY');

    // Latest unit price
    ws.getRange(row, 6).setFormula('=IF(A' + row + '<>"",IFERROR(INDEX(SORT(FILTER(Compras!J:J, Compras!C:C=A' + row + ', Compras!B:B<>""), FILTER(Compras!B:B, Compras!C:C=A' + row + ', Compras!B:B<>""), FALSE), 1, 1),""),"")');
    ws.getRange(row, 6).setNumberFormat('R$ #,##0.00');

    // Min price ever
    ws.getRange(row, 7).setFormula('=IF(A' + row + '<>"",IFERROR(MIN(FILTER(Compras!J:J, Compras!C:C=A' + row + ')),""),"")');
    ws.getRange(row, 7).setNumberFormat('R$ #,##0.00');

    // Max price ever
    ws.getRange(row, 8).setFormula('=IF(A' + row + '<>"",IFERROR(MAX(FILTER(Compras!J:J, Compras!C:C=A' + row + ')),""),"")');
    ws.getRange(row, 8).setNumberFormat('R$ #,##0.00');

    // Number of purchases
    ws.getRange(row, 9).setFormula('=IF(A' + row + '<>"",IFERROR(COUNTA(FILTER(Compras!A:A, Compras!C:C=A' + row + ')),""),"")');
  }

  ws.autoResizeColumns(1, headers.length);
  ws.setFrozenRows(4);
}
