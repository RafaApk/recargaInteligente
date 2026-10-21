import json
import os
import tempfile
import unittest
from pathlib import Path

from dashboard import dados, exemplo


class DadosComExemplo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        exemplo.gerar(self.raiz)

    def tearDown(self):
        self._tmp.cleanup()

    def test_gasto_por_agencia_soma_taxas_do_ledger(self):
        linhas = [json.loads(ln) for ln in (self.raiz / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(linhas), 5)
        esperado = sum(ln["taxa"] for ln in linhas)
        self.assertGreater(esperado, 0)
        self.assertEqual(dados.gasto_por_agencia(self.raiz), {"Bangkok": esperado})
        self.assertEqual(len(dados.ledger(self.raiz)), 5)

    def test_respostas_juiz_tem_duas_com_series(self):
        resp = dados.respostas_juiz(self.raiz, "Bangkok")
        self.assertEqual(len(resp), 2)
        for h, r in resp.items():
            self.assertEqual(len(h), 64)
            s = r["series"]
            self.assertEqual(s["passo_min"], 15)
            self.assertEqual(len(s["potencia_kw"]), 28 * 96)
            self.assertEqual(len(s["plugados_max"]), 28 * 96)
            self.assertEqual(len(s["fila_max"]), 28 * 96)
            m = r["metricas"]
            nao = m["contratos"] - round(m["contratos"] * m["atendimento_pct"] / 100)
            self.assertEqual(len(s["nao_atendidos_min"]), nao)
            self.assertEqual(len(s["soc_retirada"]), m["contratos"] - nao)

    def test_pontos_do_juiz_somam_a_nota(self):
        com_pontos = [r for r in dados.respostas_juiz(self.raiz, "Bangkok").values() if "pontos" in r]
        self.assertTrue(com_pontos)
        for r in com_pontos:
            self.assertAlmostEqual(sum(i[3] for i in r["pontos"]["itens"]), r["pontos"]["nota"], places=6)
            self.assertAlmostEqual(r["pontos"]["nota"], r["nota"], places=6)
            self.assertEqual([i[0] for i in r["pontos"]["itens"]], [i for i, _ in dados.ITENS])

    def test_simulacoes_casam_com_respostas(self):
        sims = dados.simulacoes(self.raiz, "Bangkok")
        self.assertEqual(set(sims), set(dados.respostas_juiz(self.raiz, "Bangkok")))
        for s in sims.values():
            self.assertEqual(len(dados.normalizar_series(s["series"])["potencia_kw"]), 28 * 96)

    def test_demais_arquivos(self):
        self.assertEqual(len(dados.placar(self.raiz)), 3)
        self.assertEqual(len(dados.finais(self.raiz)), 2)
        self.assertEqual(dados.status(self.raiz)["fase"], "neblina")
        self.assertGreaterEqual(len(dados.ranking(self.raiz, "Bangkok")), 3)
        self.assertGreaterEqual(len(dados.demanda(self.raiz, "Bangkok")), 5)
        self.assertIn("pesos", dados.pesos(self.raiz))

    def test_ranking_aponta_para_respostas_existentes(self):
        hashes = set(dados.respostas_juiz(self.raiz, "Bangkok"))
        rk = dados.ranking(self.raiz, "Bangkok")
        self.assertTrue(hashes <= {c["hash"] for c in rk})

    def test_vigente_e_o_ultimo_final_aceito(self):
        vig = dados.vigentes(dados.finais(self.raiz))
        fin = dados.finais(self.raiz)
        self.assertEqual(vig["Bangkok"], fin[-1])
        self.assertEqual(fin[-1]["n"], 2)

    def test_agencias_conhecidas(self):
        self.assertEqual(dados.agencias_conhecidas(self.raiz), ["Bangkok"])

    def test_normalizar_series_desembrulha_publico(self):
        plano = {"inicio_min": 1080, "passo_min": 15, "potencia_kw": [1.0]}
        self.assertIs(dados.normalizar_series({"publico": plano}), plano)
        self.assertIs(dados.normalizar_series(plano), plano)
        self.assertEqual(dados.normalizar_series(None), {})


class PastaVaziaOuRuim(unittest.TestCase):
    def test_pasta_vazia_devolve_vazios(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            self.assertEqual(dados.ledger(r), [])
            self.assertEqual(dados.gasto_por_agencia(r), {})
            self.assertEqual(dados.placar(r), [])
            self.assertEqual(dados.finais(r), [])
            self.assertEqual(dados.status(r), {})
            self.assertEqual(dados.respostas_juiz(r, "X"), {})
            self.assertEqual(dados.simulacoes(r, "X"), {})
            self.assertEqual(dados.ranking(r, "X"), [])
            self.assertEqual(dados.demanda(r, "X"), [])
            self.assertEqual(dados.pesos(r), {})
            self.assertEqual(dados.agencias_conhecidas(r), [])

    def test_pasta_inexistente(self):
        r = Path(tempfile.gettempdir()) / "nao-existe-recarga-xyz"
        self.assertEqual(dados.ledger(r), [])
        self.assertEqual(dados.respostas_juiz(r, "X"), {})

    def test_linha_corrompida_e_ignorada(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / "ledger.jsonl").write_text(
                '{"agencia": "A", "taxa": 20}\n{quebrada\n\n{"agencia": "A", "taxa": 5}\n', encoding="utf-8")
            (r / "status.json").write_text("{nao é json", encoding="utf-8")
            self.assertEqual(len(dados.ledger(r)), 2)
            self.assertEqual(dados.gasto_por_agencia(r), {"A": 25})
            self.assertEqual(dados.status(r), {})

    def test_padrao_le_variavel_de_ambiente(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            antes = os.environ.get("RESULTADOS_DIR")
            os.environ["RESULTADOS_DIR"] = d
            try:
                self.assertEqual(len(dados.ledger()), 5)
            finally:
                if antes is None:
                    del os.environ["RESULTADOS_DIR"]
                else:
                    os.environ["RESULTADOS_DIR"] = antes


class PontuacaoEstimada(unittest.TestCase):
    """Formato de `recarga.pesos.salvar`: tudo com sinal."""
    METRICAS = {"certos": 100, "upgrades": 10, "nao_atendidos": 5, "demanda_contratada_kw": 90.0,
                "energia_ponta_kwh": 200.0}
    EST = {"pesos": {"w": {"certo": 10, "upgrade": 6, "nao_atendido": -12, "demanda_contratada": -2,
                           "energia_ponta_kwh": -0.5},
                     "k_carregador": {"dc_60x2": -20, "ac_22x2": -8}, "k_entrada": {"a4_150": -50}},
           "residuo_rms": 1.0, "n": 9, "confiavel": True, "nao_identificados": []}
    SUB = {"carregadores": {"dc_60x2": 2, "ac_22x2": 1}, "entrada": "a4_150"}

    def test_itens_estimados_com_sinal(self):
        itens = dados.pontuar_estimado(self.METRICAS, self.EST, self.SUB, entrada_existente="b3_45")
        por = {i[0]: i[3] for i in itens["itens"]}
        self.assertEqual(por["certo"], 1000)
        self.assertEqual(por["upgrade"], 60)
        self.assertEqual(por["nao_atendido"], -60)
        self.assertEqual(por["demanda_contratada"], -180)
        self.assertEqual(por["energia_ponta_kwh"], -100)
        self.assertEqual(por["infraestrutura"], -(2 * 20 + 8 + 50))
        self.assertAlmostEqual(itens["nota"], sum(por.values()))

    def test_entrada_existente_nao_custa(self):
        sub = {**self.SUB, "entrada": "b3_45"}
        itens = dados.pontuar_estimado(self.METRICAS, self.EST, sub, entrada_existente="b3_45")
        por = {i[0]: i[3] for i in itens["itens"]}
        self.assertEqual(por["infraestrutura"], -(2 * 20 + 8))

    def test_custo_nao_identificado_invalida(self):
        est = {**self.EST, "nao_identificados": ["car:ac_22x2"]}
        self.assertIsNone(dados.pontuar_estimado(self.METRICAS, est, self.SUB, "b3_45"))
        self.assertIsNone(dados.obra_estimada(self.EST, {**self.SUB, "entrada": "a4_225"}, "b3_45"))

    def test_item_sem_peso_so_passa_com_quantidade_zero(self):
        w = {k: v for k, v in self.EST["pesos"]["w"].items() if k != "upgrade"}
        est = {**self.EST, "pesos": {**self.EST["pesos"], "w": w}}
        self.assertIsNone(dados.pontuar_estimado(self.METRICAS, est, self.SUB, "b3_45"))
        zero = {**self.METRICAS, "upgrades": 0}
        self.assertIsNotNone(dados.pontuar_estimado(zero, est, self.SUB, "b3_45"))

    def test_sem_pesos_devolve_none(self):
        self.assertIsNone(dados.pontuar_estimado(self.METRICAS, {}, self.SUB))
        self.assertIsNone(dados.pontuar_estimado({}, self.EST, self.SUB))


class PontuacaoExata(unittest.TestCase):
    """Pós-H4: `kickoff.nota.custo_infra` + `kickoff.nota.pontuar` com o catálogo."""

    def test_usa_custos_e_pesos_do_catalogo(self):
        from kickoff.dados import carregar
        from recarga import RAIZ
        cat = {"pesos": {"Bangkok": {"certo": 10, "upgrade": 6, "nao_atendido": -12, "demanda_contratada": -2,
                                     "energia_ponta_kwh": -0.5, "infraestrutura": -3}},
               "carregadores": [{"id": k, "custo": c} for k, c in
                                (("ac_7", 2), ("ac_11", 3), ("ac_22x2", 7), ("dc_30", 8), ("dc_60x2", 18),
                                 ("dc_120x2", 30))],
               "entradas": [{"id": k, "custo": c} for k, c in (("b3_45", 0), ("b3_75", 6), ("a4_150", 14),
                                                               ("a4_225", 20))]}
        cen = carregar(RAIZ, "Bangkok", cat)
        sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_75",
               "demanda_contratada_kw": None}  # forma normalizada: o dashboard tira o null
        m = {"certos": 100, "upgrades": 10, "nao_atendidos": 5, "demanda_contratada_kw": 0.0,
             "energia_ponta_kwh": 200.0}
        r = dados.pontuar_exato(m, sub, cen, cat, "Bangkok")
        por = {i[0]: i[3] for i in r["itens"]}
        self.assertEqual(r["custo_infra"]["total"], 2 * 2 + 8 + 6)
        self.assertEqual(por["infraestrutura"], -3 * 18)
        self.assertEqual(por["certo"], 1000)
        self.assertAlmostEqual(r["nota"], 1000 + 60 - 60 - 100 - 54)

    def test_sem_custos_devolve_none(self):
        from kickoff.dados import carregar
        from recarga import RAIZ
        cen = carregar(RAIZ, "Bangkok")  # sem catálogo: custos None
        cat = {"pesos": {"Bangkok": {}}}
        sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 1}, "entrada": "b3_45"}
        self.assertIsNone(dados.pontuar_exato({"certos": 1}, sub, cen, cat, "Bangkok"))


