import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import streamlit as st
from streamlit.testing.v1 import AppTest

from recarga import lote

from dashboard import exemplo

APP = str(Path(__file__).resolve().parent.parent / "app.py")


class AppStreamlit(unittest.TestCase):
    def setUp(self):
        self._antes = os.environ.get("RESULTADOS_DIR")
        # candidatas sem `series` fazem o app rodar o motor ao vivo: o cache do lote vai para uma pasta temporária
        self._cache = tempfile.TemporaryDirectory()
        patch = mock.patch.object(lote, "CACHE", Path(self._cache.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._cache.cleanup)
        st.cache_data.clear()
        st.cache_resource.clear()

    def tearDown(self):
        if self._antes is None:
            os.environ.pop("RESULTADOS_DIR", None)
        else:
            os.environ["RESULTADOS_DIR"] = self._antes

    def _rodar(self, pasta: str) -> AppTest:
        os.environ["RESULTADOS_DIR"] = pasta
        return AppTest.from_file(APP, default_timeout=120).run()

    def test_app_sobe_com_exemplo(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            at = self._rodar(d)
            self.assertFalse(at.exception)
            self.assertTrue(len(at.metric) >= 4)

    def test_pagina_consolidado_sobe_com_exemplo(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            at = self._rodar(d)
            at.sidebar.radio(key="pagina").set_value("Consolidado").run()
            self.assertFalse(at.exception)

    def test_submissoes_do_exemplo_abrem_sem_erro(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            at = self._rodar(d)
            caixa = at.sidebar.selectbox(key="submissao")
            self.assertGreaterEqual(len(caixa.options), 3)
            for i in range(len(caixa.options)):
                caixa.select_index(i)
                at.run()
                self.assertFalse(at.exception, f"submissão {i}")

    def test_app_sobe_sem_nenhum_dado(self):
        with tempfile.TemporaryDirectory() as d:
            at = self._rodar(d)
            self.assertFalse(at.exception)
            at.sidebar.radio(key="pagina").set_value("Consolidado").run()
            self.assertFalse(at.exception)

    def test_app_sobe_com_arquivos_corrompidos(self):
        with tempfile.TemporaryDirectory() as d:
            exemplo.gerar(Path(d))
            (Path(d) / "ledger.jsonl").write_text("{lixo\n", encoding="utf-8")
            (Path(d) / "otimizador" / "Bangkok" / "ranking.json").write_text("[1, 2", encoding="utf-8")
            at = self._rodar(d)
            self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
