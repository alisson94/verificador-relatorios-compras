# Verificador de relatório de compras

Solução da Parte C de um exercício de análise de compras. O script reproduz a conferência de dez itens, calculando os indicadores a partir do CSV e comparando com os valores do relatório. A análise respeita a regra de gasto, os pedidos únicos e os arredondamentos.

## Como executar

Requer Python 3.10 ou superior. Usa somente a biblioteca padrão, sem instalação de pacotes.

Clone o repositório ou extraia o ZIP. Abra um terminal na pasta do projeto e execute:

```powershell
python verificar_relatorio.py --saida resultado.json
```

Se o Python estiver disponível pelo launcher do Windows, pode usar `py` no lugar de `python`.

Para os arquivos fornecidos, o resultado esperado é:

```text
Pedidos unicos: 240; linhas: 243
Item 1: ERRADO
Item 2: CERTO
Item 3: ERRADO
Item 4: CERTO
Item 5: CERTO
Item 6: ERRADO
Item 7: ERRADO
Item 8: CERTO
Item 9: CERTO
Item 10: CERTO
BLOQUEADO: divergencias nos itens [1, 3, 6, 7].
```

Entre as linhas acima, o programa também imprime os valores informados e esperados de cada indicador. O código de saída é `0` quando todos os itens passam, `1` quando há divergências e `2` quando uma entrada é inválida ou ocorre falha de leitura/gravação. Assim, retornar `1` com o relatório original demonstra a detecção dos erros. Uma integração deve verificar esse código antes de liberar um envio.

O arquivo `resultado.json` registra os cálculos sem escala, as comparações, as duplicatas, o cliente, o período, as regras de status, a versão do verificador e os hashes SHA-256 das entradas.

## Como executar os testes

```powershell
python -m unittest -v
```

Há uma base pequena com contas manuais para testar filtros, percentuais, mediana e limites do trimestre. Outros casos verificam duplicatas conflitantes, dados inválidos, arredondamentos, valores altos legítimos e ausência de dados. Os testes de integração usam o CSV do exercício: um relatório corrigido precisa passar, e a reintrodução isolada de cada um dos quatro erros precisa ser detectada. Também são testados os códigos de saída e a substituição de um resultado antigo quando a entrada atual é inválida.

## Arquivos e origem dos dados

- `verificar_relatorio.py`: leitura, validação, cálculos, comparação e execução por terminal.
- `test_verificar_relatorio.py`: testes automatizados com `unittest`.
- `pedidos_2025.csv`: cópia sem alterações de `Exercicio-pedidos_2025.csv`, fornecido no exercício com dados sintéticos.
- `relatorio_agente.json`: transcrição manual dos números, da categoria e da afirmação de um único pedido em destaque escritos em `Exercicio-relatorio-do-agente.docx`. Este JSON foi criado para a checagem; não foi fornecido pela empresa.
- `resultado.json`: evidência de uma execução com as entradas incluídas.

Os itens 4 e 10 têm mais de um campo conferido, mas cada um continua contando como um único item do relatório. No item 10, são conferidos o total de TI, o maior pedido e a existência de um único pedido nesse valor. O programa verifica os indicadores estruturados; a leitura automática do Word, a redação final, o agendamento semanal e o envio a clientes não fazem parte desta implementação local.

## Regras e pontos para explicar na entrevista

1. `ler_pedidos` valida a estrutura e registra cópias com todos os campos idênticos. O mesmo ID com informações diferentes interrompe a análise. O arquivo original permanece intacto.
2. `STATUS_GASTO` define quais status entram no gasto. `selecionar_gasto` aplica a mesma seleção ao gasto e ao ticket. Para experimentar a regra de gasto apenas dos entregues, altere essa constante para `{"entregue"}` e execute novamente. Um teste já cobre essa mudança.
3. `calcular_indicadores` filtra o ano pela emissão, agrupa categorias e fornecedores e calcula explicitamente a mediana. A comparação entre trimestre e semestre não depende da posição das linhas no CSV.
4. `INDICADORES` registra unidade e casas decimais de cada campo. Valores monetários são calculados em reais com `Decimal` e convertidos para mil ou milhões antes da comparação. O arredondamento usa `ROUND_HALF_UP`; essa escolha não altera os resultados deste exercício.
5. `conferir_relatorio` exige todos os campos, o período correto e o contrato de unidades e precisão. Ausência de dados para um indicador é tratada como impedimento à aprovação.

Para selecionar outro ano ou trimestre, use `--ano` e `--trimestre` e forneça um JSON com o mesmo período. Por exemplo:

```powershell
python verificar_relatorio.py --csv outra_base.csv --relatorio outro_relatorio.json --ano 2026 --trimestre 2 --cliente "Cliente exemplo" --saida outro_resultado.json
```

O script não tenta adivinhar qual código o agente utilizou. Ele identifica as divergências; as explicações sobre suas causas foram fundamentadas na conferência da Parte A.

## Uso de IA

Usei o Codex para apoiar a escrita e revisão do código, dos testes e da documentação. Os cálculos iniciais da Parte A foram executados em Python e reconferidos em PowerShell. Os testes incluídos permitem reproduzir e examinar a checagem local.
