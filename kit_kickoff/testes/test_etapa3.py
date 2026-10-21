"""Etapa 3: fila, plug, curva e fim de recarga — camada 1 (regulamento 5.2, 5.3, 6.3.2-6.3.5)."""
import heapq
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import DIA, T0  # noqa: E402
from kickoff import motor as motor_mod  # noqa: E402

GEELY, DGS, KWID, JAC = "Geely EX2 Pro", "BYD Dolphin GS", "Renault Kwid E-Tech", "JAC E-JS1"
DMINI, MG4, LEAP = "BYD Dolphin Mini GS", "MG4 Urban Comfort", "Leapmotor B10 BEV"
FOLGADO = {"entrada": "se_2000", "demanda": 1800}  # limite da agência que nunca aperta

# atendimento_pct de exemplo_submissao.json medido ao fim da etapa 2 (Task A1)
ATENDIMENTO_ETAPA2 = 8.118081180811808


def ponto(m, pid):
    return next(p for p in m.pontos if p.id == pid)


def fila_633(prioridade, contratos=()):
    """6.3.3: A Kwid 30% (fila 10:00), B Dolphin Mini 20% (10:20), C MG4 55% (10:40), D Leapmotor 40% (10:55)."""
    frota = [apoio.veiculo("A", KWID, soc=30.0), apoio.veiculo("B", DMINI, soc=20.0),
             apoio.veiculo("C", MG4, soc=55.0), apoio.veiculo("D", LEAP, soc=40.0)]
    m = apoio.motor(apoio.cenario(frota, contratos), {"ac_7": 1}, politica={"prioridade": prioridade})
    for vid, h in (("D", 655), ("B", 620), ("C", 640), ("A", 600)):  # fora de ordem de propósito
        v = m.veiculos[vid]
        v.na_fila, v.entrou_fila_t = True, DIA + h
        m.patio[vid] = v
        m.fila.append(v)
    return m


