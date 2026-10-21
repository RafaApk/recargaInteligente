"""Etapa 4: limite da agência e `divisao` (regulamento 5.3, 6.3.5, 6.3.7)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import T0  # noqa: E402

GEELY, DGS, KWID, JAC = "Geely EX2 Pro", "BYD Dolphin GS", "Renault Kwid E-Tech", "JAC E-JS1"
LIMITE_40_5 = {}  # entrada existente b3_45 (40.5 kW úteis)
LIMITE_80 = {"entrada": "a4_150", "demanda": 80}


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Divisao635(unittest.TestCase):
    """2x dc_60x2; carregador 1: Geely 30%, Dolphin GS 50%; carregador 2: Kwid 40%, JAC 75%; menor_soc."""

    def montar(self, divisao, limite):
        frota = [apoio.veiculo("geely", GEELY, soc=30.0), apoio.veiculo("dolphin", DGS, soc=50.0),
                 apoio.veiculo("kwid", KWID, soc=40.0), apoio.veiculo("jac", JAC, soc=75.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 2}, politica={"prioridade": "menor_soc", "divisao": divisao},
                        **limite)
        for vid, i in (("geely", 0), ("dolphin", 0), ("kwid", 1), ("jac", 1)):
            m.plugar(m.veiculos[vid], m.pontos[i])
        m.recalcular_potencias(T0)
        self.m = m

    def assertPot(self, esperado):
        for vid, kw in esperado.items():
            self.assertAlmostEqual(self.m.veiculos[vid].potencia_kw, kw, places=4, msg=vid)
        total = sum(v.potencia_kw for v in self.m.veiculos.values())
        self.assertLessEqual(total, self.m.limite_kw + 1e-9)

    def test_6_3_5_igual_40_5(self):
        self.montar("igual", LIMITE_40_5)
        self.assertPot({"geely": 10.125, "dolphin": 10.125, "kwid": 10.125, "jac": 10.125})

    def test_6_3_5_prioridade_40_5(self):
        self.montar("prioridade", LIMITE_40_5)
        self.assertPot({"kwid": 26.6, "geely": 13.9, "jac": 0, "dolphin": 0})

    def test_6_3_5_igual_80(self):
        self.montar("igual", LIMITE_80)
        self.assertPot({"jac": 16.45, "geely": 21.18333, "dolphin": 21.18333, "kwid": 21.18333})

    def test_6_3_5_prioridade_80(self):
        self.montar("prioridade", LIMITE_80)
        self.assertPot({"kwid": 26.6, "geely": 53.4, "jac": 0, "dolphin": 0})

    def test_plugados_ordenados(self):
        self.montar("prioridade", LIMITE_40_5)
        self.assertEqual([v.id for v in self.m._plugados_ordenados(T0)], ["kwid", "geely", "jac", "dolphin"])


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Limite(unittest.TestCase):
    def test_pico_nunca_passa_do_limite_bangkok(self):
        import simular
        for divisao in ("igual", "prioridade"):
            for prioridade in ("menor_soc", "chegada"):
                sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45",
                       "politica": {"prioridade": prioridade, "evitar_ponta": False, "divisao": divisao}}
                out = simular.avaliar(sub, {"Bangkok": apoio.base()}, apoio.RAIZ / "dados", None, [], False)
                self.assertEqual(out["violacoes"], [])
                self.assertLessEqual(out["metricas"]["pico_kw"], 40.5 + 1e-6, msg=(divisao, prioridade))

    def test_demanda_contratada_e_teto(self):
        # 4 Leapmotor a 10% em 2x dc_120x2 pediriam ~480 kW; demanda 80 segura o pico em 80
        frota = [apoio.veiculo(f"l{i}", "Leapmotor B10 BEV", soc=10.0) for i in range(4)]
        res = apoio.motor(apoio.cenario(frota), {"dc_120x2": 2}, entrada="a4_150", demanda=80).rodar()
        pico = max(res.bins.values()) * 4
        self.assertLessEqual(pico, 80 + 1e-6)
        self.assertGreater(pico, 79)


if __name__ == "__main__":
    unittest.main()
