import json
import math
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import recarga
from recarga import lote, objetivo, otimizador, pesos
from recarga.testes.test_objetivo import catalogo_falso
from kickoff import validar

EXEMPLO = json.loads((recarga.KIT / "exemplo_submissao.json").read_text(encoding="utf-8"))
SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}


class ComTemporarios(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for alvo, nome, valor in ((lote, "CACHE", self.tmp / "sim"),
                                  (otimizador, "SAIDA", self.tmp / "otimizador"),
                                  (otimizador, "ESCALA", self.tmp / "pesos" / "escala.json"),
                                  (pesos, "ESTIMATIVA", self.tmp / "pesos" / "estimativa.json"),
                                  (lote, "catalogo", lambda: None)):
            p = mock.patch.object(alvo, nome, valor)
            p.start()
            self.addCleanup(p.stop)


class Espaco(unittest.TestCase):
    def test_12_politicas(self):
        ps = otimizador.politicas()
        self.assertEqual(len(ps), 12)
        self.assertEqual(len({json.dumps(p, sort_keys=True) for p in ps}), 12)
        cen = lote.cenario("Bangkok")
        for p in ps:
            self.assertEqual(validar.validar({**EXEMPLO, "politica": p}, cen), [])

    def test_vizinhos_respeitam_vagas(self):
        viz = otimizador.vizinhos({"dc_60x2": 3}, 6)
        self.assertTrue(viz)
        for v in viz:
            self.assertLessEqual(sum(SAIDAS[k] * n for k, n in v.items()), 6, v)
            self.assertGreaterEqual(sum(v.values()), 1)
            self.assertTrue(all(n > 0 for n in v.values()))
        self.assertIn({"dc_60x2": 2}, viz)
        self.assertIn({"dc_30": 1, "dc_60x2": 2}, viz)
        self.assertNotIn({"dc_60x2": 4}, viz)
        self.assertEqual(len({json.dumps(v, sort_keys=True) for v in viz}), len(viz))

    def test_vizinhos_adiciona_troca_e_nao_esvazia(self):
        viz = otimizador.vizinhos({"ac_7": 1}, 6)
        self.assertIn({"ac_7": 2}, viz)
        self.assertIn({"ac_7": 1, "dc_120x2": 1}, viz)
        self.assertIn({"dc_30": 1}, viz)
        self.assertIn({"ac_22x2": 1}, viz)
        self.assertNotIn({}, viz)
        self.assertNotIn({"ac_7": 1}, viz)

    def test_entrada_para(self):
        cen = lote.cenario("Bangkok")
        self.assertEqual(otimizador.entrada_para(140, "b3_45", cen), "a4_225")
        self.assertEqual(otimizador.entrada_para(130, "b3_45", cen), "a4_150")
        self.assertEqual(otimizador.entrada_para(30, "b3_45", cen), "a4_150")
        self.assertEqual(otimizador.entrada_para(None, "b3_45", cen), "b3_45")
        self.assertEqual(otimizador.entrada_para(50, "a4_300", cen), "a4_300")
        self.assertIsNone(otimizador.entrada_para(5000, "b3_45", cen))

    def test_para_envio_tira_demanda_nula(self):
        cen = lote.cenario("Bangkok")
        s = validar.normalizar(EXEMPLO, cen)
        env = otimizador.para_envio(s)
        self.assertNotIn("demanda_contratada_kw", env)
        self.assertEqual(validar.validar(env, cen), [])


class Objetivos(ComTemporarios):
    def setUp(self):
        super().setUp()
        self.r = lote.avaliar("Bangkok", {**EXEMPLO, "carregadores": {"dc_60x2": 1}, "entrada": "a4_150",
                                          "demanda_contratada_kw": 60})

    def test_sem_catalogo_nem_estimativa_lexicografica(self):
        obj = otimizador.objetivo_padrao("Bangkok")
        self.assertEqual(obj(self.r), objetivo.chave_lexicografica(self.r["metricas"], self.r["sub"],
                                                                   lote.cenario("Bangkok")))

    def test_catalogo_com_pesos_da_nota_exata(self):
        cat = catalogo_falso()
        with mock.patch.object(lote, "catalogo", lambda: cat):
            obj = otimizador.objetivo_padrao("Bangkok")
            sem = otimizador.objetivo_semana_padrao("Bangkok")
        p = objetivo.pesos_do_catalogo(cat, "Bangkok")
        self.assertAlmostEqual(obj(self.r), objetivo.nota(self.r["metricas"], self.r["sub"], "b3_45", p))
        s0 = self.r["semanas"][0]
        self.assertAlmostEqual(sem(s0, self.r["sub"]), objetivo.nota(s0, self.r["sub"], "b3_45", p))

    def test_estimativa_confiavel_com_escala(self):
        w = {"certo": 10.0, "upgrade": 6.0, "nao_atendido": -25.0, "demanda_contratada": -0.4,
             "energia_ponta_kwh": -0.05}
        est = pesos.Estimativa(objetivo.Pesos(w, {"dc_60x2": -3.0}, {"a4_150": -7.0}), 0.0, 40, True,
                               ["car:dc_120x2"])
        pesos.salvar(est, pesos.ESTIMATIVA)
        otimizador.ESCALA.write_text(json.dumps({"Bangkok": 2.0}), encoding="utf-8")
        obj = otimizador.objetivo_padrao("Bangkok")
        m = self.r["metricas"]
        op = sum(w[i] * m[objetivo.METRICA[i]] for i in objetivo.ITENS_OPERACAO)
        self.assertAlmostEqual(obj(self.r), 2.0 * op - 3.0 - 7.0)
        r120 = lote.avaliar("Bangkok", {**EXEMPLO, "carregadores": {"dc_120x2": 1}})
        self.assertEqual(obj(r120), -math.inf)

    def test_estimativa_nao_confiavel_e_ignorada(self):
        est = pesos.Estimativa(objetivo.Pesos({"certo": 1.0}), 99.0, 40, False, [])
        pesos.salvar(est, pesos.ESTIMATIVA)
        self.assertIsInstance(otimizador.objetivo_padrao("Bangkok")(self.r), tuple)
        self.assertEqual(otimizador.objetivo_semana_padrao("Bangkok")(self.r["semanas"][0], self.r["sub"]),
                         self.r["semanas"][0]["atendimento_pct"])


class Busca(ComTemporarios):
    def test_varrer_demanda(self):
        pol = dict(validar.PADRAO)
        linhas = otimizador.varrer_demanda("Bangkok", {"dc_60x2": 1}, pol, otimizador.objetivo_padrao("Bangkok"))
        b3 = [l for l in linhas if l["demanda"] is None]
        a4 = [l for l in linhas if l["demanda"] is not None]
        self.assertEqual({l["entrada"] for l in b3}, {"b3_45", "b3_75"})
        self.assertEqual([l["demanda"] for l in a4], [30, 40, 50, 60])
        self.assertTrue(all(l["entrada"] == "a4_150" for l in a4))
        self.assertTrue(all("valor" in l for l in linhas))

    def test_buscar_rapido_bangkok_valido_e_melhor_que_exemplo(self):
        exemplo_atendimento = lote.avaliar("Bangkok", EXEMPLO)["metricas"]["atendimento_pct"]
        t = time.time()
        ranking = otimizador.buscar("Bangkok", "rapido")
        self.tempo = time.time() - t
        r = ranking[0]
        self.assertTrue(r["valido"])
        self.assertEqual(r["violacoes"], [])
        self.assertGreaterEqual(r["metricas"]["atendimento_pct"], exemplo_atendimento)
        self.assertIn("valor", r)
        valores = [x["valor"] for x in ranking]
        self.assertEqual(valores, sorted(valores, reverse=True))
        cen = lote.cenario("Bangkok")
        self.assertEqual(validar.validar(r["envio"], cen), [])
        salvo = json.loads((otimizador.SAIDA / "Bangkok" / "ranking.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(salvo), 20)
        self.assertEqual(salvo[0]["hash"], r["hash"])
        self.assertEqual(len(salvo[0]["valor_semanas"]), 4)
        dem = json.loads((otimizador.SAIDA / "Bangkok" / "demanda.json").read_text(encoding="utf-8"))
        self.assertTrue(dem)
        print(f"\n[buscar rapido Bangkok: {self.tempo:.1f} s]")

    def test_busca_local_sobe_com_objetivo_falso(self):
        """Com o motor vazio nada melhora; um objetivo sintético exercita a subida e a varredura."""
        cen = lote.cenario("Bangkok")

        def obj(r):  # alvo: 120 kW nominais; demanda contratada custa um pouco; prefere 'chegada'
            kw = objetivo.kw_instalado(r["sub"], cen)
            bonus = 1.0 if r["sub"]["politica"]["prioridade"] == "chegada" else 0.0
            return -abs(kw - 120) - 0.01 * (r["sub"]["demanda_contratada_kw"] or 0) + bonus

        ranking = otimizador.buscar("Bangkok", "rapido", obj=obj)
        r = ranking[0]
        self.assertEqual(objetivo.kw_instalado(r["sub"], cen), 120)
        self.assertEqual(r["sub"]["politica"]["prioridade"], "chegada")
        self.assertIsNone(r["sub"]["demanda_contratada_kw"])  # B3 vence: demanda só custa
        self.assertGreater(len(ranking), 50)


if __name__ == "__main__":
    unittest.main()
