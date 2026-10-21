import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import recarga
from kickoff import validar
from kickoff.api import ErroApi
from kickoff.dados import carregar
from recarga import juiz as mod
from recarga.juiz import Juiz, Limitador, Recusado, carregar_env, chave

SUB = {"agencia": "Teste", "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45"}


class ClienteFalso:
    """Registra chamadas; respostas configuráveis."""

    def __init__(self, saldo=1000, taxa=20):
        self.saldo, self.taxa = saldo, taxa
        self.eventos_ativos = []
        self.envios_na_status = True   # False simula o campo `envios` ausente/renomeado
        self.fila_teste = []        # respostas/exceções devolvidas antes do padrão
        self.fila_final = []
        self.chamadas_status = 0
        self.chamadas_teste = []
        self.chamadas_final = []
        self.chamadas_outras = []

    def status(self):
        self.chamadas_status += 1
        info = {"aberta": True, **({"envios": 0} if self.envios_na_status else {})}
        return {"fase": "neblina", "saldo": self.saldo, "eventos_ativos": list(self.eventos_ativos),
                "agencias": {"Teste": dict(info), "Bangkok": dict(info)}}

    def catalogo(self):
        self.chamadas_outras.append("catalogo")
        return {"carregadores": []}

    def _req(self, metodo, caminho, corpo=None):
        """Kit: zip mínimo em base64, como o API Gateway devolve."""
        import base64, io, zipfile
        ag = caminho.split("/")[2]
        self.chamadas_outras.append(("kit", ag))
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr(f"{ag}/agencias.md", "x")
        return base64.b64encode(b.getvalue())

    def teste(self, ag, sub, detalhe="placar", salvar=None):
        self.chamadas_teste.append((ag, sub, detalhe))
        if self.fila_teste:
            r = self.fila_teste.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        taxa = 0 if ag == "Bangkok" else self.taxa
        self.saldo -= taxa
        return {"agencia": ag, "valido": True, "erros": [], "violacoes": [], "nota": 1.0,
                "metricas": {"contratos": 10}, "taxa": taxa, "saldo": self.saldo, "repetido": False}

    def _json(self, metodo, caminho, corpo=None):
        if caminho == "/placar":
            self.chamadas_outras.append("placar")
            return {"fase": "neblina", "equipes": []}
        if caminho.startswith("/final/"):
            ag = caminho.split("/")[-1]
            self.chamadas_final.append((ag, corpo))
            if self.fila_final:
                r = self.fila_final.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r
            return {"agencia": ag, "n": len(self.chamadas_final), "taxa": 0, "saldo": self.saldo,
                    "aceito": True, "custo_infra": "pendente"}
        raise AssertionError(caminho)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dados = Path(tempfile.mkdtemp())
        for nome in ("Bangkok", "Teste"):
            shutil.copytree(recarga.DADOS / "Bangkok", cls.tmp_dados / nome)
        cls.cen = carregar(cls.tmp_dados, "Teste")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dados, ignore_errors=True)

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.falso = ClienteFalso()
        self.dormidos = []
        self.juiz = self.novo()

    def novo(self, **kw):
        kw.setdefault("cliente", self.falso)
        kw.setdefault("dormir", self.dormidos.append)
        return Juiz(raiz=self.raiz, dados=self.tmp_dados, autor="tester", **kw)

    def norm(self, sub):
        return validar.normalizar(sub, self.cen)

    def linhas(self, nome):
        p = self.raiz / nome
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


