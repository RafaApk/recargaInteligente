"""Etapa 5: horário de funcionamento e `evitar_ponta` (regulamento 5.2, 5.3, 6.3.6)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import DIA  # noqa: E402
from kickoff import medicao, tempo  # noqa: E402

MG4, GEELY = "MG4 Urban Comfort", "Geely EX2 Pro"
SEG_17H = DIA + 17 * 60  # segunda 18/10 17:00 = minuto 2460
TER_08H = 2 * DIA + 8 * 60  # terça 19/10 08:00 = minuto 3360
COMERCIAL = [(8 * 60, 18 * 60)] * 5 + [None, None]  # seg-sex 08:00-18:00


def mg4_29(evitar_ponta=False, horario=None, devolucao_t=SEG_17H, carregadores=None, extra=()):
    frota = [apoio.veiculo("mg4", MG4, "em_contrato", devolucao_t=devolucao_t, soc_devolucao=29.0), *extra]
    m = apoio.motor(apoio.cenario(frota, horario=horario), carregadores or {"ac_22x2": 1},
                    politica={"evitar_ponta": evitar_ponta})
    res = m.rodar()
    return m, res, medicao.metricas(res.retiradas, res.nao_atendidos, res.bins, *tempo.JANELA_PUBLICA)


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Ponta636(unittest.TestCase):
    def test_6_3_6_sem_evitar_ponta_termina_19h(self):
        _, res, m = mg4_29()
        self.assertAlmostEqual(apoio.fim_plug(res, SEG_17H), SEG_17H + 120, delta=3)
        self.assertAlmostEqual(m["energia_ponta_kwh"], 11.0, delta=0.3)

    def test_6_3_6_com_evitar_ponta_termina_22h(self):
        mot, res, m = mg4_29(evitar_ponta=True)
        self.assertAlmostEqual(apoio.fim_plug(res, SEG_17H), SEG_17H + 300, delta=3)
        self.assertEqual(m["energia_ponta_kwh"], 0.0)
        self.assertAlmostEqual(m["energia_kwh"], 0.51 * 43.0, places=6)
        self.assertAlmostEqual(mot.veiculos["mg4"].soc, 80.0, places=9)

    def test_na_ponta_pluga_a_zero_kw(self):
        # devolvido às 18:30 com evitar_ponta: pluga na hora, só carrega a partir das 21:00
        _, res, m = mg4_29(evitar_ponta=True, devolucao_t=SEG_17H + 90)
        plug = [(t, n) for t, n, _ in res.trace if t >= SEG_17H + 90]
        self.assertEqual(plug[0], (SEG_17H + 90, 1))
        self.assertEqual(m["energia_ponta_kwh"], 0.0)
        self.assertAlmostEqual(apoio.fim_plug(res, SEG_17H), SEG_17H + 240 + 51 * 0.43 / 11 * 60, delta=0.5)

    def test_6_3_6_fecha_20h_retirada_19h30(self):
        # 6.3.6: agência que fecha às 20:00, retirada Ouro às 19:30. Sem evitar_ponta o MG4 (17:00, 29%)
        # está pronto às ~19:00 e sai; com evitar_ponta está perto de 55% e o cliente é perdido
        ate_20h = [(8 * 60, 20 * 60)] * 7
        ret = SEG_17H + 150
        for evitar, atendido in ((False, True), (True, False)):
            with self.subTest(evitar_ponta=evitar):
                frota = [apoio.veiculo("mg4", MG4, "em_contrato", devolucao_t=SEG_17H, soc_devolucao=29.0)]
                cen = apoio.cenario(frota, [apoio.contrato("c1", "Ouro", ret)], horario=ate_20h)
                mot = apoio.motor(cen, {"ac_22x2": 1}, politica={"evitar_ponta": evitar})
                res = mot.rodar()
                if atendido:
                    self.assertEqual([(r.veiculo_id, r.t) for r in res.retiradas], [("mg4", ret)])
                    self.assertAlmostEqual(res.retiradas[0].soc, 80.0, places=9)
                else:
                    self.assertEqual(res.nao_atendidos, [ret])
                    self.assertAlmostEqual(mot.veiculos["mg4"].soc, 80.0, places=9)
                    # termina às ~22:00 com a agência fechada e segura a saída até 08:00 de terça
                    self.assertEqual(apoio.fim_plug(res, SEG_17H), TER_08H)

    def test_sabado_sem_ponta(self):
        sab_17h = 6 * DIA + 17 * 60
        _, res, _ = mg4_29(evitar_ponta=True, devolucao_t=sab_17h)
        self.assertAlmostEqual(apoio.fim_plug(res, sab_17h), sab_17h + 51 * 0.43 / 11 * 60, delta=0.5)


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Horario(unittest.TestCase):
    def test_80_com_agencia_fechada_segura_saida(self):  # Review Focus 2
        # seg-sex 08:00-18:00; chega a 80% às ~19:00 fechada: segue plugado até terça 08:00
        mot, res, _ = mg4_29(horario=COMERCIAL)
        self.assertEqual(apoio.fim_plug(res, SEG_17H), TER_08H)
        self.assertAlmostEqual(mot.veiculos["mg4"].soc, 80.0, places=9)  # parado no alvo: não passa de 80

    def test_saida_segura_so_libera_na_abertura(self):  # Review Focus 2
        # 1 saída (ac_7): MG4 chega a 80% fechada; o Geely (fila desde 17:30) só pluga na abertura
        geely = apoio.veiculo("geely", GEELY, "em_contrato", devolucao_t=SEG_17H + 30, soc_devolucao=50.0)
        mot, res, m = mg4_29(horario=COMERCIAL, carregadores={"ac_7": 1}, extra=[geely])
        antes = sum(e for i, e in res.bins.items() if 15 * i < TER_08H)
        self.assertAlmostEqual(antes, 0.51 * 43.0, places=6)  # só o MG4 carregou antes da abertura
        self.assertAlmostEqual(m["energia_kwh"], 0.51 * 43.0 + 0.30 * 39.0, places=6)
        self.assertEqual([(t, n) for t, n, _ in res.trace if t == TER_08H][-1], (TER_08H, 1))
        self.assertAlmostEqual(apoio.fim_plug(res, TER_08H), TER_08H + 0.30 * 39.0 / 6.6 * 60, delta=0.01)

    def test_fechada_nao_pluga(self):
        # devolvido às 19:00 (fechada) só pluga na abertura seguinte
        _, res, _ = mg4_29(horario=COMERCIAL, devolucao_t=SEG_17H + 120)
        self.assertTrue(all(n == 0 for t, n, _ in res.trace if t < TER_08H))
        self.assertIn((TER_08H, 1, 0), res.trace)

    def test_recarga_continua_fechada(self):
        # pluga às 17:00 e a agência fecha às 18:00: a energia continua entrando até 80%
        _, res, m = mg4_29(horario=COMERCIAL)
        self.assertAlmostEqual(m["energia_kwh"], 0.51 * 43.0, places=6)
        fechada = sum(e for i, e in res.bins.items() if SEG_17H + 60 <= 15 * i < TER_08H)
        self.assertGreater(fechada, 10.0)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class EventoCorte(unittest.TestCase):
    def test_corte_reduz_limite_na_janela(self):
        # juiz em Marrakech: demanda 110 kW, corte 0.7 -> potência travada em 77 kW na janela
        cen = apoio.cenario([apoio.veiculo(f"V{i}", "MG4 Urban Comfort", soc=10.0) for i in range(4)])
        m = apoio.motor(cen, {"ac_22x2": 2}, entrada="a4_150", demanda=30, eventos=[["corte", "Teste", 1200, 1300, 0.5]])
        res = m.rodar()
        self.assertAlmostEqual(max(e for i, e in res.bins.items() if 1200 <= i * 15 and i * 15 + 15 <= 1300) * 4, 15.0, places=6)
        self.assertAlmostEqual(max(e for i, e in res.bins.items() if 1320 <= i * 15 < 1500) * 4, 30.0, places=6)
