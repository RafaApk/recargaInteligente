"""Etapa 6: `prioridade` proxima_retirada (regulamento 6.3.3)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apoio  # noqa: E402
from apoio import DIA  # noqa: E402
from test_etapa3 import fila_633  # noqa: E402

ONZE = DIA + 11 * 60  # segunda 18/10 11:00


def contratos_633():
    """Próximos contratos ainda não retirados: 12:30 Ouro, 13:15 Prata, 14:00 Bronze (18/10)."""
    return [apoio.contrato("c1230", "Ouro", DIA + 750), apoio.contrato("c1315", "Prata", DIA + 795),
            apoio.contrato("c1400", "Bronze", DIA + 840)]


def ids(m):
    return [v.id for v in m.fila]


@unittest.skipUnless(apoio.TEM_DADOS, apoio.SEM_DADOS)
class ProximaRetirada(unittest.TestCase):
    def test_6_3_3_proxima_retirada(self):
        m = fila_633("proxima_retirada", contratos_633())
        m.ordenar_fila(ONZE)
        self.assertEqual(ids(m), ["C", "D", "B", "A"])

    def test_reserva_avanca_depois_da_retirada(self):
        m = fila_633("proxima_retirada", contratos_633())
        self.assertEqual(m._proxima_reserva(3), DIA + 750)
        m.on_retirada("c1230", DIA + 750)  # ninguém apto: contrato perdido, mas já processado
        self.assertEqual(m.nao_atendidos, [DIA + 750])
        self.assertEqual(m._proxima_reserva(3), DIA + 795)
        self.assertEqual(m._proxima_reserva(4), DIA + 795)
        self.assertEqual(m._proxima_reserva(2), DIA + 795)
        self.assertEqual(m._proxima_reserva(1), DIA + 840)
        m.ordenar_fila(DIA + 760)
        self.assertEqual(ids(m), ["C", "D", "B", "A"])  # C, D e B empatam em 13:15: maior SOC primeiro

    def test_sem_reserva_vai_para_o_fim(self):
        m = fila_633("proxima_retirada", [apoio.contrato("c1230", "Ouro", DIA + 750)])
        m.ordenar_fila(ONZE)
        self.assertEqual(ids(m), ["C", "D", "A", "B"])  # A e B sem reserva: maior SOC primeiro
        m.on_retirada("c1230", DIA + 750)
        self.assertIsNone(m._proxima_reserva(4))

    def test_divisao_prioridade_usa_proxima_retirada(self):
        m = fila_633("proxima_retirada", contratos_633())
        self.assertEqual([v.id for v in sorted(m.fila, key=lambda v: m._chave_prioridade(v, ONZE))],
                         ["C", "D", "B", "A"])

    def test_bangkok_tres_prioridades(self):
        import simular
        for pr in ("menor_soc", "chegada", "proxima_retirada"):
            for div in ("igual", "prioridade"):
                sub = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45",
                       "politica": {"prioridade": pr, "divisao": div}}
                out = simular.avaliar(sub, {"Bangkok": apoio.base()}, apoio.RAIZ / "dados", None, [], False)
                self.assertEqual(out["violacoes"], [], msg=(pr, div))
                self.assertLessEqual(out["metricas"]["pico_kw"], 40.5 + 1e-6, msg=(pr, div))


if __name__ == "__main__":
    unittest.main()
