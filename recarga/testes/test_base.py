import unittest


class Base(unittest.TestCase):
    def test_importa_kit(self):
        import recarga
        from kickoff import dados
        cen = dados.carregar(recarga.DADOS, "Bangkok")
        self.assertEqual(cen.agencia.vagas, 6)
        self.assertEqual(len(cen.contratos), 271)

    def test_constantes(self):
        import recarga
        self.assertEqual(recarga.KIT, recarga.RAIZ / "kit_kickoff")
        self.assertEqual(recarga.DADOS, recarga.KIT / "dados")
        self.assertEqual(recarga.RESULTADOS, recarga.RAIZ / "resultados")


class Chave(unittest.TestCase):
    def test_ordem_das_chaves_nao_importa(self):
        from recarga.chave import chave
        a = {"x": 1, "y": {"b": 2, "a": 3}}
        b = {"y": {"a": 3, "b": 2}, "x": 1}
        self.assertEqual(chave(a, [1, 2]), chave(b, [1, 2]))

    def test_eventos_diferentes_hash_diferente(self):
        from recarga.chave import chave
        sub = {"x": 1}
        self.assertNotEqual(chave(sub, [1, 2]), chave(sub, [1, 3]))
        self.assertEqual(len(chave(sub, [])), 64)


if __name__ == "__main__":
    unittest.main()
