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
            self.assertIn("publico", s["series"])  # formato de simular.avaliar

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
    METRICAS = {"certos": 100, "upgrades": 10, "nao_atendidos": 5, "demanda_contratada_kw": 90.0,
                "energia_ponta_kwh": 200.0}
    EST = {"pesos": {"certo": 10, "upgrade": 6, "nao_atendido": 12, "demanda_contratada": 2, "energia_ponta_kwh": 0.5},
           "custos": {"carregadores": {"dc_60x2": 20, "ac_22x2": 8}, "entradas": {"a4_150": 50}}}
    SUB = {"carregadores": {"dc_60x2": 2, "ac_22x2": 1}, "entrada": "a4_150"}

    def test_itens_estimados(self):
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

    def test_aceita_letras_a_e(self):
        est = {"pesos": {"a": 10, "b": 6, "c": 12, "d": 2, "e": 0.5}, "custos": self.EST["custos"]}
        self.assertIsNotNone(dados.pontuar_estimado(self.METRICAS, est, self.SUB))

    def test_sem_pesos_devolve_none(self):
        self.assertIsNone(dados.pontuar_estimado(self.METRICAS, {}, self.SUB))
        self.assertIsNone(dados.pontuar_estimado({}, self.EST, self.SUB))


if __name__ == "__main__":
    unittest.main()
