import contextlib
import io
import json
import unittest
from unittest import mock

from recarga import otimizador, robustez


def cand(nome, semanas):
    return {"hash": nome, "sub": {"nome": nome}, "semanas": [{"v": v} for v in semanas]}


def por_v(m, sub):
    return m["v"]


class Escolher(unittest.TestCase):
    def test_prefere_melhor_pior_semana(self):
        a, b = cand("A", [10, 10, 10, 2]), cand("B", [8, 8, 8, 8])
        self.assertIs(robustez.escolher([a, b], por_v), b)

    def test_desempate_pela_media(self):
        a, b = cand("A", [5, 6, 6, 6]), cand("B", [5, 9, 9, 9])
        self.assertIs(robustez.escolher([a, b], por_v), b)

    def test_empate_total_fica_com_o_primeiro_do_ranking(self):
        a, b = cand("A", [5, 5, 5, 5]), cand("B", [5, 5, 5, 5])
        self.assertIs(robustez.escolher([a, b], por_v), a)

    def test_so_considera_top(self):
        ranking = [cand(str(i), [5, 5, 5, 5]) for i in range(10)] + [cand("fora", [100] * 4)]
        self.assertEqual(robustez.escolher(ranking, por_v)["hash"], "0")
        self.assertEqual(robustez.escolher(ranking, por_v, top=11)["hash"], "fora")

    def test_obj_recebe_sub(self):
        visto = []
        robustez.escolher([cand("A", [1, 2, 3, 4])], lambda m, s: visto.append(s) or 0)
        self.assertEqual(visto, [{"nome": "A"}] * 4)

    def test_ranking_vazio(self):
        with self.assertRaises(ValueError):
            robustez.escolher([], por_v)


class Cli(unittest.TestCase):
    def test_cli_imprime_a_escolha_robusta(self):
        a = {**cand("A", [10, 10, 10, 2]), "envio": {"carregadores": {"ac_7": 1}}, "valor": 9}
        b = {**cand("B", [8, 8, 8, 8]), "envio": {"carregadores": {"dc_30": 1}}, "valor": 8}
        out = io.StringIO()
        with mock.patch.object(otimizador, "buscar", return_value=[a, b]), \
                mock.patch.object(otimizador, "objetivo_semana_padrao", return_value=por_v), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            otimizador.main(["Bangkok"])
        self.assertEqual(json.loads(out.getvalue()), b["envio"])


if __name__ == "__main__":
    unittest.main()
