"""Funções objetivo do otimizador: nota (pesos exatos ou estimados) e ordem lexicográfica."""
from dataclasses import dataclass, field

import recarga  # noqa: F401  (põe o kit no sys.path)
from kickoff import nota as _nota

ITENS_OPERACAO = ("certo", "upgrade", "nao_atendido", "demanda_contratada", "energia_ponta_kwh")
METRICA = {r: k for r, k in _nota.ITENS}  # item da nota -> chave em `metricas`


@dataclass
class Pesos:
    """Pesos com sinal (como em catalogo["pesos"][ag]) e custo de obra em pontos com sinal por unidade."""
    w: dict
    k_carregador: dict = field(default_factory=dict)
    k_entrada: dict = field(default_factory=dict)


def nota(metricas: dict, sub_norm: dict, entrada_existente: str, p: Pesos) -> float:
    """Nota da janela de `metricas`; obra e demanda entram inteiras. Entrada existente custa 0."""
    total = sum(p.w.get(i, 0.0) * metricas[METRICA[i]] for i in ITENS_OPERACAO)
    total += sum(n * p.k_carregador.get(k, 0.0) for k, n in sub_norm["carregadores"].items())
    e = sub_norm["entrada"]
    if e != entrada_existente:
        total += p.k_entrada.get(e, 0.0)
    return total


def pesos_do_catalogo(cat: dict, ag: str) -> Pesos:
    """Pesos exatos de GET /catalogo (pós-H4): k = peso_infraestrutura × custo."""
    pa = cat["pesos"][ag]
    pinf = pa["infraestrutura"]
    return Pesos(
        w={i: float(pa[i]) for i in ITENS_OPERACAO},
        k_carregador={c["id"]: pinf * c["custo"] for c in cat.get("carregadores", ()) if c.get("custo") is not None},
        k_entrada={e["id"]: pinf * e["custo"] for e in cat.get("entradas", ()) if e.get("custo") is not None},
    )


def tem_pesos(cat, ag: str) -> bool:
    """O catálogo traz pesos da agência e custo de carregadores e entradas? (mesmo critério de simular.py)"""
    return bool(cat and cat.get("pesos", {}).get(ag)
                and all("custo" in c for c in tuple(cat.get("carregadores", ())) + tuple(cat.get("entradas", ()))))


def kw_instalado(sub_norm: dict, cen) -> float:
    return float(sum(n * cen.carregadores[k].potencia_kw for k, n in sub_norm["carregadores"].items()))


def chave_lexicografica(metricas: dict, sub_norm: dict, cen) -> tuple:
    """(atendimento_pct, certos, -kW instalado): maior é melhor."""
    return (metricas["atendimento_pct"], metricas["certos"], -kw_instalado(sub_norm, cen))
