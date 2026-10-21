import contextlib
import io
import itertools
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import recarga
from recarga import lote, objetivo, pesos
from kickoff import validar

CARS = ("ac_7", "ac_11", "ac_22x2", "dc_30", "dc_60x2")  # dc_120x2 fica de fora de propósito
ENTS = ("b3_45", "b3_75", "a4_150", "a4_225", "a4_300", "se_500", "se_750", "se_1000", "se_1500", "se_2000")
REAIS = {"certo": 10.0, "upgrade": 6.5, "nao_atendido": -25.0, "demanda_contratada": -0.4,
         "energia_ponta_kwh": -0.05,
         **{f"car:{c}": -0.7 * (i + 1) for i, c in enumerate(CARS)},
         **{f"ent:{e}": -1.3 * (i + 1) for i, e in enumerate(ENTS[1:])}}


def est_valor(est, k):
    if k.startswith("car:"):
        return est.pesos.k_carregador[k[4:]]
    if k.startswith("ent:"):
        return est.pesos.k_entrada[k[4:]]
    return est.pesos.w[k]


def amostras_sinteticas(n=40, semente=0, reais=REAIS):
    rng = np.random.default_rng(semente)
    out = []
    for i in range(n):
        c = int(rng.integers(100, 250))
        u = int(rng.integers(0, 271 - c))
        f = {"certo": c, "upgrade": u, "nao_atendido": 271 - c - u,
             "demanda_contratada": float(rng.choice([0, 30, 60, 90, 130, 200])),
             "energia_ponta_kwh": float(rng.uniform(0, 400))}
        for car in CARS:
            f[f"car:{car}"] = int(rng.integers(0, 3))
        e = ENTS[i % len(ENTS)]
        for x in ENTS[1:]:
            f[f"ent:{x}"] = 1 if x == e else 0
        y = sum(reais[k] * v for k, v in f.items())
        out.append((f, y))
    return out


class Features(unittest.TestCase):
    def test_features(self):
        m = {"certos": 200, "upgrades": 40, "nao_atendidos": 31, "demanda_contratada_kw": 90,
             "energia_ponta_kwh": 12.5}
        s = {"carregadores": {"dc_60x2": 2, "ac_7": 1}, "entrada": "a4_150"}
        f = pesos.features(m, s, "b3_45")
        self.assertEqual(f, {"certo": 200, "upgrade": 40, "nao_atendido": 31, "demanda_contratada": 90,
                             "energia_ponta_kwh": 12.5, "car:dc_60x2": 2, "car:ac_7": 1, "ent:a4_150": 1})
        self.assertNotIn("ent:b3_45", pesos.features(m, {**s, "entrada": "b3_45"}, "b3_45"))

    def test_features_batem_com_objetivo(self):
        p = objetivo.Pesos({"certo": 2, "upgrade": 1, "nao_atendido": -3, "demanda_contratada": -0.5,
                            "energia_ponta_kwh": -0.1}, {"dc_60x2": -4, "ac_7": -1}, {"a4_150": -9})
        m = {"certos": 200, "upgrades": 40, "nao_atendidos": 31, "demanda_contratada_kw": 90,
             "energia_ponta_kwh": 12.5}
        s = {"carregadores": {"dc_60x2": 2, "ac_7": 1}, "entrada": "a4_150"}
        f = pesos.features(m, s, "b3_45")
        lin = sum(v * {**p.w, **{f"car:{k}": x for k, x in p.k_carregador.items()},
                       **{f"ent:{k}": x for k, x in p.k_entrada.items()}}[k] for k, v in f.items())
        self.assertAlmostEqual(lin, objetivo.nota(m, s, "b3_45", p))


