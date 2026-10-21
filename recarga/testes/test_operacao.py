import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from kickoff.api import ErroApi
from recarga.operacao import Monitor


def status(fase="neblina", agencias=("Bangkok",), eventos=(), cartas=()):
    return {"fase": fase, "saldo": 1000,
            "agencias": {a: {"aberta": True, "envios": 0} for a in agencias},
            "cartas": list(cartas), "eventos_ativos": list(eventos)}


class JuizFalso:
    def __init__(self, *sequencia):
        self.sequencia = list(sequencia)
        self.kits, self.catalogos, self.placares = [], 0, 0
        self.status_chamadas = 0

    def status(self):
        self.status_chamadas += 1
        r = self.sequencia[min(self.status_chamadas - 1, len(self.sequencia) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    def kit(self, ag):
        self.kits.append(ag)
        return Path("x") / ag

    def catalogo(self):
        self.catalogos += 1
        return {"carregadores": [{"id": "ac_7", "custo": 3}], "pesos": {}}

    def placar(self):
        self.placares += 1
        return {"fase": "neblina", "equipes": [{"posicao": 1, "nome": "nós", "nota": 1.5}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.dados = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.dados, ignore_errors=True)

    def monitor(self, *sequencia):
        self.juiz = JuizFalso(*sequencia)
        return Monitor(self.juiz, raiz=self.raiz, dados=self.dados)

    def passo(self, mon, agora):
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            alertas = mon.passo(agora)
        return alertas, saida.getvalue()


class Monitoramento(Base):
    def test_agencia_nova_baixa_kit(self):
        mon = self.monitor(status(agencias=("Bangkok",)), status(agencias=("Bangkok", "Tokyo")))
        self.passo(mon, 0)
        self.juiz.kits.clear()
        alertas, saida = self.passo(mon, 60)
        self.assertEqual(self.juiz.kits, ["Tokyo"])
        self.assertTrue(any("Tokyo" in a for a in alertas))
        self.assertIn("\a", saida)
        self.passo(mon, 120)  # mesma lista: não baixa de novo
        self.assertEqual(self.juiz.kits, ["Tokyo"])

    def test_kit_ja_local_nao_rebaixa(self):
        (self.dados / "Tokyo").mkdir()
        (self.dados / "Tokyo" / "agencias.md").write_text("x", encoding="utf-8")
        mon = self.monitor(status(agencias=("Bangkok",)), status(agencias=("Bangkok", "Tokyo")))
        self.passo(mon, 0)
        alertas, _ = self.passo(mon, 60)
        self.assertNotIn("Tokyo", self.juiz.kits)
        self.assertTrue(any("Tokyo" in a for a in alertas))

    def test_primeira_rodada_baixa_kit_do_que_falta(self):
        mon = self.monitor(status(agencias=("Bangkok", "Tokyo")))
        self.passo(mon, 0)
        self.assertEqual(sorted(self.juiz.kits), ["Bangkok", "Tokyo"])

    def test_estado_anterior_vem_do_status_json_em_disco(self):
        self.raiz.mkdir(exist_ok=True)
        (self.raiz / "status.json").write_text(json.dumps(status(agencias=("Bangkok",))), encoding="utf-8")
        (self.dados / "Bangkok").mkdir()
        (self.dados / "Bangkok" / "agencias.md").write_text("x", encoding="utf-8")
        mon = self.monitor(status(agencias=("Bangkok", "Tokyo")))
        alertas, _ = self.passo(mon, 0)
        self.assertEqual(self.juiz.kits, ["Tokyo"])
        self.assertTrue(any("Tokyo" in a for a in alertas))

    def test_evento_novo_grava_eventos_json(self):
        ev = [{"agencia": "Bangkok", "params": [1, "Bangkok", 2000, 3000]}]
        mon = self.monitor(status(), status(eventos=ev))
        self.passo(mon, 0)
        alertas, _ = self.passo(mon, 60)
        self.assertEqual(json.loads((self.raiz / "eventos.json").read_text(encoding="utf-8")), ev)
        self.assertTrue(any("evento" in a.lower() for a in alertas))

    def test_evento_repetido_nao_alerta(self):
        ev = [{"agencia": "Bangkok", "params": [1, "Bangkok", 2000, 3000]}]
        mon = self.monitor(status(eventos=ev), status(eventos=ev))
        self.passo(mon, 0)
        alertas, _ = self.passo(mon, 60)
        self.assertEqual([a for a in alertas if "evento" in a.lower()], [])

    def test_carta_nova_alerta(self):
        carta = {"n": 1, "titulo": "Apagão", "agencia": "Bangkok"}
        mon = self.monitor(status(), status(cartas=[carta]))
        self.passo(mon, 0)
        alertas, _ = self.passo(mon, 60)
        self.assertTrue(any("Apagão" in a for a in alertas))

    def test_mudanca_de_fase_alerta(self):
        mon = self.monitor(status("neblina"), status("clara"))
        self.passo(mon, 0)
        alertas, _ = self.passo(mon, 60)
        self.assertTrue(any("clara" in a for a in alertas))

    def test_fase_clara_baixa_catalogo(self):
        mon = self.monitor(status("neblina"), status("clara"), status("clara"))
        self.passo(mon, 0)
        self.assertEqual(self.juiz.catalogos, 0)
        self.passo(mon, 60)
        self.passo(mon, 120)
        self.assertEqual(self.juiz.catalogos, 1)
        gravado = json.loads((self.dados / "catalogo.json").read_text(encoding="utf-8"))
        self.assertEqual(gravado["carregadores"][0]["custo"], 3)

    def test_catalogo_rebaixa_quando_libera_agencia_na_clara(self):
        mon = self.monitor(status("clara"), status("clara", agencias=("Bangkok", "Tokyo")))
        self.passo(mon, 0)
        self.passo(mon, 60)
        self.assertEqual(self.juiz.catalogos, 2)

    def test_placar_a_cada_5_min(self):
        mon = self.monitor(status())
        for agora in range(0, 601, 60):
            self.passo(mon, agora)
        linhas = (self.raiz / "placar.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(linhas), 3)
        self.assertEqual([json.loads(l)["agora"] for l in linhas], [0, 300, 600])
        self.assertEqual(json.loads(linhas[0])["placar"]["equipes"][0]["nome"], "nós")

    def test_excecao_nao_derruba(self):
        mon = self.monitor(ErroApi(500, "erro_interno", "falhou"))
        alertas, saida = self.passo(mon, 0)
        self.assertEqual(len(alertas), 1)
        self.assertIn("erro", alertas[0].lower())
        self.assertIn("\a", saida)

    def test_excecao_generica_tambem_nao_derruba(self):
        mon = self.monitor(OSError("rede caiu"), status())
        alertas, _ = self.passo(mon, 0)
        self.assertIn("rede caiu", alertas[0])
        alertas2, _ = self.passo(mon, 60)  # recupera na rodada seguinte
        self.assertEqual(self.juiz.status_chamadas, 2)

    def test_falha_do_placar_nao_esconde_resto(self):
        mon = self.monitor(status(agencias=("Bangkok", "Tokyo")))
        self.juiz.placar = lambda: (_ for _ in ()).throw(ErroApi(500, "erro_interno", "x"))
        alertas, _ = self.passo(mon, 0)
        self.assertTrue(any("Tokyo" in a for a in alertas))
        self.assertTrue(any("erro" in a.lower() for a in alertas))


if __name__ == "__main__":
    unittest.main()