class Cache(Base):
    def test_cache_nao_chama_rede(self):
        a = self.juiz.teste("Teste", SUB, confirmar=True)
        b = self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)
        self.assertEqual(a, b)

    def test_cache_persiste_entre_instancias(self):
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.novo().teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)
        arquivos = list((self.raiz / "juiz" / "Teste").glob("*_placar.json"))
        self.assertEqual(len(arquivos), 1)

    def test_hash_equivalentes(self):
        a = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1, "ac_11": 0}, "entrada": "b3_45"}
        b = {"entrada": "b3_45", "carregadores": {"dc_30": 1, "ac_7": 2},
             "politica": {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}, "agencia": "Bangkok"}
        cen = carregar(self.tmp_dados, "Bangkok")
        self.assertEqual(chave(validar.normalizar(a, cen), []), chave(validar.normalizar(b, cen), []))

    def test_equivalentes_nao_cobram_duas_vezes(self):
        a = {"agencia": "Teste", "carregadores": {"ac_7": 2, "dc_30": 1, "ac_11": 0}, "entrada": "b3_45"}
        b = {"entrada": "b3_45", "carregadores": {"dc_30": 1, "ac_7": 2},
             "politica": {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}, "agencia": "Teste"}
        self.juiz.teste("Teste", a, confirmar=True)
        self.juiz.teste("Teste", b, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)
        self.assertEqual(len(self.linhas("ledger.jsonl")), 1)

    def test_evento_novo_invalida_cache(self):
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.falso.eventos_ativos = [{"agencia": "Teste", "params": [1, "Teste", 2000, 3000]}]
        self.juiz._status_t = None  # força releitura do status
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 2)

    def test_evento_de_outra_agencia_nao_invalida(self):
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.falso.eventos_ativos = [{"agencia": "Tokyo", "params": [1, "Tokyo", 2000, 3000]}]
        self.juiz._status_t = None
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)

    def test_eventos_da_agencia(self):
        self.falso.eventos_ativos = [{"agencia": "Teste", "params": [1, "Teste", 5]},
                                     {"agencia": "Tokyo", "params": [2, "Tokyo", 6]}]
        self.juiz.status()
        self.assertEqual(self.juiz.eventos("Teste"), [[1, "Teste", 5]])
        self.assertEqual(self.juiz.eventos("Nada"), [])

    def test_completo_depois_de_placar_taxa_30(self):
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.falso.taxa = 30  # o juiz cobraria 30
        self.juiz.teste("Teste", SUB, detalhe="completo", confirmar=True)
        self.assertEqual(self.falso.chamadas_teste[-1][2], "completo")
        self.assertEqual([x["taxa"] for x in self.linhas("ledger.jsonl")], [20, 30])

    def test_completo_em_cache_serve_placar(self):
        self.juiz.teste("Teste", SUB, detalhe="completo", confirmar=True)
        self.juiz.teste("Teste", SUB, detalhe="placar", confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)


