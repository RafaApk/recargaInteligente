import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import recarga  # noqa: F401  (põe o kit no sys.path)
from recarga import lote

EXEMPLO = json.loads((recarga.KIT / "exemplo_submissao.json").read_text(encoding="utf-8"))


class ComCacheTemporario(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(lote, "CACHE", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)


class Lote(ComCacheTemporario):
    def test_semanas_somam_publico(self):
        r = lote.avaliar("Bangkok", EXEMPLO)
        self.assertEqual(len(r["semanas"]), 4)
        self.assertEqual(sum(s["contratos"] for s in r["semanas"]), r["metricas"]["contratos"])
        self.assertIn("demanda_contratada_kw", r["metricas"])
        for s in r["semanas"]:
            self.assertIn("demanda_contratada_kw", s)

    def test_campos(self):
        r = lote.avaliar("Bangkok", EXEMPLO)
        for k in ("hash", "sub", "valido", "erros", "violacoes", "metricas", "semanas"):
            self.assertIn(k, r)
        self.assertTrue(r["valido"])
        self.assertEqual(r["sub"]["politica"], EXEMPLO["politica"])
        self.assertEqual(len(r["hash"]), 64)
        self.assertNotIn("series", r)

    def test_cache_em_disco(self):
        with mock.patch.object(lote.motor, "simular", wraps=lote.motor.simular) as sim:
            a = lote.avaliar("Bangkok", EXEMPLO)
            b = lote.avaliar("Bangkok", EXEMPLO)
        self.assertEqual(sim.call_count, 1)
        self.assertEqual(a, b)
        self.assertTrue((self.tmp / "Bangkok" / f"{a['hash']}.json").exists())

    def test_equivalentes_mesmo_hash(self):
        a = lote.avaliar("Bangkok", {**EXEMPLO, "carregadores": {"dc_30": 1, "ac_7": 2, "ac_11": 0}})
        b = lote.avaliar("Bangkok", EXEMPLO)
        self.assertEqual(a["hash"], b["hash"])

    def test_series_sob_pedido(self):
        r = lote.avaliar("Bangkok", EXEMPLO, series=True)
        self.assertIn("potencia_kw", r["series"])
        self.assertNotIn("series", lote.avaliar("Bangkok", EXEMPLO))

    def test_lote_paralelo_igual_sequencial(self):
        subs = [EXEMPLO, {**EXEMPLO, "politica": {"prioridade": "chegada"}}]
        par = lote.avaliar_lote("Bangkok", subs, processos=2)
        shutil.rmtree(self.tmp / "Bangkok")
        self.assertEqual([r["metricas"] for r in par],
                         [lote.avaliar("Bangkok", s)["metricas"] for s in subs])

    def test_lote_mantem_ordem_e_invalidas(self):
        ruim = {**EXEMPLO, "entrada": "xyz"}
        subs = [ruim, EXEMPLO, ruim, {**EXEMPLO, "politica": {"divisao": "prioridade"}}, EXEMPLO]
        rs = lote.avaliar_lote("Bangkok", subs, processos=2)
        self.assertEqual([r["valido"] for r in rs], [False, True, False, True, True])
        self.assertEqual(rs[1]["hash"], rs[4]["hash"])
        self.assertNotEqual(rs[1]["hash"], rs[3]["hash"])

    def test_invalida_nao_simula(self):
        with mock.patch.object(lote.motor, "simular") as sim:
            r = lote.avaliar("Bangkok", {**EXEMPLO, "carregadores": {}})
        sim.assert_not_called()
        self.assertFalse(r["valido"])
        self.assertTrue(r["erros"])
        self.assertNotIn("metricas", r)

    def test_cache_de_outro_motor_e_refeito(self):
        a = lote.avaliar("Bangkok", EXEMPLO)
        arq = self.tmp / "Bangkok" / f"{a['hash']}.json"
        velho = json.loads(arq.read_text(encoding="utf-8"))
        velho["versao_motor"] = "outra"
        arq.write_text(json.dumps(velho), encoding="utf-8")
        with mock.patch.object(lote.motor, "simular", wraps=lote.motor.simular) as sim:
            lote.avaliar("Bangkok", EXEMPLO)
        self.assertEqual(sim.call_count, 1)


if __name__ == "__main__":
    unittest.main()
