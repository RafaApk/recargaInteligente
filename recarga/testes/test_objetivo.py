import unittest

import recarga
from recarga import objetivo
from kickoff import dados, nota, validar

PESOS = {"certo": 10.0, "upgrade": 6.0, "nao_atendido": -25.0, "demanda_contratada": -0.4,
         "energia_ponta_kwh": -0.05, "infraestrutura": -0.002}
CUSTO_CAR = {"ac_7": 100, "ac_11": 150, "ac_22x2": 400, "dc_30": 900, "dc_60x2": 2500, "dc_120x2": 5000}
CUSTO_ENT = {"b3_45": 0, "b3_75": 300, "a4_150": 2000, "a4_225": 2600, "a4_300": 3100, "se_500": 8000,
             "se_750": 11000, "se_1000": 14000, "se_1500": 19000, "se_2000": 25000}


def catalogo_falso():
    return {
        "carregadores": [{"id": k, "custo": v} for k, v in CUSTO_CAR.items()],
        "entradas": [{"id": k, "custo": v} for k, v in CUSTO_ENT.items()],
        "pesos": {"Bangkok": dict(PESOS)},
    }


METRICAS = {"contratos": 271, "certos": 200, "upgrades": 40, "nao_atendidos": 31, "pico_kw": 80.0,
            "energia_kwh": 3000.0, "energia_ponta_kwh": 120.5, "atendimento_pct": 88.56,
            "demanda_contratada_kw": 90}


class Objetivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = catalogo_falso()
        cls.cen = dados.carregar(recarga.DADOS, "Bangkok", cls.cat)

    def test_itens_operacao_sao_do_kit(self):
        nomes = [r for r, _ in nota.ITENS]
        for i in objetivo.ITENS_OPERACAO:
            self.assertIn(i, nomes)
        self.assertNotIn("infraestrutura", objetivo.ITENS_OPERACAO)

    def test_nota_igual_ao_kit(self):
        p = objetivo.pesos_do_catalogo(self.cat, "Bangkok")
        for sub in (
            {"agencia": "Bangkok", "carregadores": {"dc_60x2": 2, "ac_7": 1}, "entrada": "a4_150",
             "demanda_contratada_kw": 90},
            {"agencia": "Bangkok", "carregadores": {"ac_22x2": 1, "dc_30": 2}, "entrada": "b3_45"},
            {"agencia": "Bangkok", "carregadores": {"dc_120x2": 3}, "entrada": "se_500"},
        ):
            self.assertEqual(validar.validar(sub, self.cen), [])
            s = validar.normalizar(sub, self.cen)
            m = {**METRICAS, "demanda_contratada_kw": s["demanda_contratada_kw"] or 0.0}
            m2 = {**m, "custo_infra": nota.custo_infra(s, self.cen)["total"]}
            esperado = nota.pontuar(m2, self.cat["pesos"]["Bangkok"])["nota"]
            obtido = objetivo.nota(m, s, self.cen.agencia.entrada_existente, p)
            self.assertAlmostEqual(obtido, esperado, places=9)

    def test_entrada_existente_custa_zero(self):
        cat = catalogo_falso()
        cat["entradas"] = [{"id": k, "custo": 777} for k in CUSTO_ENT]
        p = objetivo.pesos_do_catalogo(cat, "Bangkok")
        s = {"agencia": "Bangkok", "carregadores": {"ac_7": 1}, "entrada": "b3_45",
             "demanda_contratada_kw": None, "politica": dict(validar.PADRAO)}
        m = {**METRICAS, "demanda_contratada_kw": 0.0}
        base = objetivo.nota(m, s, "b3_45", p)
        self.assertAlmostEqual(base, objetivo.nota(m, s, "b3_45", objetivo.Pesos(p.w, p.k_carregador, {})))
        s75 = {**s, "entrada": "b3_75"}
        self.assertAlmostEqual(objetivo.nota(m, s75, "b3_45", p), base + PESOS["infraestrutura"] * 777)

    def test_pesos_do_catalogo(self):
        p = objetivo.pesos_do_catalogo(self.cat, "Bangkok")
        self.assertEqual(set(p.w), set(objetivo.ITENS_OPERACAO))
        self.assertAlmostEqual(p.k_carregador["dc_60x2"], -0.002 * 2500)
        self.assertAlmostEqual(p.k_entrada["a4_150"], -0.002 * 2000)

    def test_lexicografica_prefere_menos_kw_com_mesmo_atendimento(self):
        s1 = validar.normalizar({"agencia": "Bangkok", "carregadores": {"dc_60x2": 2}, "entrada": "b3_45"}, self.cen)
        s2 = validar.normalizar({"agencia": "Bangkok", "carregadores": {"dc_30": 2}, "entrada": "b3_45"}, self.cen)
        k1 = objetivo.chave_lexicografica(METRICAS, s1, self.cen)
        k2 = objetivo.chave_lexicografica(METRICAS, s2, self.cen)
        self.assertGreater(k2, k1)
        self.assertEqual(k2, (METRICAS["atendimento_pct"], METRICAS["certos"], -60.0))

    def test_lexicografica_atendimento_manda(self):
        s1 = validar.normalizar({"agencia": "Bangkok", "carregadores": {"dc_60x2": 3}, "entrada": "b3_45"}, self.cen)
        s2 = validar.normalizar({"agencia": "Bangkok", "carregadores": {"ac_7": 1}, "entrada": "b3_45"}, self.cen)
        melhor = {**METRICAS, "atendimento_pct": 95.0, "certos": 100}
        self.assertGreater(objetivo.chave_lexicografica(melhor, s1, self.cen),
                           objetivo.chave_lexicografica(METRICAS, s2, self.cen))


if __name__ == "__main__":
    unittest.main()