class Travas(Base):
    def test_invalida_nao_vai_para_rede(self):
        ruim = {**SUB, "carregadores": {"ac_7": 2, "dc_30": 99}}
        with self.assertRaises(Recusado):
            self.juiz.teste("Teste", ruim, confirmar=True)
        self.assertEqual(self.falso.chamadas_teste, [])

    def test_agencia_divergente(self):
        with self.assertRaises(Recusado):
            self.juiz.teste("Teste", {**SUB, "agencia": "Outra"}, confirmar=True)
        self.assertEqual(self.falso.chamadas_teste, [])

    def test_agencia_omitida_no_corpo(self):
        sub = {k: v for k, v in SUB.items() if k != "agencia"}
        self.juiz.teste("Teste", sub, confirmar=True)
        self.assertEqual(self.falso.chamadas_teste[0][1]["agencia"], "Teste")

    def test_detalhe_invalido(self):
        with self.assertRaises(Recusado):
            self.juiz.teste("Teste", SUB, detalhe="xyz", confirmar=True)

    def test_paga_sem_confirmar_recusada(self):
        with self.assertRaises(Recusado):
            self.juiz.teste("Teste", SUB)
        self.assertEqual(self.falso.chamadas_teste, [])

    def test_bangkok_nao_exige_confirmar(self):
        r = self.juiz.teste("Bangkok", {**SUB, "agencia": "Bangkok"})
        self.assertEqual(r["taxa"], 0)
        self.assertEqual(len(self.falso.chamadas_teste), 1)
        self.assertEqual(self.linhas("ledger.jsonl"), [])

    def test_reserva_minima(self):
        self.falso.saldo = 310
        with self.assertRaises(Recusado) as cm:
            self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertIn("reserva", str(cm.exception))
        self.assertEqual(self.falso.chamadas_teste, [])

    def test_reserva_exatamente_no_limite_passa(self):
        self.falso.saldo = 320
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)

    def test_reserva_configuravel(self):
        self.falso.saldo = 310
        self.novo(reserva=0).teste("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_teste), 1)

    def test_teto_por_agencia(self):
        j = self.novo(teto_por_agencia={"Teste": 30})
        j.teste("Teste", SUB, confirmar=True)  # gasta 20
        outro = {**SUB, "carregadores": {"ac_7": 3}}
        with self.assertRaises(Recusado) as cm:
            j.teste("Teste", outro, confirmar=True)  # 20 + 20 > 30
        self.assertIn("teto", str(cm.exception))
        self.assertEqual(len(self.falso.chamadas_teste), 1)

    def test_erro_da_api_propaga_e_nao_registra(self):
        self.falso.fila_teste = [ErroApi(402, "saldo_insuficiente", "sem saldo")]
        with self.assertRaises(ErroApi):
            self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(self.linhas("ledger.jsonl"), [])
        self.assertEqual(list((self.raiz / "juiz").rglob("*.json")), [])


class Espera429(Base):
    def _futuro(self, seg):
        return (datetime.now(timezone.utc) + timedelta(seconds=seg)).isoformat().replace("+00:00", "Z")

    def test_429_espera_retry_em(self):
        ok = {"agencia": "Teste", "taxa": 20, "saldo": 980, "nota": 2.0, "metricas": {}}
        self.falso.fila_teste = [ErroApi(429, "cooldown", "aguarde", {"retry_em": self._futuro(30)}), ok]
        r = self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(r, ok)
        self.assertEqual(len(self.dormidos), 1)
        self.assertGreaterEqual(self.dormidos[0], 0)
        self.assertLessEqual(self.dormidos[0], 31)
        self.assertEqual(len(self.falso.chamadas_teste), 2)
        self.assertEqual(len(self.linhas("ledger.jsonl")), 1)

    def test_429_retry_em_no_passado_espera_zero_ou_pouco(self):
        ok = {"agencia": "Teste", "taxa": 20, "saldo": 980, "nota": 2.0, "metricas": {}}
        passado = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        self.falso.fila_teste = [ErroApi(429, "cooldown", "x", {"retry_em": passado}), ok]
        self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(self.dormidos, [0])

    def test_429_rate_limit_espera_e_segue(self):
        ok = {"agencia": "Teste", "taxa": 20, "saldo": 980, "nota": 2.0, "metricas": {}}
        self.falso.fila_teste = [ErroApi(429, "rate_limit", "muitas"), ok]
        r = self.juiz.teste("Teste", SUB, confirmar=True)
        self.assertEqual(r, ok)
        self.assertEqual(len(self.dormidos), 1)
        self.assertGreater(self.dormidos[0], 0)

    def test_429_persistente_acaba_propagando(self):
        self.falso.fila_teste = [ErroApi(429, "rate_limit", "x") for _ in range(50)]
        with self.assertRaises(ErroApi):
            self.juiz.teste("Teste", SUB, confirmar=True)

    def test_429_no_final_tambem_espera(self):
        ok = {"agencia": "Teste", "n": 1, "taxa": 0, "saldo": 1000, "aceito": True, "custo_infra": "pendente"}
        self.falso.fila_final = [ErroApi(429, "cooldown", "x", {"retry_em": self._futuro(5)}), ok]
        self.juiz.final("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_final), 2)
        self.assertEqual(len(self.dormidos), 1)


class Ledger(Base):
    def test_ledger_so_registra_cobranca(self):
        self.juiz.teste("Teste", SUB, confirmar=True)
        linhas = self.linhas("ledger.jsonl")
        self.assertEqual(len(linhas), 1)
        l = linhas[0]
        self.assertEqual(set(l), {"t", "rota", "agencia", "hash", "taxa", "saldo", "autor"})
        self.assertEqual((l["rota"], l["agencia"], l["taxa"], l["saldo"], l["autor"]),
                         ("teste", "Teste", 20, 980, "tester"))
        self.assertEqual(l["hash"], chave(self.norm(SUB), []))
        self.falso.fila_teste = [ErroApi(422, "invalido", "x")]
        with self.assertRaises(ErroApi):
            self.juiz.teste("Teste", {**SUB, "carregadores": {"ac_7": 4}}, confirmar=True)
        self.assertEqual(len(self.linhas("ledger.jsonl")), 1)


class Final(Base):
    def test_final_envia_e_registra(self):
        r = self.juiz.final("Teste", SUB, confirmar=True)
        self.assertTrue(r["aceito"])
        self.assertEqual(len(self.falso.chamadas_final), 1)
        fin = self.linhas("finais.jsonl")
        self.assertEqual(len(fin), 1)
        self.assertEqual(fin[0]["hash"], chave(self.norm(SUB), []))
        self.assertEqual(fin[0]["sub"], self.norm(SUB))
        self.assertEqual(self.linhas("ledger.jsonl"), [])  # 1º final é grátis

    def test_final_exige_confirmar(self):
        with self.assertRaises(Recusado):
            self.juiz.final("Teste", SUB)
        self.assertEqual(self.falso.chamadas_final, [])

    def test_final_invalido_recusado(self):
        with self.assertRaises(Recusado):
            self.juiz.final("Teste", {**SUB, "carregadores": {"ac_7": 99}}, confirmar=True)
        self.assertEqual(self.falso.chamadas_final, [])

    def test_final_bangkok_recusado(self):
        with self.assertRaises(Recusado):
            self.juiz.final("Bangkok", {**SUB, "agencia": "Bangkok"}, confirmar=True)

    def test_final_identico_recusado_localmente(self):
        self.juiz.final("Teste", SUB, confirmar=True)
        equivalente = {"entrada": "b3_45", "carregadores": {"dc_30": 1, "ac_7": 2, "ac_11": 0}, "agencia": "Teste"}
        with self.assertRaises(Recusado) as cm:
            self.juiz.final("Teste", equivalente, confirmar=True)
        self.assertIn("idêntic", str(cm.exception))
        self.assertEqual(len(self.falso.chamadas_final), 1)

    def test_final_identico_via_finais_jsonl_preexistente(self):
        self.raiz.mkdir(exist_ok=True)
        (self.raiz / "finais.jsonl").write_text(
            json.dumps({"agencia": "Teste", "hash": chave(self.norm(SUB), [])}) + "\n", encoding="utf-8")
        with self.assertRaises(Recusado):
            self.juiz.final("Teste", SUB, confirmar=True)

    def test_final_diferente_do_vigente_passa_e_cobra_reenvio(self):
        self.juiz.final("Teste", SUB, confirmar=True)
        outro = {**SUB, "carregadores": {"ac_7": 3}}
        self.falso.fila_final = [{"agencia": "Teste", "n": 2, "taxa": 80, "saldo": 920,
                                  "aceito": True, "custo_infra": "pendente"}]
        self.juiz.final("Teste", outro, confirmar=True)
        self.assertEqual([x["taxa"] for x in self.linhas("ledger.jsonl")], [80])
        self.assertEqual([x["rota"] for x in self.linhas("ledger.jsonl")], ["final"])
        # o vigente agora é o segundo: reenviar o primeiro é permitido, o segundo não
        with self.assertRaises(Recusado):
            self.juiz.final("Teste", outro, confirmar=True)

    def test_final_reenvio_respeita_reserva(self):
        self.juiz.final("Teste", SUB, confirmar=True)
        self.falso.saldo = 350  # reenvio custaria 80: 350-80 < 300
        with self.assertRaises(Recusado) as cm:
            self.juiz.final("Teste", {**SUB, "carregadores": {"ac_7": 3}}, confirmar=True)
        self.assertIn("reserva", str(cm.exception))
        self.assertEqual(len(self.falso.chamadas_final), 1)

    def test_final_envios_desconhecido_trata_como_pago_e_respeita_reserva(self):
        self.falso.envios_na_status = False
        self.falso.saldo = 350  # taxa assumida >= 80: 350-80 < 300
        with self.assertRaises(Recusado) as cm:
            self.juiz.final("Teste", SUB, confirmar=True)
        self.assertIn("reserva", str(cm.exception))
        self.assertEqual(self.falso.chamadas_final, [])

    def test_final_envios_desconhecido_com_saldo_folgado_envia(self):
        self.falso.envios_na_status = False
        self.juiz.final("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_final), 1)

    def test_final_envios_desconhecido_usa_historico_local(self):
        self.falso.envios_na_status = False
        self.juiz.final("Teste", SUB, confirmar=True)
        self.falso.saldo = 450  # 2º envio local custaria 80 (450-80 ok); 3º custaria 160 (450-160 < 300)
        self.juiz.final("Teste", {**SUB, "carregadores": {"ac_7": 3}}, confirmar=True)
        with self.assertRaises(Recusado) as cm:
            self.juiz.final("Teste", {**SUB, "carregadores": {"ac_7": 4}}, confirmar=True)
        self.assertIn("reserva", str(cm.exception))

    def test_primeiro_final_gratis_ignora_reserva(self):
        self.falso.saldo = 100
        self.juiz.final("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_final), 1)

    def test_final_violacao_no_nosso_motor_recusada(self):
        sim = mock.Mock(return_value={"valido": True, "violacoes": ["x"]})
        juiz = self.novo(simulador=sim)
        with self.assertRaises(Recusado) as cm:
            juiz.final("Teste", SUB, confirmar=True)
        self.assertIn("violaç", str(cm.exception))
        sim.assert_called_once()
        self.assertEqual(self.falso.chamadas_final, [])

    def test_final_sem_simulador_nao_simula(self):
        self.assertIsNone(self.juiz.simulador)
        self.juiz.final("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_final), 1)

    def test_final_com_simulador_limpo_envia(self):
        sim = mock.Mock(return_value={"valido": True, "violacoes": []})
        self.novo(simulador=sim).final("Teste", SUB, confirmar=True)
        self.assertEqual(len(self.falso.chamadas_final), 1)
        sim.assert_called_once()

    def test_simulador_padrao_e_none_com_dados_alternativos(self):
        self.assertNotEqual(self.tmp_dados.resolve(), Path(recarga.DADOS).resolve())
        self.assertIsNone(Juiz(cliente=self.falso, raiz=self.raiz, dados=self.tmp_dados).simulador)

    def test_simulador_padrao_e_lote_com_dados_globais(self):
        fake = mock.Mock()
        with mock.patch.object(mod, "lote", fake):
            j = Juiz(cliente=self.falso, raiz=self.raiz, dados=recarga.DADOS)
        self.assertIs(j.simulador, fake.avaliar)


class ImportLote(unittest.TestCase):
    def test_ausencia_de_recarga_lote_vira_none(self):
        ausente = ModuleNotFoundError("No module named 'recarga.lote'", name="recarga.lote")
        with mock.patch.object(mod.importlib, "import_module", side_effect=ausente):
            self.assertIsNone(mod._importar_lote())

    def test_outro_erro_de_import_sobe(self):
        outro = ModuleNotFoundError("No module named 'numpy'", name="numpy")
        with mock.patch.object(mod.importlib, "import_module", side_effect=outro):
            with self.assertRaises(ModuleNotFoundError):
                mod._importar_lote()
        with mock.patch.object(mod.importlib, "import_module", side_effect=ImportError("quebrado")):
            with self.assertRaises(ImportError):
                mod._importar_lote()

    def test_modulo_presente_e_devolvido(self):
        falso = object()
        with mock.patch.object(mod.importlib, "import_module", return_value=falso):
            self.assertIs(mod._importar_lote(), falso)


class Rotas(Base):
    def test_status_grava_arquivo(self):
        st = self.juiz.status()
        self.assertEqual(st["fase"], "neblina")
        gravado = json.loads((self.raiz / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(gravado, st)

    def test_catalogo_placar_kit(self):
        self.assertEqual(self.juiz.catalogo(), {"carregadores": []})
        self.assertEqual(self.juiz.placar()["fase"], "neblina")
        self.assertEqual(self.juiz.kit("Tokyo"), self.tmp_dados / "Tokyo")
        self.assertIn(("kit", "Tokyo"), self.falso.chamadas_outras)
        self.assertEqual((self.tmp_dados / "Tokyo" / "agencias.md").read_text(), "x")


class LimitadorTeste(unittest.TestCase):
    def test_nao_passa_de_max_por_min(self):
        t = [0.0]
        dormidos = []

        def dormir(s):
            dormidos.append(s)
            t[0] += s

        lim = Limitador(max_por_min=3, relogio=lambda: t[0], dormir=dormir)
        for _ in range(3):
            lim.esperar()
        self.assertEqual(dormidos, [])
        lim.esperar()  # 4ª na mesma janela de 60 s
        self.assertEqual(len(dormidos), 1)
        self.assertGreaterEqual(dormidos[0], 60)

    def test_janela_desliza(self):
        t = [0.0]
        lim = Limitador(max_por_min=2, relogio=lambda: t[0], dormir=lambda s: self.fail("não deveria dormir"))
        lim.esperar()
        lim.esperar()
        t[0] = 61.0
        lim.esperar()

    def test_padrao_e_18(self):
        self.assertEqual(Limitador().max_por_min, 18)


class Env(unittest.TestCase):
    def test_carregar_env_nao_sobrescreve(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / ".env"
        p.write_text('# comentário\n\nGAMEDAY_URL_T=http://x/api\nGAMEDAY_TOKEN_T="abc def"\n'
                     'export OUTRA_T=1\nJA_EXISTE_T=novo\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"JA_EXISTE_T": "velho"}, clear=False):
            carregar_env(p)
            self.assertEqual(os.environ["GAMEDAY_URL_T"], "http://x/api")
            self.assertEqual(os.environ["GAMEDAY_TOKEN_T"], "abc def")
            self.assertEqual(os.environ["OUTRA_T"], "1")
            self.assertEqual(os.environ["JA_EXISTE_T"], "velho")
        for k in ("GAMEDAY_URL_T", "GAMEDAY_TOKEN_T", "OUTRA_T"):
            os.environ.pop(k, None)

    def test_arquivo_ausente_e_noop(self):
        carregar_env(Path(tempfile.gettempdir()) / "nao-existe-xyz" / ".env")


if __name__ == "__main__":
    unittest.main()


class ExtrairKit(unittest.TestCase):
    def _zip(self):
        import io, zipfile
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("Ag/agencias.md", "x")
        return b.getvalue()

    def test_zip_cru_e_base64(self):
        import base64
        from recarga.juiz import extrair_kit
        for corpo in (self._zip(), base64.b64encode(self._zip())):
            d = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)
            extrair_kit(corpo, d)
            self.assertEqual((d / "Ag" / "agencias.md").read_text(), "x")
