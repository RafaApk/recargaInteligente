"""Contrato de dados: `resultados/` produzido pelos escritores REAIS das outras frentes
(`recarga.juiz`, `recarga.operacao`, `recarga.lote`, `recarga.otimizador`, `recarga.pesos`) deve ser lido
pelo dashboard sem painéis vazios. O motor ainda pode ser o esqueleto (perde todos os clientes): o que importa
aqui é o formato dos arquivos, não o valor dos números.
"""
import contextlib
import io
import json
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import streamlit as st
from streamlit.testing.v1 import AppTest

import recarga
from recarga import juiz as juiz_mod
from recarga import lote, operacao, otimizador, pesos

from dashboard import dados, graficos

APP = str(Path(__file__).resolve().parent.parent / "app.py")
EXEMPLO = json.loads((recarga.KIT / "exemplo_submissao.json").read_text(encoding="utf-8"))
SUB_1 = {**EXEMPLO, "carregadores": {"ac_7": 2, "dc_30": 1}}
SUB_2 = {**EXEMPLO, "carregadores": {"dc_60x2": 2, "ac_22x2": 1}, "entrada": "b3_75",
         "politica": {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "prioridade"}}
EVENTO = {"agencia": "Teste", "params": [1, "Teste", 2000, 3000]}


class ClienteFalso:
    """Faz o papel da API: responde /teste com o resultado do nosso lote, no formato do regulamento 12.3."""

    def __init__(self):
        self.saldo, self.finais, self.eventos = 1000, 0, []

    def status(self):
        return {"equipe": {"numero": 7, "nome": "Nós", "pode_renomear": False}, "fase": "neblina",
                "etapa": {"n": 1, "rotulo": "Neblina"}, "saldo": self.saldo, "eventos_ativos": list(self.eventos),
                "agencias": {"Bangkok": {"aberta": True, "envios": 0}, "Teste": {"aberta": True, "envios": self.finais}},
                "cartas": []}

    def catalogo(self):
        return {"carregadores": [], "pesos": {}}

    def baixar_kit(self, ag, destino=None):
        return Path(destino) / ag

    def teste(self, ag, sub, detalhe="placar", salvar=None):
        r = lote.avaliar(ag, sub, series=detalhe == "completo")
        taxa = 0 if ag == "Bangkok" else (20 if detalhe == "placar" else 50)
        self.saldo -= taxa
        resp = {"agencia": ag, "periodo": "publico", "valido": True, "erros": [], "violacoes": [], "nota": -1.0,
                "metricas": {k: r["metricas"][k] for k in ("contratos", "atendimento_pct", "pico_kw", "energia_kwh")},
                "taxa": taxa, "saldo": self.saldo, "repetido": False}
        if detalhe == "completo":
            resp["series"] = r["series"]
        return resp

    def _json(self, metodo, caminho, corpo=None):
        if caminho == "/placar":
            return {"fase": "neblina", "etapa": {"n": 1, "rotulo": "Neblina"}, "atualizado_em": "2026-10-21T10:00:00Z",
                    "recalculando": False, "agencias": ["Bangkok", "Teste"], "a_liberar": 4, "cartas": [],
                    "equipes": [{"posicao": 1, "numero": 3, "nome": "Volts", "nota": 120.0, "agencias": {},
                                 "finais": 1, "saldo": 900, "nao_atendidos": None, "custo_infra": None},
                                {"posicao": 2, "numero": 7, "nome": "Nós", "nota": 80.0, "agencias": {},
                                 "finais": 1, "saldo": self.saldo, "nao_atendidos": None, "custo_infra": None}]}
        if caminho.startswith("/final/"):
            taxa = 0 if self.finais == 0 else 80
            self.finais += 1
            self.saldo -= taxa
            return {"agencia": caminho.split("/")[-1], "n": self.finais, "taxa": taxa, "saldo": self.saldo,
                    "aceito": True, "custo_infra": "pendente"}
        raise AssertionError(caminho)


