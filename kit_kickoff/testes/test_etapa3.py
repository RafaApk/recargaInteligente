"""Etapa 3: fila, plug, curva e fim de recarga — camada 1 (regulamento 5.2, 5.3, 6.3.2-6.3.5)."""
import heapq
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import DIA, T0  # noqa: E402

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

    def test_fila_t0_plugada_na_ordem_da_politica(self):
        # 3 carros na fila em T0, 1 saída: pluga o de menos km (menor_soc), não o menor id
        frota = [apoio.veiculo("a", GEELY, soc=60.0), apoio.veiculo("b", GEELY, soc=20.0),
                 apoio.veiculo("c", GEELY, soc=40.0)]
        m = apoio.motor(apoio.cenario(frota), {"ac_7": 1}, **FOLGADO)
        m._agendar_inicio()
        self.assertEqual(m.pontos[0].conectados, [])  # nada pluga durante a montagem de T0
        while m.heap and m.heap[0][0] == T0:
            t, _, _, tipo, _ = heapq.heappop(m.heap)
            if tipo == "abertura":
                m.on_abertura(t)
        self.assertEqual([v.id for v in m.pontos[0].conectados], ["b"])
        self.assertEqual([v.id for v in m.fila], ["c", "a"])


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
