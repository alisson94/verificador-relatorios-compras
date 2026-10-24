"""Conferencia local de dez indicadores de compras, usando somente Python padrao."""

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from statistics import mean, median


VERSAO = "1.0.0"
PASTA = Path(__file__).resolve().parent
STATUS_VALIDOS = {"entregue", "em aberto", "cancelado"}
# Altere esta regra para experimentar, por exemplo, gasto apenas dos entregues.
STATUS_GASTO = {"entregue", "em aberto"}
COLUNAS = (
    "id_pedido", "data_pedido", "fornecedor", "categoria", "valor_brl",
    "prazo_entrega_dias", "status",
)


@dataclass(frozen=True)
class Pedido:
    id: str
    data: date
    fornecedor: str
    categoria: str
    valor: Decimal
    prazo: int
    status: str


@dataclass(frozen=True)
class Indicador:
    item: int
    nome: str
    unidade: str
    divisor: Decimal
    casas: int | None


# Unidade e precisao sao o contrato da checagem, nao escolhas livres do agente.
INDICADORES = {
    "total_pedidos": Indicador(1, "Quantidade de pedidos", "pedidos", Decimal(1), 0),
    "pedidos_cancelados": Indicador(2, "Pedidos cancelados", "pedidos", Decimal(1), 0),
    "gasto_total": Indicador(3, "Gasto total", "BRL_milhoes", Decimal(1000000), 2),
    "maior_categoria": Indicador(4, "Maior categoria", "texto", Decimal(1), None),
    "participacao_maior_categoria": Indicador(4, "Participacao da maior categoria", "percentual", Decimal(1), 0),
    "concentracao_top3": Indicador(5, "Concentracao dos tres maiores fornecedores", "percentual", Decimal(1), 0),
    "ticket_mediano": Indicador(6, "Ticket mediano", "BRL_mil", Decimal(1000), 1),
    "gasto_trimestre": Indicador(7, "Gasto do trimestre", "BRL_milhoes", Decimal(1000000), 2),
    "prazo_medio_entregues": Indicador(8, "Prazo medio dos entregues", "dias", Decimal(1), 0),
    "pedidos_em_aberto_pct": Indicador(9, "Pedidos em aberto", "percentual", Decimal(1), 0),
    "gasto_ti": Indicador(10, "Gasto de TI", "BRL_milhoes", Decimal(1000000), 2),
    "maior_pedido_ti": Indicador(10, "Maior pedido de TI", "BRL_mil", Decimal(1000), 0),
    "quantidade_maior_pedido_ti": Indicador(10, "Quantidade de pedidos no maior valor de TI", "pedidos", Decimal(1), 0),
}


def ler_pedidos(caminho):
    """Valida o CSV; remove somente copias com todos os campos identicos."""
    conteudo = Path(caminho).read_bytes()
    leitor = csv.DictReader(io.StringIO(conteudo.decode("utf-8-sig")))
    cabecalho = leitor.fieldnames or []
    if len(cabecalho) != len(set(cabecalho)) or set(cabecalho) != set(COLUNAS):
        raise ValueError("Cabecalho deve conter exatamente as sete colunas do enunciado.")
    originais, pedidos, duplicatas = {}, [], Counter()
    linhas = 0
    for linha in leitor:
        linhas += 1
        numero_linha = leitor.line_num
        if set(linha) != set(COLUNAS) or any(
            not isinstance(v, str) or not v.strip() for v in linha.values()
        ):
            raise ValueError(f"Linha {numero_linha}: campo vazio ou quantidade de campos invalida.")
        try:
            data = date.fromisoformat(linha["data_pedido"])
            if data.isoformat() != linha["data_pedido"]:
                raise ValueError("data deve usar YYYY-MM-DD")
            valor = Decimal(linha["valor_brl"])
            if not valor.is_finite() or valor != valor.quantize(Decimal("0.01")):
                raise ValueError("valor deve ser finito e ter no maximo duas casas decimais")
            prazo = int(linha["prazo_entrega_dias"])
            if prazo < 0:
                raise ValueError("prazo deve ser inteiro nao negativo")
            if linha["status"] not in STATUS_VALIDOS:
                raise ValueError("status desconhecido")
        except (ValueError, InvalidOperation) as erro:
            raise ValueError(f"Linha {numero_linha}: {erro}.") from erro
        identificador = linha["id_pedido"]
        if identificador in originais:
            if originais[identificador] != linha:
                raise ValueError(f"ID {identificador}: registros conflitantes; revisao necessaria.")
            duplicatas[identificador] += 1
            continue
        originais[identificador] = linha
        pedidos.append(Pedido(
            identificador, data, linha["fornecedor"], linha["categoria"],
            valor, prazo, linha["status"],
        ))
    return pedidos, {
        "linhas_csv": linhas,
        "pedidos_unicos_csv": len(pedidos),
        "copias_descartadas_por_id": dict(sorted(duplicatas.items())),
        "csv_sha256": hashlib.sha256(conteudo).hexdigest(),
    }