class Real(unittest.TestCase):
    """Ambiente isolado: resultados, kits e cache do lote em pastas temporárias."""

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.kits = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.addCleanup(shutil.rmtree, self.kits, True)
        for nome in ("Bangkok", "Teste"):
            shutil.copytree(recarga.RAIZ / "Bangkok", self.kits / nome)
        lote._CENARIOS.clear()
        for alvo, nome, valor in ((lote, "CACHE", self.raiz / "sim"), (lote, "DADOS", self.kits),
                                  (lote, "catalogo", lambda: None),
                                  (otimizador, "SAIDA", self.raiz / "otimizador"),
                                  (otimizador, "ESCALA", self.raiz / "pesos" / "escala.json"),
                                  (pesos, "ESTIMATIVA", self.raiz / "pesos" / "estimativa.json")):
            p = mock.patch.object(alvo, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lote._CENARIOS.clear)
        st.cache_data.clear()  # o app guarda leituras e resultados do motor entre execuções do AppTest
        st.cache_resource.clear()
        self.cliente = ClienteFalso()
        self.juiz = juiz_mod.Juiz(
            cliente=self.cliente, raiz=self.raiz, dados=self.kits, autor="ana", dormir=lambda s: None,
            limitador=juiz_mod.Limitador(max_por_min=10 ** 6, dormir=lambda s: None),
            simulador=lambda ag, sub, ev: lote.avaliar(ag, sub, ev))

    def operar(self):
        """Dia típico: testes grátis e pagos, dois envios finais e duas rodadas do monitor."""
        j = self.juiz
        j.teste("Bangkok", SUB_1, "placar")
        j.teste("Bangkok", SUB_1, "completo")
        j.teste("Teste", {**SUB_2, "agencia": "Teste"}, "completo", confirmar=True)
        j.final("Teste", {**SUB_1, "agencia": "Teste"}, confirmar=True)
        j.final("Teste", {**SUB_2, "agencia": "Teste"}, confirmar=True)
        self.cliente.eventos = [EVENTO]
        mon = operacao.Monitor(j, raiz=self.raiz, dados=self.kits, dormir=lambda s: None)
        with contextlib.redirect_stdout(io.StringIO()):
            mon.passo(0.0)
            mon.passo(400.0)

    def otimizar(self):
        return otimizador.buscar("Bangkok", "rapido", processos=1)

    def estimar(self):
        w = {"certo": 9.6, "upgrade": 6.3, "nao_atendido": -11.5, "demanda_contratada": -3.1,
             "energia_ponta_kwh": -0.26}
        k_car = {k: -3.0 * (i + 1) for i, k in enumerate(("ac_7", "ac_11", "ac_22x2", "dc_30", "dc_60x2", "dc_120x2"))}
        k_ent = {"b3_75": -12.0, "a4_150": -27.0, "a4_225": -40.0}
        pesos.salvar(pesos.Estimativa(pesos.Pesos(w, k_car, k_ent), 4.8, 17, True, []), pesos.ESTIMATIVA)


