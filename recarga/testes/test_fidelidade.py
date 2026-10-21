import contextlib
import io
import unittest

import recarga
import simular
from kickoff import validar
from kickoff.api import ErroApi
from kickoff.dados import carregar
from recarga.chave import chave
from recarga.fidelidade import matriz, rodar, rotulo

cen = carregar(recarga.DADOS, "Bangkok")


def norm(s):
    return validar.normalizar(s, cen)


def minha_simulacao(sub):
    out = simular.avaliar(sub, {}, recarga.DADOS, None, [], True)
    return {"agencia": "Bangkok", "metricas": out["metricas"], "series": out["series"]["publico"],
            "violacoes": out["violacoes"]}


class JuizFalso:
    """Devolve a própria simulação (ou uma versão alterada dela)."""

    def __init__(self, alterar=None):
        self.chamadas = []
        self.alterar = alterar

    def eventos(self, ag):
        return []

    def teste(self, ag, sub, detalhe="placar", confirmar=False):
        self.chamadas.append((ag, detalhe))
        r = minha_simulacao(sub)
        return self.alterar(r) if self.alterar else r


class Matriz(unittest.TestCase):
    def test_matriz_24_validas_e_distintas(self):
        subs = matriz()
        self.assertEqual(len(subs), 24)
        self.assertEqual(len({chave(norm(s), []) for s in subs}), 24)
        for s in subs:
            self.assertEqual(validar.validar(s, cen), [])

    def test_matriz_cobre_o_menu(self):
        subs = matriz()
        self.assertEqual({s["politica"]["prioridade"] for s in subs}, set(validar.MENU["prioridade"]))
        self.assertEqual({s["politica"]["divisao"] for s in subs}, set(validar.MENU["divisao"]))
        self.assertEqual({s["politica"]["evitar_ponta"] for s in subs}, {False, True})
        self.assertEqual({s["entrada"] for s in subs}, {"b3_45", "a4_150"})
        for s in subs:
            self.assertEqual(s["carregadores"], {"dc_60x2": 1, "ac_22x2": 1, "ac_7": 2})
            self.assertEqual(s["agencia"], "Bangkok")
            self.assertEqual("demanda_contratada_kw" in s, s["entrada"] == "a4_150")
            if s["entrada"] == "a4_150":
                self.assertEqual(s["demanda_contratada_kw"], 130)

    def test_rotulo_distingue_as_24(self):
        self.assertEqual(len({rotulo(s) for s in matriz()}), 24)


class Rodar(unittest.TestCase):
    def test_rodar_marca_ok_quando_igual(self):
        juiz = JuizFalso()
        subs = matriz()[:4]
        res = rodar(juiz, subs)
        self.assertEqual(len(res), 4)
        for r in res:
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["diverge"], [])
        self.assertEqual(juiz.chamadas, [("Bangkok", "completo")] * 4)
        self.assertEqual([r["sub"] for r in res], subs)

    def test_rodar_apanha_divergencia_de_metrica(self):
        def alterar(r):
            r["metricas"] = {**r["metricas"], "pico_kw": r["metricas"]["pico_kw"] + 5}
            return r
        res = rodar(JuizFalso(alterar), matriz()[:1])
        self.assertFalse(res[0]["ok"])
        self.assertIn("pico_kw", res[0]["diverge"])

    def test_rodar_apanha_divergencia_de_serie(self):
        def alterar(r):
            s = dict(r["series"])
            s["potencia_kw"] = [x + 1 for x in s["potencia_kw"]]
            r["series"] = s
            return r
        res = rodar(JuizFalso(alterar), matriz()[:1])
        self.assertFalse(res[0]["ok"])
        self.assertTrue(any(d.startswith("series.potencia_kw") for d in res[0]["diverge"]))

    def test_resposta_sem_metricas_diverge(self):
        res = rodar(JuizFalso(lambda r: {k: v for k, v in r.items() if k != "metricas"}), matriz()[:1])
        self.assertFalse(res[0]["ok"])
        self.assertIn("juiz.sem_metricas", res[0]["diverge"])

    def test_resposta_com_metricas_vazias_diverge(self):
        res = rodar(JuizFalso(lambda r: {**r, "metricas": {}}), matriz()[:1])
        self.assertIn("juiz.sem_metricas", res[0]["diverge"])
        self.assertFalse(res[0]["ok"])

    def test_resposta_sem_series_diverge(self):
        res = rodar(JuizFalso(lambda r: {k: v for k, v in r.items() if k != "series"}), matriz()[:1])
        self.assertFalse(res[0]["ok"])
        self.assertIn("juiz.sem_series", res[0]["diverge"])

    def test_resposta_invalida_diverge(self):
        res = rodar(JuizFalso(lambda r: {"valido": False, "erros": ["x"]}), matriz()[:1])
        self.assertFalse(res[0]["ok"])
        self.assertEqual(res[0]["diverge"], ["juiz.invalido"])

    def test_rodar_registra_erro_e_segue(self):
        class Quebrado(JuizFalso):
            def teste(self, ag, sub, detalhe="placar", confirmar=False):
                if not self.chamadas:
                    self.chamadas.append(1)
                    raise ErroApi(403, "jogo_congelado", "x")
                return super().teste(ag, sub, detalhe)
        res = rodar(Quebrado(), matriz()[:2])
        self.assertFalse(res[0]["ok"])
        self.assertTrue(res[0]["diverge"][0].startswith("erro"))
        self.assertTrue(res[1]["ok"])

    def test_rodar_nao_imprime_no_stdout(self):
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            rodar(JuizFalso(), matriz()[:1])
        self.assertEqual(saida.getvalue(), "")

    def test_rodar_chama_callback_por_sub(self):
        vistos = []
        rodar(JuizFalso(), matriz()[:3], ao_terminar=lambda i, n, r: vistos.append((i, n, r["ok"])))
        self.assertEqual(vistos, [(1, 3, True), (2, 3, True), (3, 3, True)])


if __name__ == "__main__":
    unittest.main()