def selecionar_gasto(pedidos):
    return [p for p in pedidos if p.status in STATUS_GASTO]


def somar_valores(pedidos):
    return sum((p.valor for p in pedidos), Decimal(0))


def calcular_indicadores(pedidos, ano=2025, trimestre=3):
    """Todos os calculos usam pedidos unicos e data de emissao."""
    if type(ano) is not int or not 1 <= ano <= 9999:
        raise ValueError("Ano invalido.")
    if type(trimestre) is not int or trimestre not in (1, 2, 3, 4):
        raise ValueError("Trimestre deve estar entre 1 e 4.")
    periodo = [p for p in pedidos if p.data.year == ano]
    if not periodo:
        raise ValueError(f"Nenhum pedido no ano {ano}.")
    gasto = selecionar_gasto(periodo)
    entregues = [p for p in periodo if p.status == "entregue"]
    total = somar_valores(gasto)
    categorias, fornecedores = defaultdict(Decimal), defaultdict(Decimal)
    for p in gasto:
        categorias[p.categoria] += p.valor
        fornecedores[p.fornecedor] += p.valor
    # Empates sao ordenados por nome para tornar o resultado reproduzivel.
    ranking_categorias = sorted(categorias, key=lambda k: (-categorias[k], k))
    ranking_fornecedores = sorted(fornecedores, key=lambda k: (-fornecedores[k], k))
    maior = ranking_categorias[0] if ranking_categorias else None
    ti = [p for p in gasto if p.categoria == "TI"]
    maior_ti = max((p.valor for p in ti), default=None)
    valores = {
        "total_pedidos": Decimal(len(periodo)),
        "pedidos_cancelados": Decimal(sum(p.status == "cancelado" for p in periodo)),
        "gasto_total": total,
        "maior_categoria": maior,
        "participacao_maior_categoria": categorias[maior] / total * 100 if total else None,
        "concentracao_top3": sum((fornecedores[k] for k in ranking_fornecedores[:3]), Decimal(0)) / total * 100 if total else None,
        "ticket_mediano": median([p.valor for p in gasto]) if gasto else None,
        "gasto_trimestre": somar_valores([p for p in gasto if (p.data.month - 1) // 3 + 1 == trimestre]),
        "prazo_medio_entregues": mean([Decimal(p.prazo) for p in entregues]) if entregues else None,
        "pedidos_em_aberto_pct": Decimal(sum(p.status == "em aberto" for p in periodo)) / len(periodo) * 100,
        "gasto_ti": somar_valores(ti),
        "maior_pedido_ti": maior_ti,
        "quantidade_maior_pedido_ti": Decimal(sum(p.valor == maior_ti for p in ti)) if ti else None,
    }
    apoio = {
        "pedidos_no_ano": len(periodo), "pedidos_no_gasto": len(gasto),
        "status_no_ano": dict(Counter(p.status for p in periodo)),
        "gasto_por_categoria": dict(categorias),
        "top3_fornecedores": {k: fornecedores[k] for k in ranking_fornecedores[:3]},
    }
    return valores, apoio


def sem_chaves_repetidas(pares):
    resultado = {}
    for chave, valor in pares:
        if chave in resultado:
            raise ValueError(f"JSON com chave repetida: {chave}.")
        resultado[chave] = valor
    return resultado


def arredondar(valor, casas):
    return valor.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def conferir_indicador(chave, informado, calculado):
    regra = INDICADORES[chave]
    if not isinstance(informado, dict) or set(informado) != {"valor", "unidade", "casas_decimais"}:
        raise ValueError(f"{chave}: formato do indicador invalido.")
    if informado["unidade"] != regra.unidade or (
        informado["casas_decimais"] != regra.casas
        or type(informado["casas_decimais"]) is not type(regra.casas)
    ):
        raise ValueError(f"{chave}: unidade ou precisao diferente do contrato.")
    valor = informado["valor"]
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{chave}: valor deve ser uma string preenchida.")
    if regra.casas is None:
        esperado = calculado
        certo = calculado is not None and valor == calculado
    else:
        try:
            numero = Decimal(valor)
            if not numero.is_finite() or numero != arredondar(numero, regra.casas):
                raise ValueError("valor nao finito ou precisao excedida")
        except (InvalidOperation, ValueError) as erro:
            raise ValueError(f"{chave}: numero invalido ({erro}).") from erro
        esperado = arredondar(calculado / regra.divisor, regra.casas) if calculado is not None else None
        certo = esperado is not None and numero == esperado
    return {
        "indicador": chave, "informado": valor, "esperado": esperado,
        "valor_calculado_sem_escala": calculado, "unidade": regra.unidade,
        "casas_decimais": regra.casas, "correto": certo,
        "motivo": "comparacao na precisao do relatorio" if calculado is not None else "dados insuficientes para este indicador",
    }


def conferir_relatorio(valores, relatorio, ano=2025, trimestre=3):
    if not isinstance(relatorio, dict) or set(relatorio) != {"ano", "trimestre", "indicadores"}:
        raise ValueError("Estrutura do relatorio JSON invalida.")
    if type(relatorio["ano"]) is not int or type(relatorio["trimestre"]) is not int or (
        relatorio["ano"], relatorio["trimestre"]
    ) != (ano, trimestre):
        raise ValueError("Periodo do relatorio diferente do periodo solicitado.")
    dados = relatorio["indicadores"]
    if not isinstance(dados, dict) or set(dados) != set(INDICADORES):
        raise ValueError("Relatorio com indicadores ausentes ou inesperados.")
    grupos = defaultdict(list)
    for chave, regra in INDICADORES.items():
        grupos[regra.item].append(conferir_indicador(chave, dados[chave], valores[chave]))
    return [
        {"item": item, "correto": all(c["correto"] for c in campos), "campos": campos}
        for item, campos in sorted(grupos.items())
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=PASTA / "pedidos_2025.csv")
    parser.add_argument("--relatorio", type=Path, default=PASTA / "relatorio_agente.json")
    parser.add_argument("--ano", type=int, default=2025)
    parser.add_argument("--trimestre", type=int, default=3)
    parser.add_argument("--cliente", default="Distribuidora ficticia")
    parser.add_argument("--saida", type=Path, help="Salvar evidencia em JSON UTF-8.")
    args = parser.parse_args()
    if args.saida and args.saida.resolve() in {args.csv.resolve(), args.relatorio.resolve()}:
        parser.error("A saida nao pode sobrescrever uma das entradas.")
    resultado = {
        "versao_verificador": VERSAO,
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "cliente": args.cliente, "ano": args.ano, "trimestre": args.trimestre,
        "status_incluidos_no_gasto": sorted(STATUS_GASTO),
        "aprovado": False,
    }
    try:
        pedidos, qualidade = ler_pedidos(args.csv)
        conteudo_relatorio = args.relatorio.read_bytes()
        relatorio = json.loads(conteudo_relatorio.decode("utf-8-sig"), object_pairs_hook=sem_chaves_repetidas)
        valores, apoio = calcular_indicadores(pedidos, args.ano, args.trimestre)
        itens = conferir_relatorio(valores, relatorio, args.ano, args.trimestre)
        errados = [i["item"] for i in itens if not i["correto"]]
        resultado.update({
            "qualidade": qualidade, "apoio": apoio, "itens": itens,
            "relatorio_sha256": hashlib.sha256(conteudo_relatorio).hexdigest(),
            "itens_errados": errados, "aprovado": not errados,
        })
        print(f"Pedidos unicos: {qualidade['pedidos_unicos_csv']}; linhas: {qualidade['linhas_csv']}")
        for item in itens:
            print(f"Item {item['item']}: {'CERTO' if item['correto'] else 'ERRADO'}")
            for campo in item["campos"]:
                print(f"  {campo['indicador']}: informado={campo['informado']}; esperado={campo['esperado']} {campo['unidade']}")
        print("APROVADO" if not errados else f"BLOQUEADO: divergencias nos itens {errados}.")
        codigo = 1 if errados else 0
    except (OSError, UnicodeError, ValueError, csv.Error) as erro:
        resultado["erro_validacao"] = str(erro)
        print(f"BLOQUEADO: {erro}", file=sys.stderr)
        codigo = 2
    if args.saida:
        try:
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        except OSError as erro:
            print(f"Falha ao salvar a evidencia: {erro}", file=sys.stderr)
            return 2
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
