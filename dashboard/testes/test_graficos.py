import tempfile
import unittest
from pathlib import Path

import plotly.graph_objects as go

from dashboard import dados, exemplo, graficos

LIMITE = 40.5
HORARIO = exemplo.HORARIO


class GraficosComExemplo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.raiz = Path(cls._tmp.name)
        exemplo.gerar(cls.raiz)
        cls.juizes = list(dados.respostas_juiz(cls.raiz, "Bangkok").values())
        cls.com_pontos = next(r for r in cls.juizes if "pontos" in r)
        cls.series = cls.com_pontos["series"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_potencia_tem_ponta_e_limite(self):
        fig = graficos.potencia(self.series, LIMITE, HORARIO)
        ponta = [s for s in fig.layout.shapes if s.name == "ponta"]
        self.assertEqual(len(ponta), 20)  # 4 semanas x seg-sex
        limite = [s for s in fig.layout.shapes if s.type == "line" and s.y0 == s.y1 == LIMITE]
        self.assertEqual(len(limite), 1)
        self.assertTrue(any(s.name == "fechado" for s in fig.layout.shapes))

    def test_ponta_so_cobre_18_a_21_de_dia_util(self):
        fig = graficos.potencia(self.series, LIMITE, HORARIO)
        for s in (s for s in fig.layout.shapes if s.name == "ponta"):
            self.assertEqual((s.x1 - s.x0).total_seconds(), 3 * 3600)
            self.assertEqual((s.x0.hour, s.x0.minute), (18, 0))
            self.assertLess(s.x0.weekday(), 5)

    def test_fechado_nao_cobre_horario_aberto(self):
        from datetime import timedelta
        fig = graficos.potencia(self.series, LIMITE, HORARIO)
        fechados = [s for s in fig.layout.shapes if s.name == "fechado"]
        self.assertTrue(fechados)
        for s in fechados:
            self.assertLess(s.x0, s.x1)
            t = s.x0
            while t < s.x1:  # amostra a cada 15 min o interior do retângulo
                j = HORARIO[t.weekday()]
                minuto = t.hour * 60 + t.minute
                self.assertFalse(j is not None and j[0] <= minuto < j[1], f"aberto em {t}")
                t += timedelta(minutes=15)

    def test_semana_define_o_intervalo_visivel(self):
        fig = graficos.potencia(self.series, LIMITE, HORARIO, semana=2)
        a, b = fig.layout.xaxis.range
        self.assertEqual((b - a).days, 7)

    def test_perdas_heatmap_7x24(self):
        fig = graficos.perdas(self.series["nao_atendidos_min"], self.series["inicio_min"])
        z = fig.data[0].z
        self.assertEqual((len(z), len(z[0])), (7, 24))
        self.assertEqual(sum(sum(l) for l in z), len(self.series["nao_atendidos_min"]))

    def test_perda_uma_hora_depois_do_inicio_cai_na_hora_seguinte(self):
        from kickoff import tempo
        ini = tempo.T0  # domingo 18:00
        z = graficos.matriz_perdas([60.0], ini)
        self.assertEqual(z[tempo.dia_semana(ini)][18 + 1], 1)
        self.assertEqual(sum(sum(l) for l in z), 1)
        self.assertEqual(graficos.matriz_perdas([6 * 60.0], ini)[0][0], 1)  # domingo 24h = segunda 0h

    def test_cascata_soma_nota(self):
        itens = self.com_pontos["pontos"]["itens"]
        fig = graficos.cascata(itens, None)
        tr = fig.data[0]
        self.assertAlmostEqual(sum(tr.y), self.com_pontos["pontos"]["nota"], places=6)
        self.assertEqual(len(tr.x), len(itens) + 1)  # itens + barra de total

    def test_cascata_estimada_vem_marcada(self):
        fig = graficos.cascata(self.com_pontos["pontos"]["itens"], None, estimado=True)
        self.assertIn("estimado", fig.data[0].name)
        self.assertTrue(any("ESTIMADO" in a.text for a in fig.layout.annotations))
        self.assertFalse(any("ESTIMADO" in a.text for a in graficos.cascata(
            self.com_pontos["pontos"]["itens"], None).layout.annotations))

    def test_cascata_compara_com_o_juiz(self):
        itens = self.com_pontos["pontos"]["itens"]
        fig = graficos.cascata(itens, itens)
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(fig.layout.waterfallmode, "group")

    def test_ocupacao_tem_linhas_de_saidas_e_vagas(self):
        fig = graficos.ocupacao(self.series, 6, 8)
        ys = sorted(s.y0 for s in fig.layout.shapes if s.type == "line")
        self.assertEqual(ys, [6, 8])

    def test_ocupacao_saidas_iguais_as_vagas_tem_uma_linha_so(self):
        fig = graficos.ocupacao(self.series, 6, 6)
        self.assertEqual([s.y0 for s in fig.layout.shapes if s.type == "line"], [6])

    def test_soc_tem_linha_em_80(self):
        fig = graficos.soc_retirada(self.series["soc_retirada"])
        self.assertTrue(any(s.type == "line" and s.x0 == s.x1 == 80 for s in fig.layout.shapes))
        hist = [t for t in fig.data if t.type == "histogram"]
        self.assertEqual(sum(len(t.x) for t in hist), len(self.series["soc_retirada"]))

    def test_gastos_e_evolucao_e_demanda_e_pesos(self):
        ledger = dados.ledger(self.raiz)
        fig = graficos.gastos(ledger)
        barras = [t for t in fig.data if t.type == "bar"]
        self.assertAlmostEqual(sum(sum(b.y) for b in barras), sum(ln["taxa"] for ln in ledger))
        ev = graficos.evolucao(dados.placar(self.raiz), 7)
        nossa = next(t for t in ev.data if t.name == "Nossa equipe")
        self.assertEqual(len(nossa.y), 3)
        dem = graficos.curva_demanda(dados.demanda(self.raiz, "Bangkok"), 90)
        self.assertTrue(any(t.name == "Escolhida" for t in dem.data))
        est = dados.pesos(self.raiz)["pesos"]["w"]
        pv = graficos.pesos_vs_reais(est, {"certo": 10, "upgrade": 6, "nao_atendido": -12})
        self.assertEqual(len(pv.data), 2)
        self.assertEqual(len(graficos.pesos_vs_reais(est, None).data), 1)


class Obra(unittest.TestCase):
    def test_barras_por_agencia_com_origem(self):
        fig = graficos.obra_por_agencia({"Bangkok": (57, "juiz"), "Lima": (30.5, "estimado")})
        barra = fig.data[0]
        self.assertEqual(list(barra.x), ["Bangkok", "Lima"])
        self.assertEqual(list(barra.y), [57, 30.5])
        self.assertEqual(len(fig.data), 3)  # barras + uma legenda por origem


class FigurasVazias(unittest.TestCase):
    def test_tudo_funciona_vazio(self):
        figs = [
            graficos.cascata([], None),
            graficos.cascata([], []),
            graficos.potencia({}, 0, []),
            graficos.potencia({}, None, [None] * 7),
            graficos.ocupacao({}, 0, 0),
            graficos.soc_retirada([]),
            graficos.perdas([], 1080),
            graficos.gastos([]),
            graficos.evolucao([], 7),
            graficos.evolucao([], None),
            graficos.curva_demanda([], None),
            graficos.pesos_vs_reais({}, None),
            graficos.pesos_vs_reais({}, {}),
            graficos.obra_por_agencia({}),
        ]
        for f in figs:
            self.assertIsInstance(f, go.Figure)

    def test_entradas_incompletas_nao_quebram(self):
        self.assertIsInstance(graficos.gastos([{"agencia": "A"}, {"taxa": "x"}]), go.Figure)
        self.assertIsInstance(graficos.evolucao([{"equipes": []}, {}], 7), go.Figure)
        self.assertIsInstance(graficos.curva_demanda([{"demanda_kw": None, "nota": 1}], 10), go.Figure)
        self.assertIsInstance(graficos.potencia({"potencia_kw": [1.0, 2.0]}, 10, [None] * 7), go.Figure)


if __name__ == "__main__":
    unittest.main()