class Formatacao(unittest.TestCase):
    def test_fmt_brasileiro(self):
        self.assertEqual(dados.fmt(1234.567, 1), "1.234,6")
        self.assertEqual(dados.fmt(-5, 0, sinal=True), "-5")
        self.assertEqual(dados.fmt(5, 0, sinal=True), "+5")
        self.assertEqual(dados.fmt(-0.0, 0, sinal=True), "0")
        self.assertEqual(dados.fmt(-0.004, 1, sinal=True), "0,0")
        self.assertEqual(dados.fmt(None), "—")
        self.assertEqual(dados.fmt("x"), "—")

    def test_total_obra(self):
        self.assertEqual(dados.total_obra({"carregadores": 1, "entrada": 2, "total": 3}), 3)
        self.assertEqual(dados.total_obra(57), 57)
        self.assertIsNone(dados.total_obra("pendente"))
        self.assertIsNone(dados.total_obra(None))


class Fidelidade(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        exemplo.gerar(Path(self._tmp.name))
        self.juiz = dados.respostas_juiz(self._tmp.name, "Bangkok")
        self.sim = dados.simulacoes(self._tmp.name, "Bangkok")
        self.h_ok = exemplo.hash_sub(exemplo.SUB_A)
        self.h_div = exemplo.hash_sub(exemplo.SUB_B)

    def tearDown(self):
        self._tmp.cleanup()

    def _comparar(self, h):
        return dados.fidelidade(self.sim[h]["metricas"], self.juiz[h]["metricas"],
                                dados.normalizar_series(self.sim[h]["series"]),
                                dados.normalizar_series(self.juiz[h]["series"]))

    def test_bate_com_o_juiz(self):
        f = self._comparar(self.h_ok)
        self.assertTrue(f["ok"])
        self.assertEqual(f["divergencias"], [])
        self.assertIn("Pico de 15 min (kW)", {ln["metrica"] for ln in f["linhas"]})
        self.assertTrue(all(ln["ok"] for ln in f["linhas"]))

    def test_aponta_metrica_e_primeira_janela_divergente(self):
        f = self._comparar(self.h_div)
        self.assertFalse(f["ok"])
        self.assertIn("pico_kw", f["divergencias"])
        self.assertTrue(any(d.startswith("series.potencia_kw@") for d in f["divergencias"]))
        self.assertIn("primeira divergência", f["series"])
        pico = next(ln for ln in f["linhas"] if ln["chave"] == "pico_kw")
        self.assertFalse(pico["ok"])
        self.assertAlmostEqual(pico["dif"], 0.03, places=4)

    def test_sem_series(self):
        f = dados.fidelidade({"pico_kw": 1.0}, {"pico_kw": 1.0}, {}, {})
        self.assertTrue(f["ok"])
        self.assertEqual(f["series"], "")


class Justificativa(unittest.TestCase):
    def test_texto_com_demanda_escolhida(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            texto = dados.justificativa(exemplo.SUB_A, dados.demanda(d, "Bangkok"))
        self.assertIn("a4_150", texto)
        self.assertIn("90", texto)
        self.assertIn("máximo", texto)
        self.assertIn("sem demanda", texto)

    def test_lexicografico_fala_em_atendimento(self):
        curva = [{"demanda_kw": d, "nota": a, "medida": "atendimento", "entrada": "a4_150"}
                 for d, a in ((60, 80.0), (90, 95.0), (120, 95.0))]
        curva.append({"demanda_kw": None, "nota": 90.0, "medida": "atendimento", "entrada": "b3_75"})
        texto = dados.justificativa({"entrada": "a4_150", "demanda_contratada_kw": 90}, curva)
        self.assertIn("atendimento 95,0 %", texto)
        self.assertIn("p.p.", texto)

    def test_sem_dados_nao_quebra(self):
        self.assertEqual(dados.justificativa(None, []), "")
        self.assertIn("b3_45", dados.justificativa({"entrada": "b3_45"}, []))


if __name__ == "__main__":
    unittest.main()
