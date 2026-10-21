"""Etapa 2: retirada e devolução (regulamento 4.1, 5.1, 6.3.1)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import DIA, T0  # noqa: E402

GEELY, DMINI, MG4, JAC = "Geely EX2 Pro", "BYD Dolphin Mini GS", "MG4 Urban Comfort", "JAC E-JS1"


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Escolha631(unittest.TestCase):
    """6.3.1: contrato Prata; pátio montado à mão em m.patio."""

    def escolher(self, geely_soc=82.0, sem_prata=False):
        frota = [apoio.veiculo("geely", GEELY, "estoque_pronto", geely_soc),
                 apoio.veiculo("dmini", DMINI, "estoque_pronto", 95.0),
                 apoio.veiculo("mg4", MG4, "estoque_pronto", 100.0),
                 apoio.veiculo("jac", JAC, "estoque_pronto", 100.0)]
        if sem_prata:
            frota = [v for v in frota if v.categoria != "Prata"]
        c = apoio.contrato("c1", "Prata", DIA + 600)
        m = apoio.motor(apoio.cenario(frota, [c]), {"ac_22x2": 1})
        for vt in frota:
            m.patio[vt.id] = m.veiculos[vt.id]
        if "dmini" in m.patio:
            m.patio["dmini"].plugado = True
        return m.escolher_carro(c, c.retirada_t)

    def test_6_3_1_sai_geely(self):
        self.assertEqual(self.escolher().id, "geely")

    def test_6_3_1_geely_78_sai_dolphin_mini(self):
        self.assertEqual(self.escolher(geely_soc=78.0).id, "dmini")

    def test_6_3_1_sem_prata_sai_mg4(self):
        self.assertEqual(self.escolher(sem_prata=True).id, "mg4")

    def test_downgrade_nunca(self):
        c = apoio.contrato("c1", "Ouro", DIA + 600)
        frota = [apoio.veiculo("jac", JAC, "estoque_pronto", 100.0)]
        m = apoio.motor(apoio.cenario(frota, [c]), {"ac_7": 1})
        m.patio["jac"] = m.veiculos["jac"]
        self.assertIsNone(m.escolher_carro(c, c.retirada_t))

    def test_desempate_nao_plugado_e_id(self):
        frota = [apoio.veiculo(i, GEELY, "estoque_pronto", 80.0) for i in ("g3", "g1", "g2")]
        c = apoio.contrato("c1", "Prata", DIA + 600)
        m = apoio.motor(apoio.cenario(frota, [c]), {"ac_7": 1})
        for vt in frota:
            m.patio[vt.id] = m.veiculos[vt.id]
        m.patio["g1"].plugado = True
        self.assertEqual(m.escolher_carro(c, c.retirada_t).id, "g2")


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Devolucao(unittest.TestCase):
    def test_soc_devolucao_km_sobre_autonomia_com_teto(self):
        # Geely (289 km) sai a 80%: 144.5 km -> 50%; 300 km -> teto 80
        frota = [apoio.veiculo("geely", GEELY, "estoque_pronto", 80.0)]
        m = apoio.motor(apoio.cenario(frota), {"ac_7": 1})
        v = m.veiculos["geely"]
        self.assertAlmostEqual(m.soc_devolucao(v, apoio.contrato("c", "Prata", T0, T0 + 60, 144.5)), 50.0)
        self.assertAlmostEqual(m.soc_devolucao(v, apoio.contrato("c", "Prata", T0, T0 + 60, 300)), 80.0)

    def test_devolvido_apto_sai_no_mesmo_minuto(self):  # Review Focus 1
        t = DIA + 600
        frota = [apoio.veiculo("geely", GEELY, "em_contrato", devolucao_t=t, soc_devolucao=90.0)]
        res = apoio.motor(apoio.cenario(frota, [apoio.contrato("c1", "Prata", t)]), {"ac_7": 1}).rodar()
        self.assertEqual(len(res.retiradas), 1)
        self.assertEqual(res.nao_atendidos, [])
        self.assertEqual(res.retiradas[0].veiculo_id, "geely")

    def test_retirada_devolve_e_sai_de_novo(self):
        # sai a 90%, volta com 144.5 km (50%) às 12:00: entra na fila; contrato das 12:00 não tem carro
        frota = [apoio.veiculo("geely", GEELY, "estoque_pronto", 90.0)]
        cs = [apoio.contrato("c1", "Prata", DIA + 600, DIA + 720, 144.5), apoio.contrato("c2", "Prata", DIA + 720)]
        m = apoio.motor(apoio.cenario(frota, cs), {"ac_7": 1})
        res = m.rodar()
        self.assertEqual([r.contrato_id for r in res.retiradas], ["c1"])
        self.assertEqual(res.nao_atendidos, [DIA + 720])

    def test_estoque_abaixo_80_nao_sai(self):
        frota = [apoio.veiculo("geely", GEELY, "estoque_a_carregar", 50.0)]
        res = apoio.motor(apoio.cenario(frota, [apoio.contrato("c1", "Prata", T0 + 1)]), {"ac_7": 1}).rodar()
        self.assertEqual(len(res.nao_atendidos), 1)
        self.assertEqual(res.retiradas, [])

    def test_abaixo_de_80_entra_na_fila(self):
        frota = [apoio.veiculo("a", GEELY, "estoque_a_carregar", 50.0),
                 apoio.veiculo("b", GEELY, "estoque_pronto", 80.0)]
        m = apoio.motor(apoio.cenario(frota, horario=[None] * 7), {"ac_7": 1})
        m.rodar()
        self.assertTrue(m.veiculos["a"].na_fila)
        self.assertEqual(m.veiculos["a"].entrou_fila_t, T0)
        self.assertFalse(m.veiculos["b"].na_fila)
        self.assertEqual(set(m.patio), {"a", "b"})


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Bangkok(unittest.TestCase):
    def test_retiradas_aptas(self):
        import simular
        cen = apoio.base()
        sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45"}
        out = simular.avaliar(sub, {"Bangkok": cen}, apoio.RAIZ / "dados", None, [], False)
        self.assertGreater(out["metricas"]["atendimento_pct"], 0)
        from kickoff import motor, validar
        res = motor.simular(cen, validar.normalizar(sub, cen))
        for r in res.retiradas:
            self.assertGreaterEqual(r.soc, 80 - 1e-9)
            self.assertGreaterEqual(r.rank_entregue, r.rank_pedido)


if __name__ == "__main__":
    unittest.main()
