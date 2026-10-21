"""Monitor do dia: acompanha GET /status e GET /placar e reage ao que muda.

  python -m recarga.operacao

A cada iteração: baixa o kit de agência recém-liberada, grava os eventos ativos em
`resultados/eventos.json`, baixa o catálogo na fase Clara (`kit_kickoff/dados/catalogo.json`)
e guarda o placar em `resultados/placar.jsonl` a cada 5 min. Alerta = print + beep.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from recarga import DADOS, RESULTADOS
from recarga.juiz import Juiz, carregar_env


def _nomes(status: dict) -> list:
    ags = status.get("agencias") or {}
    if isinstance(ags, dict):
        return list(ags)
    return [a if isinstance(a, str) else (a.get("id") or a.get("nome")) for a in ags]


def _ler_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Monitor:
    def __init__(self, juiz, raiz=RESULTADOS, dados=DADOS, placar_a_cada=300, dormir=time.sleep):
        self.juiz, self.raiz, self.dados = juiz, Path(raiz), Path(dados)
        self.placar_a_cada = placar_a_cada
        self.dormir = dormir
        self._anterior = None          # último status visto (memória; na 1ª rodada vem de status.json)
        self._pendentes_kit: set = set()
        self._cat_agencias = None      # agências do catálogo baixado na Clara
        self._ultimo_placar = None

    def _alertar(self, msg: str, alertas: list) -> None:
        alertas.append(msg)
        print(msg + "\a", flush=True)

    def _guardado(self, nome: str, fn, alertas: list) -> None:
        try:
            fn()
        except Exception as e:  # o monitor nunca cai: vira alerta e segue na próxima rodada
            self._alertar(f"erro em {nome}: {type(e).__name__}: {e}", alertas)

    def passo(self, agora: float) -> list:
        alertas: list = []
        anterior = self._anterior if self._anterior is not None else _ler_json(self.raiz / "status.json")
        try:
            st = self.juiz.status()
        except Exception as e:
            self._alertar(f"erro ao consultar status: {type(e).__name__}: {e}", alertas)
            return alertas
        self._anterior = st
        self._guardado("agências", lambda: self._agencias(st, anterior, alertas), alertas)
        self._guardado("eventos", lambda: self._eventos(st, anterior, alertas), alertas)
        self._guardado("fase", lambda: self._fase(st, anterior, alertas), alertas)
        self._guardado("placar", lambda: self._placar(agora), alertas)
        return alertas

    def _agencias(self, st: dict, anterior, alertas: list) -> None:
        antes = set(_nomes(anterior)) if anterior else set()
        for ag in _nomes(st):
            if ag not in antes:
                self._alertar(f"agência liberada: {ag}", alertas)
                self._pendentes_kit.add(ag)
        for ag in sorted(self._pendentes_kit):
            if (self.dados / ag / "agencias.md").is_file():
                self._pendentes_kit.discard(ag)
                continue
            try:
                self.juiz.kit(ag)
            except Exception as e:  # tenta de novo na próxima rodada
                self._alertar(f"erro ao baixar kit de {ag}: {type(e).__name__}: {e}", alertas)
            else:
                self._pendentes_kit.discard(ag)
                self._alertar(f"kit de {ag} baixado", alertas)

    def _eventos(self, st: dict, anterior, alertas: list) -> None:
        ev, ev_antes = st.get("eventos_ativos") or [], (anterior or {}).get("eventos_ativos") or []
        for e in ev:
            if e not in ev_antes:
                self._alertar(f"evento novo em {e.get('agencia')}: {e.get('params')}", alertas)
        if ev != ev_antes:
            self.raiz.mkdir(parents=True, exist_ok=True)
            (self.raiz / "eventos.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
        cartas_antes = (anterior or {}).get("cartas") or []
        for c in st.get("cartas") or []:
            if c not in cartas_antes:
                self._alertar(f"carta nova #{c.get('n')}: {c.get('titulo')} ({c.get('agencia')})", alertas)

    def _fase(self, st: dict, anterior, alertas: list) -> None:
        fase = st.get("fase")
        if anterior and anterior.get("fase") != fase:
            self._alertar(f"fase mudou: {anterior.get('fase')} -> {fase}", alertas)
        if fase == "clara":
            ags = frozenset(_nomes(st))
            if ags != self._cat_agencias:  # 1ª vez na Clara, ou agência nova com pesos novos
                cat = self.juiz.catalogo()
                self.dados.mkdir(parents=True, exist_ok=True)
                (self.dados / "catalogo.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
                self._cat_agencias = ags
                self._alertar("catálogo da fase Clara salvo (custos e pesos)", alertas)

    def _placar(self, agora: float) -> None:
        if self._ultimo_placar is not None and agora - self._ultimo_placar < self.placar_a_cada:
            return
        pl = self.juiz.placar()
        self._ultimo_placar = agora
        self.raiz.mkdir(parents=True, exist_ok=True)
        linha = {"t": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "agora": agora, "placar": pl}
        with open(self.raiz / "placar.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")

    def rodar(self, intervalo=60, placar_a_cada=300) -> None:
        self.placar_a_cada = placar_a_cada
        inicio = time.monotonic()
        try:
            while True:
                self.passo(time.monotonic() - inicio)
                self.dormir(intervalo)
        except KeyboardInterrupt:
            print("monitor encerrado")


def main() -> None:
    carregar_env()
    Monitor(Juiz()).rodar()


if __name__ == "__main__":
    main()