class Estimar(unittest.TestCase):
    def test_recupera_pesos_sinteticos(self):
        est = pesos.estimar(amostras_sinteticas())
        self.assertTrue(est.confiavel)
        self.assertEqual(est.n, 40)
        self.assertLess(est.residuo_rms, 1e-6)
        for k, v in REAIS.items():
            self.assertAlmostEqual(est_valor(est, k), v, places=6)

    def test_coluna_nunca_variada_nao_identificada(self):
        amostras = amostras_sinteticas()
        amostras = [({**f, "car:dc_120x2": 0}, y) for f, y in amostras]
        est = pesos.estimar(amostras)
        self.assertIn("car:dc_120x2", est.nao_identificados)
        self.assertNotIn("dc_120x2", est.pesos.k_carregador)
        self.assertNotIn("car:ac_7", est.nao_identificados)

    def test_item_de_operacao_nao_identificado_nao_confiavel(self):
        # upgrade sempre 0 (motor real em Bangkok com infra boa): ajuste exato, mas sem peso de upgrade
        amostras = []
        for f, _ in amostras_sinteticas():
            f = {**f, "nao_atendido": f["nao_atendido"] + f["upgrade"], "upgrade": 0}
            amostras.append((f, sum(REAIS[k] * v for k, v in f.items())))
        est = pesos.estimar(amostras)
        self.assertIn("upgrade", est.nao_identificados)
        self.assertLess(est.residuo_rms, 1e-6)
        self.assertFalse(est.confiavel)

    def test_ruido_grande_nao_confiavel(self):
        rng = np.random.default_rng(1)
        amostras = [(f, y + rng.normal(0, 300)) for f, y in amostras_sinteticas()]
        self.assertFalse(pesos.estimar(amostras).confiavel)

    def test_poucas_amostras_nao_confiavel(self):
        # menos amostras que incógnitas: ajuste exato, mas pesos indeterminados
        self.assertFalse(pesos.estimar(amostras_sinteticas(n=8)).confiavel)

    def test_escala(self):
        amostras = amostras_sinteticas()
        est = pesos.estimar(amostras)
        ag = []
        for f, _ in amostras_sinteticas(n=10, semente=7):
            op = sum(REAIS[k] * f[k] for k in objetivo.ITENS_OPERACAO)
            infra = sum(REAIS[k] * v for k, v in f.items() if k not in objetivo.ITENS_OPERACAO)
            ag.append((f, 1.5 * op + infra))
        self.assertAlmostEqual(pesos.escala(est, ag), 1.5, places=6)

    def test_salvar_e_carregar(self):
        est = pesos.estimar(amostras_sinteticas())
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        p = tmp / "pesos" / "estimativa.json"
        pesos.salvar(est, p)
        doc = json.loads(p.read_text(encoding="utf-8"))
        self.assertIn("residuo_rms", doc)
        de_volta = pesos.carregar(p)
        self.assertEqual(de_volta.n, est.n)
        self.assertEqual(de_volta.confiavel, est.confiavel)
        self.assertAlmostEqual(de_volta.pesos.w["certo"], est.pesos.w["certo"])


class Experimentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cen = lote.cenario("Bangkok")
        cls.subs = pesos.experimentos_bangkok()
        cls.norm = [validar.normalizar(s, cls.cen) for s in cls.subs]

    def test_experimentos_validos_e_cobrem_blocos(self):
        self.assertGreaterEqual(len(self.subs), 40)
        for s in self.subs:
            self.assertEqual(validar.validar(s, self.cen), [], s)
        hashes = {json.dumps(n, sort_keys=True) for n in self.norm}
        self.assertEqual(len(hashes), len(self.norm), "experimentos repetidos")
        for c in self.cen.carregadores:
            self.assertGreaterEqual(sum(1 for n in self.norm if c in n["carregadores"]), 2, c)
        for e in self.cen.entradas:
            self.assertGreaterEqual(sum(1 for n in self.norm if n["entrada"] == e), 2, e)

        def so_difere(a, b, campo):
            return a[campo] != b[campo] and all(a[k] == b[k] for k in a if k != campo)

        def so_difere_ponta(a, b):
            pa, pb = a["politica"], b["politica"]
            return (pa["evitar_ponta"] != pb["evitar_ponta"]
                    and all(pa[k] == pb[k] for k in pa if k != "evitar_ponta")
                    and all(a[k] == b[k] for k in a if k != "politica"))

        pares = list(itertools.combinations(self.norm, 2))
        self.assertTrue(any(so_difere(a, b, "demanda_contratada_kw") for a, b in pares))
        self.assertTrue(any(so_difere_ponta(a, b) for a, b in pares))

    def test_experimentos_tem_infra_fraca(self):
        """Com o motor real, infra boa dá 100% e 0 upgrades em Bangkok: precisa de configs fracas para variar
        nao_atendido e upgrade."""
        fracas = [n for n in self.norm if objetivo.kw_instalado(n, self.cen) <= 14]
        self.assertGreaterEqual(len(fracas), 5)
        self.assertTrue(any(n["politica"]["evitar_ponta"] for n in fracas))
        self.assertIn({"ac_7": 1}, [n["carregadores"] for n in fracas])
        # limite B3 pequeno com muitas saídas lentas
        self.assertTrue(any(n["entrada"] == "b3_45" and sum(n["carregadores"].values()) >= 6 for n in self.norm))

    def test_experimentos_identificam_todas_as_colunas(self):
        """Com o desenho, a matriz de features (já que demanda/entrada/carregadores vêm da sub) tem posto cheio
        nas colunas de obra e demanda, com operação sintética variando."""
        rng = np.random.default_rng(3)
        amostras = []
        for n in self.norm:
            c = int(rng.integers(50, 250))
            u = int(rng.integers(0, 271 - c))
            m = {"certos": c, "upgrades": u, "nao_atendidos": 271 - c - u,
                 "demanda_contratada_kw": n["demanda_contratada_kw"] or 0.0,
                 "energia_ponta_kwh": float(rng.uniform(0, 300))}
            f = pesos.features(m, n, self.cen.agencia.entrada_existente)
            amostras.append((f, sum(REAIS.get(k, -2.0) * v for k, v in f.items())))
        est = pesos.estimar(amostras)
        self.assertEqual(est.nao_identificados, [])
        self.assertTrue(est.confiavel)


class JuizFalso:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def teste(self, ag, sub, detalhe="placar", confirmar=False):
        self.chamadas.append((ag, sub, detalhe, confirmar))
        return self.respostas[len(self.chamadas) - 1]


class Coletar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(lote, "CACHE", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        silencio = contextlib.redirect_stderr(io.StringIO())
        silencio.__enter__()
        self.addCleanup(silencio.__exit__, None, None, None)

    def test_coletar_usa_nota_do_juiz_e_descarta_divergente(self):
        subs = pesos.experimentos_bangkok()[:3]
        nossos = [lote.avaliar("Bangkok", s) for s in subs]

        def fisicas(r, **extra):
            m = r["metricas"]
            return {"valido": True, "nota": 123.0, "violacoes": [],
                    "metricas": {"contratos": m["contratos"], "atendimento_pct": m["atendimento_pct"],
                                 "energia_kwh": m["energia_kwh"], "pico_kw": m["pico_kw"], **extra}}

        respostas = [fisicas(nossos[0]), fisicas(nossos[1], pico_kw=nossos[1]["metricas"]["pico_kw"] + 50),
                     {**fisicas(nossos[2]), "nota": -7.5}]
        juiz = JuizFalso(respostas)
        amostras = pesos.coletar(juiz, "Bangkok", subs)
        self.assertEqual(len(juiz.chamadas), 3)
        self.assertTrue(all(c[2] == "placar" and c[3] is False for c in juiz.chamadas))
        self.assertEqual([y for _, y in amostras], [123.0, -7.5])
        f0 = pesos.features(nossos[0]["metricas"], nossos[0]["sub"], "b3_45")
        self.assertEqual(amostras[0][0], f0)

    def test_coletar_ignora_invalida_e_violacao(self):
        subs = pesos.experimentos_bangkok()[:2]
        juiz = JuizFalso([{"valido": False, "erros": ["x"]},
                          {"valido": True, "nota": 0, "violacoes": ["v"], "metricas": {}}])
        self.assertEqual(pesos.coletar(juiz, "Bangkok", subs), [])


if __name__ == "__main__":
    unittest.main()
