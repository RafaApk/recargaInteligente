"""Avaliação em lote de submissões com o nosso motor, com cache em disco e métricas por semana.

Cache: `RESULTADOS/sim/{ag}/{hash}.json`, `hash` = recarga.chave.chave(sub_normalizada, eventos_da_agencia).
Cada arquivo guarda a impressão digital de `kickoff/motor.py`; se o motor mudar, a entrada é refeita.
"""
import atexit
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from recarga import DADOS, KIT, RESULTADOS
from recarga.chave import chave

from kickoff import dados, medicao, motor, tempo, validar  # noqa: E402  (recarga põe o kit no sys.path)

CACHE = RESULTADOS / "sim"
SEMANA = 7 * tempo.DIA
N_SEMANAS = 4

_CENARIOS: dict = {}
_CATALOGO: dict = {}
_POOL: dict = {}


def versao_motor() -> str:
    """Impressão digital do motor (muda quando a Frente A altera o motor)."""
    if "v" not in _CATALOGO:
        _CATALOGO["v"] = hashlib.sha256((KIT / "kickoff" / "motor.py").read_bytes()).hexdigest()[:16]
    return _CATALOGO["v"]


def catalogo():
    """`DADOS/catalogo.json` (GET /catalogo pós-H4) ou None."""
    p = DADOS / "catalogo.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def cenario(ag: str):
    """Cenário da agência (cache por processo)."""
    if ag not in _CENARIOS:
        _CENARIOS[ag] = dados.carregar(DADOS, ag, catalogo())
    return _CENARIOS[ag]


def eventos_da_agencia(ag: str, eventos) -> list:
    """Mesmo filtro de simular.py: params com a agência na posição 1."""
    return [list(e) for e in eventos if len(e) > 1 and e[1] == ag]


def _preparar(ag: str, sub, eventos):
    """(resultado_inválido, None) ou (None, (sub_normalizada, eventos_ag, hash))."""
    cen = cenario(ag)
    erros = validar.validar(sub, cen)
    if erros:
        return {"agencia": ag, "hash": None, "sub": sub, "valido": False, "erros": erros}, None
    s = validar.normalizar(sub, cen)
    ev = eventos_da_agencia(ag, eventos)
    return None, (s, ev, chave(s, ev))


def _arquivo(cache: Path, ag: str, h: str) -> Path:
    return Path(cache) / ag / f"{h}.json"


def _ler_cache(cache: Path, ag: str, h: str, series: bool):
    p = _arquivo(cache, ag, h)
    if not p.exists():
        return None
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if r.get("versao_motor") != versao_motor() or (series and "series" not in r):
        return None
    return r


def _gravar_cache(cache: Path, ag: str, r: dict) -> None:
    p = _arquivo(cache, ag, r["hash"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.stem}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _simular(ag: str, s: dict, ev: list, h: str, series: bool) -> dict:
    cen = cenario(ag)
    res = motor.simular(cen, s, ev)
    dem = s["demanda_contratada_kw"] or 0.0

    def janela(ini, fim):
        m = medicao.metricas(res.retiradas, res.nao_atendidos, res.bins, ini, fim)
        m["demanda_contratada_kw"] = dem
        return m

    ini, fim = tempo.JANELA_PUBLICA
    r = {
        "agencia": ag,
        "hash": h,
        "sub": s,
        "eventos": ev,
        "valido": True,
        "erros": [],
        "violacoes": list(res.violacoes),
        "metricas": janela(ini, fim),
        "semanas": [janela(tempo.T0 + w * SEMANA, tempo.T0 + (w + 1) * SEMANA) for w in range(N_SEMANAS)],
        "versao_motor": versao_motor(),
    }
    if series:
        r["series"] = medicao.series(res.bins, res.trace, res.retiradas, res.nao_atendidos, ini, fim)
    return r


def _avaliar_preparado(ag, s, ev, h, series, cache) -> dict:
    r = _ler_cache(cache, ag, h, series)
    if r is None:
        r = _simular(ag, s, ev, h, series)
        _gravar_cache(cache, ag, r)
    if not series:
        r.pop("series", None)
    return r


def _trabalho(args) -> dict:
    """Worker do pool (função de módulo: spawn no Windows)."""
    return _avaliar_preparado(*args)


def avaliar(ag: str, sub, eventos=(), series: bool = False) -> dict:
    """Simula `sub` na janela pública: hash, sub (normalizada), valido, erros, violacoes, metricas, semanas[, series]."""
    ruim, prep = _preparar(ag, sub, eventos)
    if ruim is not None:
        return ruim
    s, ev, h = prep
    return _avaliar_preparado(ag, s, ev, h, series, CACHE)


def _pool(n: int) -> ProcessPoolExecutor:
    if n not in _POOL:
        _POOL[n] = ProcessPoolExecutor(max_workers=n)
    return _POOL[n]


@atexit.register
def _fechar_pools() -> None:
    for p in _POOL.values():
        p.shutdown(wait=False, cancel_futures=True)
    _POOL.clear()


def avaliar_lote(ag: str, subs, eventos=(), processos=None) -> list:
    """`avaliar` para cada sub, na mesma ordem. Simula só o que falta no cache, em paralelo e sem repetir hash."""
    if processos is None:
        processos = max(1, (os.cpu_count() or 2) - 1)
    saida: list = [None] * len(subs)
    por_hash: dict = {}  # hash -> resultado
    hashes: list = [None] * len(subs)
    faltam: dict = {}  # hash -> args do worker
    for i, sub in enumerate(subs):
        ruim, prep = _preparar(ag, sub, eventos)
        if ruim is not None:
            saida[i] = ruim
            continue
        s, ev, h = prep
        hashes[i] = h
        if h in por_hash or h in faltam:
            continue
        r = _ler_cache(CACHE, ag, h, False)
        if r is not None:
            por_hash[h] = r
        else:
            faltam[h] = (ag, s, ev, h, False, CACHE)
    args = list(faltam.values())
    if processos <= 1 or len(args) <= 1:
        prontos = [_trabalho(a) for a in args]
    else:
        prontos = list(_pool(processos).map(_trabalho, args, chunksize=1))
    por_hash.update(zip(faltam, prontos))
    for i, h in enumerate(hashes):
        if h is not None:
            saida[i] = dict(por_hash[h])
    return saida