class FormatosReais(Real):
    def test_juiz_cache_por_hash_prefere_completo(self):
        self.operar()
        arquivos = sorted(p.name for p in (self.raiz / "juiz" / "Bangkok").glob("*.json"))
        self.assertTrue(any(a.endswith("_placar.json") for a in arquivos), arquivos)
        self.assertTrue(any(a.endswith("_completo.json") for a in arquivos), arquivos)
        resp = dados.respostas_juiz(self.raiz, "Bangkok")
        self.assertEqual(len(resp), 1)  # placar e completo do mesmo hash viram uma resposta só
        (h, r), = resp.items()
        self.assertEqual(len(h), 64)
        self.assertNotIn("_", h)
        self.assertEqual(len(r["series"]["potencia_kw"]), 28 * 96)  # veio do completo
        self.assertEqual(r["metricas"]["contratos"], 271)
        self.assertEqual(len(dados.respostas_juiz(self.raiz, "Teste")), 1)

    def test_ledger_finais_e_status(self):
        self.operar()
        led = dados.ledger(self.raiz)
        self.assertEqual([ln["taxa"] for ln in led], [50, 80])
        self.assertEqual(dados.gasto_por_agencia(self.raiz), {"Teste": 130})
        fin = dados.finais(self.raiz)
        self.assertEqual([f["n"] for f in fin], [1, 2])
        self.assertIsInstance(fin[-1]["sub"], dict)
        self.assertEqual(dados.vigentes(fin)["Teste"]["hash"], fin[-1]["hash"])
        self.assertEqual(dados.status(self.raiz)["fase"], "neblina")
        self.assertEqual(dados.agencias_conhecidas(self.raiz), ["Bangkok", "Teste"])

    def test_placar_embrulhado_vira_snapshots(self):
        self.operar()
        pl = dados.placar(self.raiz)
        self.assertEqual(len(pl), 2)
        for snap in pl:
            self.assertEqual([e["numero"] for e in snap["equipes"]], [3, 7])
            self.assertIsNotNone(dados.hora(snap))
        fig = graficos.evolucao(pl, 7)
        nossa = next(t for t in fig.data if t.name == "Nossa equipe")
        self.assertEqual(len(nossa.y), 2)

    def test_eventos_da_agencia(self):
        self.operar()
        self.assertEqual(dados.eventos(self.raiz), [EVENTO])
        self.assertEqual(dados.eventos_da_agencia(self.raiz, "Teste"), [EVENTO["params"]])
        self.assertEqual(dados.eventos_da_agencia(self.raiz, "Bangkok"), [])

    def test_otimizador_lexicografico(self):
        self.otimizar()
        rk = dados.ranking(self.raiz, "Bangkok")
        self.assertTrue(rk)
        for c in rk:
            self.assertEqual(len(c["hash"]), 64)
            self.assertIsInstance(c["sub"], dict)
            self.assertEqual(c["medida"], "atendimento")  # valor é lista: usa o atendimento (%)
            self.assertIsInstance(c["nota"], float)
            self.assertIsInstance(c["pior_semana"], float)
        dem = dados.demanda(self.raiz, "Bangkok")
        self.assertTrue(dem)
        self.assertTrue(any(d["demanda_kw"] is None for d in dem))  # alternativa B3
        self.assertTrue(any(isinstance(d["demanda_kw"], int) for d in dem))
        for d in dem:
            self.assertEqual(d["medida"], "atendimento")
            self.assertIsInstance(d["nota"], float)
        fig = graficos.curva_demanda(dem, None)
        self.assertTrue(any(t.name == "Atendimento público" for t in fig.data))
        self.assertEqual(fig.layout.yaxis.title.text, "Atendimento (%)")

    def test_otimizador_estimado(self):
        self.estimar()
        self.otimizar()
        rk = dados.ranking(self.raiz, "Bangkok")
        self.assertTrue(rk)
        self.assertTrue(all(c["medida"] == "nota" for c in rk))
        self.assertTrue(any(math.isfinite(c["nota"]) for c in rk))
        dem = dados.demanda(self.raiz, "Bangkok")
        self.assertTrue(all(d["medida"] == "nota" for d in dem))
        self.assertTrue(any(isinstance(d["nota"], float) for d in dem))
        self.assertEqual(graficos.curva_demanda(dem, None).layout.yaxis.title.text, "Nota")

    def test_sim_lido_por_hash(self):
        self.otimizar()
        h = dados.ranking(self.raiz, "Bangkok")[0]["hash"]
        sim = dados.simulacao(self.raiz, "Bangkok", h)
        self.assertEqual(sim["hash"], h)
        self.assertIn("metricas", sim)
        self.assertNotIn("series", sim)  # o otimizador avalia sem séries: o app roda o motor ao vivo
        self.assertEqual(len(sim["semanas"]), 4)
        self.assertIsNone(dados.simulacao(self.raiz, "Bangkok", "0" * 64))

    def test_pesos_salvos_pelo_pesos_py(self):
        self.estimar()
        est = dados.pesos(self.raiz)
        self.assertEqual(est["n"], 17)
        self.assertTrue(est["confiavel"])
        self.assertLess(est["pesos"]["w"]["nao_atendido"], 0)
        self.otimizar()
        sub = dados.ranking(self.raiz, "Bangkok")[0]
        m = dados.simulacao(self.raiz, "Bangkok", sub["hash"])["metricas"]
        p = dados.pontuar_estimado(m, est, sub["sub"], "b3_45")
        self.assertIsNotNone(p)
        self.assertLessEqual(p["itens"][-1][3], 0)  # obra desconta, com o sinal dos `k`
        fig = graficos.pesos_vs_reais(est["pesos"]["w"], {"certo": 10, "nao_atendido": -12, "infraestrutura": -3})
        self.assertEqual(len(fig.data), 2)


