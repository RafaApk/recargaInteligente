"""Cliente do juiz com cache, ledger e travas de segurança.

Tudo que gasta m7Coins passa por aqui: valida localmente, exige `confirmar=True`, respeita a
reserva de saldo, evita cobrar duas vezes o mesmo teste (cache por hash) e espera cooldown/rate limit.
Arquivos gerados em `raiz` (padrão `resultados/`): status.json, ledger.jsonl, finais.jsonl, juiz/<ag>/<hash>_<detalhe>.json.
"""
import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from recarga import DADOS, RAIZ, RESULTADOS
from recarga.chave import chave  # noqa: F401  (reexportada: hash de cache das submissões)

from kickoff import validar
from kickoff.api import Cliente, ErroApi
from kickoff.dados import carregar

try:  # construído por outra frente; opcional aqui
    from recarga import lote
except ImportError:
    lote = None

DETALHES = ("placar", "completo")
TAXA_PLACAR = 20
TAXA_COMPLETO = 50
TAXA_COMPLETO_APOS_PLACAR = 30
TAXA_REENVIO_BASE = 80
MAX_TENTATIVAS = 8
ESPERA_RATE_LIMIT = 15.0
IDADE_STATUS_S = 30.0
BANGKOK = "Bangkok"


class Recusado(Exception):
    """Trava local: a chamada nem chegou à rede."""


def carregar_env(path: Path = RAIZ / ".env") -> None:
    """Popula os.environ com as linhas CHAVE=VALOR do arquivo, sem sobrescrever o que já existe."""
    path = Path(path)
    if not path.is_file():
        return
    for linha in path.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        if linha.startswith("export "):
            linha = linha[len("export "):].lstrip()
        k, _, v = linha.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k:
            os.environ.setdefault(k, v)


class Limitador:
    """Janela deslizante de 60 s: no máximo `max_por_min` chamadas (o juiz aceita 20)."""

    def __init__(self, max_por_min=18, relogio=time.monotonic, dormir=time.sleep):
        self.max_por_min, self.relogio, self.dormir = max_por_min, relogio, dormir
        self._marcas: deque = deque()

    def _podar(self, agora: float) -> None:
        while self._marcas and agora - self._marcas[0] >= 60:
            self._marcas.popleft()

    def esperar(self) -> None:
        agora = self.relogio()
        self._podar(agora)
        if len(self._marcas) >= self.max_por_min:
            self.dormir(max(0.0, 60 - (agora - self._marcas[0])) + 0.05)
            agora = self.relogio()
            self._podar(agora)
        self._marcas.append(agora)


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _ler_iso(texto: str) -> datetime:
    s = texto.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _eventos_de(status: dict, ag: str) -> list:
    return [list(e["params"]) for e in (status or {}).get("eventos_ativos", ()) if e.get("agencia") == ag]


