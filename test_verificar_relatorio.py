"""Testes com contas manuais e regressao do CSV do exercicio."""

import copy
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import verificar_relatorio as v


def linha(id="A", data="2025-06-30", fornecedor="A", categoria="Manutenção",
          valor="100.00", prazo="10", status="entregue"):
    return dict(zip(v.COLUNAS, [id, data, fornecedor, categoria, valor, prazo, status]))


def base_manual():
    # Em 2025: 5 pedidos, 4 no gasto, valores 100/200/300/600.
    # Gasto 1200; mediana 250; trimestre 500; entregues com prazos 10/30/50.
    return [
        linha(),
        linha("B", "2025-07-01", "B", "TI", "200.00", "20", "em aberto"),
        linha("C", "2025-09-30", "C", "Manutenção", "300.00", "30"),
        linha("D", "2025-10-01", "D", "TI", "400.00", "40", "cancelado"),
        linha("E", "2025-12-31", "D", "TI", "600.00", "50"),
        linha("F", "2024-07-01", "X", "TI", "999.00", "99"),
    ]


class VerificadorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".teste-", dir=v.PASTA)
        self.pasta = Path(self.tmp.name).resolve()
        # A limpeza recursiva fica restrita a esta pasta temporaria do projeto.
        self.assertEqual(self.pasta.parent, v.PASTA)
        self.addCleanup(self.tmp.cleanup)

    def carregar(self, linhas, colunas=v.COLUNAS):
        caminho = self.pasta / "base.csv"
        with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
            writer = csv.DictWriter(arquivo, fieldnames=colunas)
            writer.writeheader()
            writer.writerows(linhas)
        return v.ler_pedidos(caminho)

    def relatorio_original(self):
        return json.loads((v.PASTA / "relatorio_agente.json").read_text(encoding="utf-8"))

    def relatorio_corrigido(self):
        # Valores conhecidos da conferencia independente da Parte A.
        relatorio = self.relatorio_original()
        for chave, valor in {
            "total_pedidos": "240", "gasto_total": "7.80",
            "ticket_mediano": "25.6", "gasto_trimestre": "2.11",
        }.items():
            relatorio["indicadores"][chave]["valor"] = valor
        return relatorio

    def test_contas_manuais_e_limites_do_trimestre(self):
        pedidos, _ = self.carregar(base_manual())
        numeros, apoio = v.calcular_indicadores(pedidos)
        esperado = {
            "total_pedidos": Decimal(5), "pedidos_cancelados": Decimal(1),
            "gasto_total": Decimal(1200), "maior_categoria": "TI",
            "ticket_mediano": Decimal(250), "gasto_trimestre": Decimal(500),
            "prazo_medio_entregues": Decimal(30), "pedidos_em_aberto_pct": Decimal(20),
            "gasto_ti": Decimal(800), "maior_pedido_ti": Decimal(600),
            "quantidade_maior_pedido_ti": Decimal(1),
        }
        for chave, valor in esperado.items():
            with self.subTest(indicador=chave):
                self.assertEqual(numeros[chave], valor)
        self.assertEqual(v.arredondar(numeros["participacao_maior_categoria"], 2), Decimal("66.67"))
        self.assertEqual(v.arredondar(numeros["concentracao_top3"], 2), Decimal("91.67"))
        self.assertEqual(apoio["pedidos_no_gasto"], 4)

    def test_duplicata_identica_nao_altera_contas(self):
        linhas = base_manual()
        pedidos, qualidade = self.carregar(linhas + [dict(linhas[1])])
        self.assertEqual(qualidade["linhas_csv"], 7)
        self.assertEqual(qualidade["pedidos_unicos_csv"], 6)
        self.assertEqual(qualidade["copias_descartadas_por_id"], {"B": 1})
        self.assertEqual(v.calcular_indicadores(pedidos)[0]["gasto_total"], Decimal(1200))

    def test_duplicata_conflitante_bloqueia(self):
        with self.assertRaisesRegex(ValueError, "conflitantes"):
            self.carregar([linha(), linha(valor="101.00")])

    def test_dados_invalidos_bloqueiam(self):
        casos = [
            {"status": "pago"}, {"data_pedido": "2025-02-30"},
            {"data_pedido": "20250701"}, {"valor_brl": "NaN"},
            {"valor_brl": "Infinity"}, {"valor_brl": "100.001"},
            {"prazo_entrega_dias": "-1"}, {"prazo_entrega_dias": "1.5"},
            {"fornecedor": ""},
        ]
        for alteracao in casos:
            with self.subTest(alteracao=alteracao):
                registro = linha()
                registro.update(alteracao)
                with self.assertRaises(ValueError):
                    self.carregar([registro])

    def test_coluna_ausente_bloqueia(self):
        registro = linha()
        del registro["status"]
        with self.assertRaisesRegex(ValueError, "Cabecalho"):
            self.carregar([registro], v.COLUNAS[:-1])

    def test_medianas_par_e_impar(self):
        pedidos, _ = self.carregar(base_manual())
        self.assertEqual(v.calcular_indicadores(pedidos)[0]["ticket_mediano"], Decimal(250))
        pedidos.append(v.Pedido("G", date(2025, 8, 1), "G", "TI", Decimal(1000), 15, "entregue"))
        self.assertEqual(v.calcular_indicadores(pedidos)[0]["ticket_mediano"], Decimal(300))

    def test_alterar_regra_de_gasto_tambem_altera_ticket(self):
        pedidos, _ = self.carregar(base_manual())
        with patch.object(v, "STATUS_GASTO", {"entregue"}):
            numeros, _ = v.calcular_indicadores(pedidos)
        self.assertEqual(numeros["gasto_total"], Decimal(1000))
        self.assertEqual(numeros["ticket_mediano"], Decimal(300))
        self.assertEqual(numeros["pedidos_em_aberto_pct"], Decimal(20))

    def test_pedido_alto_legitimo_permanece_no_gasto(self):
        registros = base_manual() + [linha("G", "2025-08-01", "G", "TI", "612000.00")]
        pedidos, _ = self.carregar(registros)
        numeros, _ = v.calcular_indicadores(pedidos)
        self.assertEqual(numeros["gasto_total"], Decimal(613200))
        self.assertEqual(numeros["maior_pedido_ti"], Decimal(612000))

    def test_sem_entregues_nao_passa_com_prazo_zero(self):
        pedidos, _ = self.carregar([linha(categoria="TI", status="em aberto")])
        numeros, _ = v.calcular_indicadores(pedidos)
        self.assertIsNone(numeros["prazo_medio_entregues"])
        informado = {"valor": "0", "unidade": "dias", "casas_decimais": 0}
        self.assertFalse(v.conferir_indicador("prazo_medio_entregues", informado, None)["correto"])

    def test_afirmacao_de_pedido_unico_de_ti_e_conferida(self):
        pedidos, _ = self.carregar([
            linha("A", categoria="TI", valor="612000.00"),
            linha("B", categoria="TI", valor="612000.00"),
        ])
        numeros, _ = v.calcular_indicadores(pedidos)
        self.assertEqual(numeros["quantidade_maior_pedido_ti"], Decimal(2))
        dado = {"valor": "1", "unidade": "pedidos", "casas_decimais": 0}
        self.assertFalse(v.conferir_indicador("quantidade_maior_pedido_ti", dado, numeros["quantidade_maior_pedido_ti"])["correto"])

    def test_sem_pedidos_no_ano_bloqueia(self):
        pedidos, _ = self.carregar([linha(data="2024-07-01")])
        with self.assertRaisesRegex(ValueError, "Nenhum pedido"):
            v.calcular_indicadores(pedidos)

    def test_arredondamento_na_unidade_correta(self):
        casos = [
            ("participacao_maior_categoria", "37", Decimal("37.1"), True),
            ("participacao_maior_categoria", "37", Decimal("37.5"), False),
            ("gasto_total", "7.80", Decimal("7796058.67"), True),
            ("ticket_mediano", "25.6", Decimal("25628.64"), True),
        ]
        for chave, valor, calculado, correto in casos:
            with self.subTest(chave=chave, calculado=calculado):
                regra = v.INDICADORES[chave]
                dado = {"valor": valor, "unidade": regra.unidade, "casas_decimais": regra.casas}
                self.assertEqual(v.conferir_indicador(chave, dado, calculado)["correto"], correto)

    def test_contrato_do_relatorio_nao_pode_mudar_a_escala(self):
        for alteracao in [{"unidade": "BRL"}, {"casas_decimais": 0}, {"valor": "NaN"}]:
            with self.subTest(alteracao=alteracao):
                dado = {"valor": "7.80", "unidade": "BRL_milhoes", "casas_decimais": 2}
                dado.update(alteracao)
                with self.assertRaises(ValueError):
                    v.conferir_indicador("gasto_total", dado, Decimal("7796058.67"))

    def test_campos_ausentes_ou_periodo_incorreto_bloqueiam(self):
        pedidos, _ = v.ler_pedidos(v.PASTA / "pedidos_2025.csv")
        numeros, _ = v.calcular_indicadores(pedidos)
        relatorio = self.relatorio_original()
        del relatorio["indicadores"]["ticket_mediano"]
        with self.assertRaisesRegex(ValueError, "ausentes"):
            v.conferir_relatorio(numeros, relatorio)
        relatorio = self.relatorio_original()
        relatorio["trimestre"] = 4
        with self.assertRaisesRegex(ValueError, "Periodo"):
            v.conferir_relatorio(numeros, relatorio)

    def test_json_com_chave_repetida_bloqueia(self):
        with self.assertRaisesRegex(ValueError, "repetida"):
            json.loads('{"ano":2025,"ano":2024}', object_pairs_hook=v.sem_chaves_repetidas)

    def test_base_original_reproduz_a_parte_a(self):
        pedidos, qualidade = v.ler_pedidos(v.PASTA / "pedidos_2025.csv")
        numeros, _ = v.calcular_indicadores(pedidos)
        self.assertEqual(qualidade["linhas_csv"], 243)
        self.assertEqual(len(pedidos), 240)
        self.assertEqual(qualidade["copias_descartadas_por_id"], {"PC-0013": 1, "PC-0100": 1, "PC-0181": 1})
        self.assertEqual(numeros["gasto_total"], Decimal("7796058.67"))
        self.assertEqual(numeros["ticket_mediano"], Decimal("25628.64"))
        self.assertEqual(numeros["gasto_trimestre"], Decimal("2106942.81"))
        itens = v.conferir_relatorio(numeros, self.relatorio_original())
        self.assertEqual([i["item"] for i in itens if not i["correto"]], [1, 3, 6, 7])

    def test_relatorio_corrigido_passa_e_cada_erro_e_detectado(self):
        pedidos, _ = v.ler_pedidos(v.PASTA / "pedidos_2025.csv")
        numeros, _ = v.calcular_indicadores(pedidos)
        correto = self.relatorio_corrigido()
        self.assertTrue(all(i["correto"] for i in v.conferir_relatorio(numeros, correto)))
        erros = [("total_pedidos", "243", 1), ("gasto_total", "8.38", 3),
                 ("ticket_mediano", "34.8", 6), ("gasto_trimestre", "4.15", 7)]
        for chave, valor, item in erros:
            with self.subTest(erro=chave):
                alterado = copy.deepcopy(correto)
                alterado["indicadores"][chave]["valor"] = valor
                itens = v.conferir_relatorio(numeros, alterado)
                self.assertEqual([i["item"] for i in itens if not i["correto"]], [item])

    def test_cli_retorna_1_para_divergencia_e_0_para_correto(self):
        for relatorio, esperado in [(self.relatorio_original(), 1), (self.relatorio_corrigido(), 0)]:
            with self.subTest(codigo=esperado):
                entrada, saida = self.pasta / "relatorio.json", self.pasta / "resultado.json"
                entrada.write_text(json.dumps(relatorio), encoding="utf-8")
                processo = subprocess.run([
                    sys.executable, str(v.PASTA / "verificar_relatorio.py"),
                    "--relatorio", str(entrada), "--saida", str(saida),
                ], capture_output=True)
                self.assertEqual(processo.returncode, esperado, processo.stderr)
                resultado = json.loads(saida.read_text(encoding="utf-8"))
                self.assertEqual(resultado["aprovado"], esperado == 0)

    def test_cli_invalido_retorna_2_e_substitui_resultado_anterior(self):
        entrada, saida = self.pasta / "invalido.json", self.pasta / "resultado.json"
        entrada.write_text('{"ano": 2025}', encoding="utf-8")
        saida.write_text('{"aprovado": true}', encoding="utf-8")
        processo = subprocess.run([
            sys.executable, str(v.PASTA / "verificar_relatorio.py"),
            "--relatorio", str(entrada), "--saida", str(saida),
        ], capture_output=True)
        self.assertEqual(processo.returncode, 2)
        resultado = json.loads(saida.read_text(encoding="utf-8"))
        self.assertFalse(resultado["aprovado"])
        self.assertIn("erro_validacao", resultado)


if __name__ == "__main__":
    unittest.main()