class AppComArquivosReais(Real):
    def setUp(self):
        super().setUp()
        antes = os.environ.get("RESULTADOS_DIR")
        os.environ["RESULTADOS_DIR"] = str(self.raiz)
        self.addCleanup(lambda: os.environ.__setitem__("RESULTADOS_DIR", antes) if antes is not None
                        else os.environ.pop("RESULTADOS_DIR", None))

    def _app(self):
        return AppTest.from_file(APP, default_timeout=180).run()

    def test_agencia_vigente_mostra_juiz_modelo_e_fidelidade(self):
        self.estimar()
        self.operar()
        self.otimizar()
        at = self._app()
        self.assertFalse(at.exception)
        self.assertEqual(at.sidebar.selectbox(key="agencia").value, "Teste")
        rot = {m.label: m.value for m in at.metric}
        self.assertEqual(rot["Nota do juiz"], "-1,0")  # a resposta `_completo.json` foi achada
        self.assertNotEqual(rot["Atendimento"], "—")
        self.assertEqual([s.value for s in at.success], ["Bate com o juiz."])  # fidelidade: sim ao vivo × juiz
        self.assertEqual(len(at.get("plotly_chart")), 5)  # cascata, SOC, potência, ocupação, perdas
        self.assertEqual(at.warning, [])

    def test_candidatas_do_otimizador_rodam_o_motor_ao_vivo_com_eventos(self):
        self.estimar()
        self.operar()
        self.otimizar()
        chamadas = []
        real = lote.avaliar

        def espiao(ag, sub, eventos=(), series=False):
            chamadas.append((ag, eventos, series))
            return real(ag, sub, eventos=eventos, series=series)

        with mock.patch.object(lote, "avaliar", espiao):
            at = self._app()
            at.sidebar.selectbox(key="agencia").select("Bangkok").run()
            self.assertFalse(at.exception)
            opcoes = at.sidebar.selectbox(key="submissao").options
            self.assertTrue(any(o.startswith("Candidata") for o in opcoes), opcoes)
            self.assertFalse(any(o.startswith("Teste avulso") and "·" not in o for o in opcoes))
            at.sidebar.selectbox(key="submissao").select_index(0).run()
            self.assertFalse(at.exception)
        # a candidata não tem séries no `sim/`: o app pediu o motor com séries
        self.assertTrue(any(ag == "Bangkok" and series for ag, _, series in chamadas), chamadas)
        self.assertEqual(len(at.get("plotly_chart")), 5)

    def test_eventos_ativos_vao_para_o_motor(self):
        self.otimizar()
        evento = {"agencia": "Bangkok", "params": [1, "Bangkok", 2000, 3000]}
        self.cliente.eventos = [evento]  # o monitor grava `eventos.json` a partir do /status
        mon = operacao.Monitor(self.juiz, raiz=self.raiz, dados=self.kits, dormir=lambda s: None)
        with contextlib.redirect_stdout(io.StringIO()):
            mon.passo(0.0)
        chamadas = []
        real = lote.avaliar

        def espiao(ag, sub, eventos=(), series=False):
            chamadas.append((ag, [list(e) for e in eventos], series))
            return real(ag, sub, eventos=eventos, series=series)

        with mock.patch.object(lote, "avaliar", espiao):
            at = self._app()
            self.assertFalse(at.exception)
        self.assertIn(("Bangkok", [evento["params"]], True), chamadas)

    def test_consolidado_preenche_todos_os_paineis(self):
        self.estimar()
        self.operar()
        self.otimizar()
        at = self._app()
        at.sidebar.radio(key="pagina").set_value("Consolidado").run()
        self.assertFalse(at.exception)
        rot = {m.label: m.value for m in at.metric}
        self.assertEqual(rot["Saldo"], "870 m7Coins")
        self.assertEqual(rot["Gasto no juiz"], "130 m7Coins")
        self.assertEqual(rot["Nota no placar"], "80,0")
        self.assertEqual(len(at.get("plotly_chart")), 5)  # gastos, obra, evolução, demanda, pesos
        texto = " ".join(m.value for m in at.markdown)
        self.assertIn("Entrada **b3_75**", texto)  # justificativa da vigente


if __name__ == "__main__":
    unittest.main()