def _linhas_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class Juiz:
    def __init__(self, cliente=None, raiz=RESULTADOS, dados=DADOS, reserva=300, teto_por_agencia=None,
                 autor=os.environ.get("USERNAME", "?"), limitador=None, dormir=time.sleep):
        self.cliente = cliente if cliente is not None else Cliente()
        self.raiz, self.dados = Path(raiz), Path(dados)
        self.reserva = reserva
        self.teto_por_agencia = dict(teto_por_agencia or {})
        self.autor = autor
        self.dormir = dormir
        self.limitador = limitador if limitador is not None else Limitador(dormir=dormir)
        self._status = None
        self._status_t = None
        self._cenarios: dict = {}

    # ---- chamadas à rede -------------------------------------------------

    def _espera(self, e: ErroApi) -> float:
        retry = e.corpo.get("retry_em") if isinstance(e.corpo, dict) else None
        if e.codigo == "cooldown" and retry:
            try:
                return max(0.0, (_ler_iso(retry) - _agora_utc()).total_seconds())
            except ValueError:
                pass
        return ESPERA_RATE_LIMIT

    def _chamar(self, fn, *args):
        """Chama o cliente respeitando o limitador; em 429 cooldown/rate_limit espera e repete."""
        for tentativa in range(MAX_TENTATIVAS):
            self.limitador.esperar()
            try:
                return fn(*args)
            except ErroApi as e:
                if e.status != 429 or e.codigo not in ("cooldown", "rate_limit") or tentativa == MAX_TENTATIVAS - 1:
                    raise
                espera = self._espera(e)
                if tentativa > 0:
                    espera = max(espera, 1.0)
                print(f"[juiz] {e.codigo}: aguardando {espera:.0f}s", file=sys.stderr)
                self.dormir(espera)

    # ---- rotas simples ---------------------------------------------------

    def status(self) -> dict:
        st = self._chamar(self.cliente.status)
        self._status, self._status_t = st, time.monotonic()
        self.raiz.mkdir(parents=True, exist_ok=True)
        tmp = self.raiz / "status.json.tmp"
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.raiz / "status.json")
        return st

    def _status_atual(self, max_idade: float) -> dict:
        if self._status is None or self._status_t is None or time.monotonic() - self._status_t > max_idade:
            return self.status()
        return self._status

    def catalogo(self) -> dict:
        return self._chamar(self.cliente.catalogo)

    def placar(self) -> dict:
        return self._chamar(self.cliente._json, "GET", "/placar")

    def kit(self, ag: str) -> Path:
        return self._chamar(self.cliente.baixar_kit, ag, self.dados)

    def eventos(self, ag: str) -> list:
        """Params dos eventos ativos da agência, do último status salvo em disco."""
        p = self.raiz / "status.json"
        if not p.is_file():
            return []
        return _eventos_de(json.loads(p.read_text(encoding="utf-8")), ag)

    # ---- validação local -------------------------------------------------

    def _cenario(self, ag: str):
        if ag not in self._cenarios:
            try:
                self._cenarios[ag] = carregar(self.dados, ag)
            except SystemExit as e:
                raise Recusado(f"sem dados locais de {ag}: {e}") from None
        return self._cenarios[ag]

    def _validar(self, ag: str, sub: dict):
        """Devolve (sub com `agencia`, sub normalizada) ou levanta Recusado."""
        if not isinstance(sub, dict):
            raise Recusado("submissão deve ser um objeto")
        if sub.get("agencia", ag) != ag:
            raise Recusado(f"agencia do corpo ({sub.get('agencia')!r}) diverge da rota ({ag!r})")
        sub = {**sub, "agencia": ag}
        cen = self._cenario(ag)
        erros = validar.validar(sub, cen)
        if erros:
            raise Recusado("submissão inválida: " + "; ".join(erros))
        return sub, validar.normalizar(sub, cen)

    # ---- ledger e cache --------------------------------------------------

    def _anexar(self, nome: str, linha: dict) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        with open(self.raiz / nome, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")

    def _registrar_cobranca(self, rota: str, ag: str, h: str, resp: dict) -> None:
        taxa = resp.get("taxa") or 0
        if taxa > 0:
            self._anexar("ledger.jsonl", {"t": _iso(_agora_utc()), "rota": rota, "agencia": ag, "hash": h,
                                          "taxa": taxa, "saldo": resp.get("saldo"), "autor": self.autor})
        if self._status is not None and resp.get("saldo") is not None:
            self._status = {**self._status, "saldo": resp["saldo"]}

    def _arquivo_cache(self, ag: str, h: str, detalhe: str) -> Path:
        return self.raiz / "juiz" / ag / f"{h}_{detalhe}.json"

    def _cache_ler(self, ag: str, h: str, detalhe: str):
        # um teste completo já pago serve também para o placar
        for d in ((detalhe, "completo") if detalhe == "placar" else (detalhe,)):
            p = self._arquivo_cache(ag, h, d)
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _gasto_testes(self, ag: str) -> float:
        return sum(l.get("taxa", 0) for l in _linhas_jsonl(self.raiz / "ledger.jsonl")
                   if l.get("agencia") == ag and l.get("rota") == "teste")

    def _checar_saldo(self, ag: str, taxa: float, rota: str) -> None:
        saldo = self._status["saldo"]
        if saldo - taxa < self.reserva:
            raise Recusado(f"reserva: saldo {saldo} - taxa {taxa} ficaria abaixo da reserva mínima {self.reserva}")
        teto = self.teto_por_agencia.get(ag)
        if rota == "teste" and teto is not None and self._gasto_testes(ag) + taxa > teto:
            raise Recusado(f"teto de gasto em testes de {ag} ({teto}) seria ultrapassado")

    # ---- teste e final ---------------------------------------------------

    def _hash(self, ag: str, norm: dict, max_idade: float):
        ev = _eventos_de(self._status_atual(max_idade), ag)
        return chave(norm, ev), ev

    def teste(self, ag: str, sub: dict, detalhe: str = "placar", confirmar: bool = False) -> dict:
        if detalhe not in DETALHES:
            raise Recusado(f"detalhe inválido: {detalhe!r}")
        sub, norm = self._validar(ag, sub)
        h, _ = self._hash(ag, norm, IDADE_STATUS_S)
        hit = self._cache_ler(ag, h, detalhe)
        if hit is not None:
            return hit
        pontuada = ag != BANGKOK
        if pontuada:
            if not confirmar:
                raise Recusado(f"teste pago em {ag} exige confirmar=True")
            h, _ = self._hash(ag, norm, 0)  # saldo e eventos frescos antes de gastar
            hit = self._cache_ler(ag, h, detalhe)
            if hit is not None:
                return hit
            if detalhe == "placar":
                taxa = TAXA_PLACAR
            elif self._arquivo_cache(ag, h, "placar").is_file():
                taxa = TAXA_COMPLETO_APOS_PLACAR
            else:
                taxa = TAXA_COMPLETO
            self._checar_saldo(ag, taxa, "teste")
        resp = self._chamar(self.cliente.teste, ag, sub, detalhe)
        p = self._arquivo_cache(ag, h, detalhe)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
        self._registrar_cobranca("teste", ag, h, resp)
        return resp

    def _envios_anteriores(self, ag: str) -> int:
        local = sum(1 for l in _linhas_jsonl(self.raiz / "finais.jsonl") if l.get("agencia") == ag)
        info = ((self._status or {}).get("agencias") or {}).get(ag) or {}
        envios = info.get("envios")
        if isinstance(envios, list):
            envios = len(envios)
        return max(local, envios if isinstance(envios, int) and not isinstance(envios, bool) else 0)

    def final(self, ag: str, sub: dict, confirmar: bool = False) -> dict:
        if ag == BANGKOK:
            raise Recusado("Bangkok não pontua: não aceita envio final")
        if not confirmar:
            raise Recusado(f"envio final em {ag} exige confirmar=True")
        sub, norm = self._validar(ag, sub)
        self.status()
        h, ev = self._hash(ag, norm, IDADE_STATUS_S)
        h_sub = chave(norm, [])
        vigente = next((l for l in reversed(_linhas_jsonl(self.raiz / "finais.jsonl"))
                        if l.get("agencia") == ag), None)
        if vigente and (vigente.get("hash") in (h, h_sub) or vigente.get("hash_sub") == h_sub):
            raise Recusado(f"envio final idêntico ao vigente de {ag}")
        if lote is not None:
            r = lote.avaliar(ag, sub, ev)
            if not r.get("valido", True) or r.get("violacoes"):
                raise Recusado(f"violações no nosso motor: {r.get('violacoes') or r.get('erros')}")
        n = self._envios_anteriores(ag)
        taxa = 0 if n == 0 else TAXA_REENVIO_BASE * 2 ** (n - 1)
        if taxa > 0:
            self._checar_saldo(ag, taxa, "final")
        resp = self._chamar(self.cliente._json, "POST", f"/final/{ag}", sub)
        if resp.get("aceito", True):
            self._anexar("finais.jsonl", {"t": _iso(_agora_utc()), "agencia": ag, "hash": h, "hash_sub": h_sub,
                                          "n": resp.get("n"), "taxa": resp.get("taxa", 0), "autor": self.autor})
        self._registrar_cobranca("final", ag, h, resp)
        return resp