def ordem(prioridade, contratos=(), t=DIA + 660):
    m = fila_633(prioridade, contratos)
    m.ordenar_fila(t)
    return [v.id for v in m.fila]


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Recarga(unittest.TestCase):
    def test_6_3_2_dolphin_gs_20_a_80_em_36_7_min(self):
        frota = [apoio.veiculo("dgs", DGS, soc=20.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1}, **FOLGADO)
        res = m.rodar()
        self.assertAlmostEqual(apoio.fim_plug(res) - T0, 36.7, delta=0.1)
        self.assertAlmostEqual(sum(res.bins.values()), 0.6 * 44.9, places=3)
        self.assertAlmostEqual(m.veiculos["dgs"].soc, 80.0, places=9)
        self.assertFalse(m.veiculos["dgs"].plugado)

    def test_agendar_fim_degrau(self):
        frota = [apoio.veiculo("dgs", DGS, soc=22.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1}, **FOLGADO)
        v = m.veiculos["dgs"]
        v.potencia_kw = 58.35
        token = v.token
        m.agendar_fim_degrau(v, T0)
        self.assertEqual(v.soc_limite, 25.0)
        self.assertEqual(v.token, token + 1)
        t, _, _, tipo, payload = m.heap[-1]
        self.assertEqual((tipo, payload), ("fim_recarga", ("dgs", v.token)))
        self.assertAlmostEqual(t - T0, 0.03 * 44.9 / 58.35 * 60, places=9)

    def test_potencia_zero_nao_agenda(self):
        frota = [apoio.veiculo("dgs", DGS, soc=22.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1}, **FOLGADO)
        v = m.veiculos["dgs"]
        n = len(m.heap)
        m.agendar_fim_degrau(v, T0)
        self.assertEqual(len(m.heap), n)

    def test_6_3_4_escolhe_dc60(self):
        # dc_60x2 com Geely 30% plugado; ac_22x2 vazio; Dolphin GS 20% chega
        frota = [apoio.veiculo("geely", GEELY, soc=30.0), apoio.veiculo("dgs", DGS, soc=20.0),
                 apoio.veiculo("x", DGS, soc=20.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1, "ac_22x2": 1}, **FOLGADO)
        m.plugar(m.veiculos["geely"], ponto(m, "dc_60x2-0"))
        dgs = m.veiculos["dgs"]
        self.assertEqual(m.escolher_ponto(dgs).modelo.id, "dc_60x2")
        m.plugar(dgs, ponto(m, "dc_60x2-0"))
        self.assertEqual(m.escolher_ponto(m.veiculos["x"]).modelo.id, "ac_22x2")

    def test_empate_primeiro_ponto(self):
        frota = [apoio.veiculo("a", GEELY, soc=30.0)]
        m = apoio.motor(apoio.cenario(frota), {"ac_7": 2}, **FOLGADO)
        self.assertEqual(m.escolher_ponto(m.veiculos["a"]).id, "ac_7-0")

    def test_sem_saida_livre(self):
        frota = [apoio.veiculo("a", GEELY, soc=30.0), apoio.veiculo("b", GEELY, soc=30.0)]
        m = apoio.motor(apoio.cenario(frota), {"ac_7": 1}, **FOLGADO)
        m.plugar(m.veiculos["a"], m.pontos[0])
        self.assertIsNone(m.escolher_ponto(m.veiculos["b"]))

    def test_sobra_do_carregador_vai_para_o_outro(self):  # Review Focus 3
        # dc_60x2 com JAC 75% (curva DC 16.45) e Geely 30% (71.5): Geely recebe 60 - 16.45
        frota = [apoio.veiculo("jac", JAC, soc=75.0), apoio.veiculo("geely", GEELY, soc=30.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1}, **FOLGADO)
        for vid in ("jac", "geely"):
            m.plugar(m.veiculos[vid], m.pontos[0])
        m.recalcular_potencias(T0)
        self.assertAlmostEqual(m.veiculos["geely"].potencia_kw, 43.55, places=6)
        self.assertAlmostEqual(m.veiculos["jac"].potencia_kw, 16.45, places=6)

    def test_carro_no_alvo_nao_divide(self):
        # carro a 80% plugado (segurando saída) não leva parte da potência do carregador
        frota = [apoio.veiculo("cheio", GEELY, soc=80.0), apoio.veiculo("geely", GEELY, soc=30.0)]
        m = apoio.motor(apoio.cenario(frota), {"dc_60x2": 1}, **FOLGADO)
        for vid in ("cheio", "geely"):
            m.plugar(m.veiculos[vid], m.pontos[0])
        m.recalcular_potencias(T0)
        self.assertEqual(m.veiculos["cheio"].potencia_kw, 0.0)
        self.assertAlmostEqual(m.veiculos["geely"].potencia_kw, 60.0, places=9)

    def test_plugados_nunca_passam_das_saidas(self):
        frota = [apoio.veiculo(f"v{i}", GEELY, soc=10.0 + i) for i in range(5)]
        m = apoio.motor(apoio.cenario(frota), {"ac_22x2": 1}, **FOLGADO)
        res = m.rodar()
        self.assertEqual(res.violacoes, [])
        self.assertLessEqual(max(n for _, n, _ in res.trace), 2)
        self.assertTrue(all(m.veiculos[f"v{i}"].soc >= 80 - 1e-9 for i in range(5)))

    def _fila_t0(self):
        # 3 carros na fila em T0 (agência aberta), 1 saída, menor_soc
        frota = [apoio.veiculo("a", GEELY, soc=60.0), apoio.veiculo("b", GEELY, soc=20.0),
                 apoio.veiculo("c", GEELY, soc=40.0)]
        return apoio.motor(apoio.cenario(frota), {"ac_7": 1}, **FOLGADO)

    def test_fila_t0_em_lote_pluga_na_ordem_da_politica(self):
        # PLUG_T0_EM_LOTE=True (padrão, leitura de 6.3.3 ainda não confirmada no juiz):
        # a fila de T0 é plugada de uma vez, na ordem da política -> o de menos km
        with mock.patch.object(motor_mod, "PLUG_T0_EM_LOTE", True):
            m = self._fila_t0()
            m._agendar_inicio()
            self.assertEqual(m.pontos[0].conectados, [])  # nada pluga durante a montagem de T0
            while m.heap and m.heap[0][0] == T0:
                t, _, _, tipo, _ = heapq.heappop(m.heap)
                if tipo == "abertura":
                    m.on_abertura(t)
        self.assertEqual([v.id for v in m.pontos[0].conectados], ["b"])
        self.assertEqual([v.id for v in m.fila], ["c", "a"])

    def test_fila_t0_carro_a_carro_pluga_em_ordem_de_id(self):
        # PLUG_T0_EM_LOTE=False (leitura literal do esqueleto): _agendar_inicio chama entrar_patio
        # carro a carro em ordem de id, e cada um pluga se houver saída -> o menor id leva a saída
        with mock.patch.object(motor_mod, "PLUG_T0_EM_LOTE", False):
            m = self._fila_t0()
            m._agendar_inicio()
        self.assertEqual([v.id for v in m.pontos[0].conectados], ["a"])
        self.assertEqual([v.id for v in m.fila], ["b", "c"])
        self.assertFalse(any(tipo == "abertura" and t == T0 for t, _, _, tipo, _ in m.heap))

    def test_alvo_com_evento_simultaneo_despluga(self):
        # Fix I1: o fim de degrau de outro carro no mesmo instante recalcula antes; o carro que chega a
        # 80% não pode ficar plugado com a agência aberta (5.2). Geely a 6.6 kW num ac_7: degraus de
        # 5% em 17.73 min, então carros com SOC defasado em múltiplos de 5% trocam de degrau juntos.
        geely_10pct = 0.10 * 39.0 / 6.6 * 60  # 70% -> 80%
        # em lote (menor_soc): c 30% e a 70% plugam, b espera e entra no lugar de a (seguem 2 plugados);
        # carro a carro (id): os gêmeos a e b chegam a 80% juntos, c entra num lugar e o outro fica livre
        for lote, fim_espera, plugados in ((True, 0.10, 2), (False, 0.50, 1)):
            with self.subTest(PLUG_T0_EM_LOTE=lote), mock.patch.object(motor_mod, "PLUG_T0_EM_LOTE", lote):
                frota = [apoio.veiculo("a", GEELY, soc=70.0), apoio.veiculo("b", GEELY, soc=70.0),
                         apoio.veiculo("c", GEELY, soc=30.0)]
                m = apoio.motor(apoio.cenario(frota), {"ac_7": 2}, **FOLGADO)
                res = m.rodar()
                self.assertTrue(all(not v.plugado for v in m.veiculos.values()))
                self.assertTrue(all(abs(v.soc - 80.0) < 1e-9 for v in m.veiculos.values()))
                # quem esperava pluga no instante em que o primeiro chega a 80%
                t_plug = next(t for t, n, f in res.trace if t > T0 and f == 0)
                self.assertAlmostEqual(t_plug, T0 + geely_10pct, places=6)
                self.assertEqual([n for t, n, f in res.trace if t == t_plug][-1], plugados)
                # e a recarga dele (b de 70%, ou c de 30%) termina contando a partir daí
                quedas = [t for (_, n0, _), (t, n1, _) in zip(res.trace, res.trace[1:]) if n1 < n0]
                fim = t_plug + fim_espera * 39.0 / 6.6 * 60
                self.assertTrue(any(abs(t - fim) < 1e-6 for t in quedas), (quedas, fim))

    def test_fim_de_recarga_e_retirada_no_mesmo_minuto(self):
        # 5.1: fim de recarga antes da retirada. Dolphin Plus 70% num ac_11 chega a 80% em T0 + 33.0
        for ret, atendido in ((T0 + 33, True), (T0 + 32, False)):
            with self.subTest(retirada=ret):
                frota = [apoio.veiculo("dp", "BYD Dolphin Plus", soc=70.0)]
                res = apoio.motor(apoio.cenario(frota, [apoio.contrato("c1", "Diamante", ret)]), {"ac_11": 1}).rodar()
                self.assertEqual(len(res.retiradas), int(atendido))
                if atendido:
                    self.assertAlmostEqual(res.retiradas[0].soc, 80.0, places=9)


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Fila(unittest.TestCase):
    def test_6_3_3_chegada_e_menor_soc(self):
        self.assertEqual(ordem("chegada"), ["A", "B", "C", "D"])
        self.assertEqual(ordem("menor_soc"), ["A", "B", "D", "C"])

    def test_chegada_empate_pelo_id(self):
        m = fila_633("chegada")
        for v in m.fila:
            v.entrou_fila_t = T0
        m.ordenar_fila(DIA)
        self.assertEqual([v.id for v in m.fila], ["A", "B", "C", "D"])

    def test_fechada_nao_pluga(self):
        m = fila_633("menor_soc")
        m.aberta = False
        m.plugar_fila(DIA + 660)
        self.assertEqual(len(m.fila), 4)
        m.aberta = True
        m.plugar_fila(DIA + 660)
        self.assertEqual([v.id for v in m.fila], ["B", "D", "C"])
        self.assertEqual([v.id for v in m.pontos[0].conectados], ["A"])


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class Bangkok(unittest.TestCase):
    def test_bangkok_sem_violacao_e_atendimento_sobe(self):
        import simular
        sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45",
               "politica": {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}}
        out = simular.avaliar(sub, {"Bangkok": apoio.base()}, apoio.RAIZ / "dados", None, [], False)
        self.assertEqual(out["violacoes"], [])
        self.assertGreater(out["metricas"]["atendimento_pct"], ATENDIMENTO_ETAPA2)


if __name__ == "__main__":
    unittest.main()
