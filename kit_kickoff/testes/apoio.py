"""Apoio aos testes do motor: cenários pequenos montados à mão sobre o catálogo de Bangkok.

Os testes que usam curvas reais devem usar `@unittest.skipUnless(apoio.TEM_DADOS, ...)`.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from kickoff import dados, tempo, validar  # noqa: E402
from kickoff.modelo import Agencia, Cenario, Contrato, VeiculoT0  # noqa: E402
from kickoff.motor import Motor  # noqa: E402

T0 = tempo.T0
DIA = tempo.DIA
TEM_DADOS = (RAIZ / "dados" / "Bangkok").is_dir()
SEM_DADOS = "dados/Bangkok ausentes"

_BASE = None


def base() -> Cenario:
    """Cenário real de Bangkok (cache em módulo): fonte dos modelos, carregadores, entradas e categorias."""
    global _BASE
    if _BASE is None:
        _BASE = dados.carregar(RAIZ / "dados", "Bangkok")
    return _BASE


def veiculo(id, modelo, situacao="estoque_a_carregar", soc=50.0, devolucao_t=None, soc_devolucao=None) -> VeiculoT0:
    """Veículo em T0. Em contrato, o SOC de devolução vale `soc_devolucao` (ou `soc`, se omitido)."""
    m = base().modelos[modelo]
    if situacao == "em_contrato":
        soc_devolucao = soc if soc_devolucao is None else soc_devolucao
        soc = soc_devolucao
    return VeiculoT0(id, modelo, m.categoria, m.rank, situacao, soc, devolucao_t, soc_devolucao)


def contrato(id, categoria, retirada_t, devolucao_t=None, km_devolucao=None) -> Contrato:
    return Contrato(id, categoria, base().categorias[categoria], retirada_t, devolucao_t, 0.0, km_devolucao)


def cenario(veiculos, contratos=(), vagas=6, horario=None, existente="b3_45") -> Cenario:
    """Agência 'Teste'. `horario=None` = aberta 24 h todos os dias."""
    b = base()
    ag = Agencia("Teste", vagas, len(veiculos), list(horario) if horario is not None else [(0, 1440)] * 7, existente)
    return Cenario(ag, b.modelos, list(veiculos), sorted(contratos, key=lambda c: (c.retirada_t, c.id)),
                   b.carregadores, b.entradas, b.categorias)


def motor(cen, carregadores, entrada=None, demanda=None, politica=None, eventos=()) -> Motor:
    """Monta, valida (AssertionError se inválida) e normaliza a submissão; devolve o Motor sem rodar."""
    sub = {"agencia": cen.agencia.nome, "carregadores": dict(carregadores),
           "entrada": entrada or cen.agencia.entrada_existente}
    if demanda is not None:
        sub["demanda_contratada_kw"] = demanda
    if politica is not None:
        sub["politica"] = dict(politica)
    erros = validar.validar(sub, cen)
    if erros:
        raise AssertionError(f"submissão inválida: {erros}")
    return Motor(cen, validar.normalizar(sub, cen), eventos)


def fim_plug(res, a_partir=T0):
    """Primeiro `t` do trace, depois de `a_partir`, em que o número de plugados cai (None se nunca)."""
    for (_, n0, _), (t, n1, _) in zip(res.trace, res.trace[1:]):
        if t > a_partir and n1 < n0:
            return t
    return None
