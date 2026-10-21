"""Testa interpretações do evento 'corte' de Marrakech contra a resposta do juiz. Não chama a API."""
import itertools, sys
import recarga
from recarga import lote
from kickoff import motor, validar, medicao, tempo

ALVO = {"nota": -3759.0, "atend": 97.23577235772358, "energia": 20676.26}
SUB = {"agencia": "Marrakech", "carregadores": {"ac_22x2": 5}, "entrada": "a4_150", "demanda_contratada_kw": 110,
       "politica": {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "igual"}}
cen = lote.cenario("Marrakech"); norm = validar.normalizar(SUB, cen)


def rodar(modo, ini, fim, f):
    class M(motor.Motor):
        def agendar_eventos(self, eventos):
            self.agendar(ini, motor.PRIO_ABERTURA, "evento", "ini")
            self.agendar(fim, motor.PRIO_ABERTURA, "evento", "fim")

        def on_evento(self, t, acao):
            if acao == "ini":
                self._base = (self.limite_kw, [p.modelo for p in self.pontos])
                if modo == "limite":
                    self.limite_kw *= f
                elif modo == "carregador":
                    for p in self.pontos:
                        m = p.modelo
                        p.modelo = type(m)(m.id, m.modelo, m.tipo, m.potencia_kw * f, m.saidas, m.custo)
                elif modo == "entrada":  # f aplicado ao kW útil da entrada; teto = min(demanda, útil*f)
                    self.limite_kw = min(self.limite_kw, cen.entradas[norm["entrada"]].kw_util * f)
            else:
                self.limite_kw, mods = self._base
                for p, m in zip(self.pontos, mods):
                    p.modelo = m
            self.recalcular_potencias(t)

    res = M(cen, norm).rodar()
    m = medicao.metricas(res.retiradas, res.nao_atendidos, res.bins, *tempo.JANELA_PUBLICA)
    nota = 15 * m["certos"] + 8 * m["upgrades"] - 200 * m["nao_atendidos"] - 0.5 * m["energia_ponta_kwh"] - 2 * 110 - 14000
    return nota, m


if __name__ == "__main__":
    I, F = 31680, 34560
    janelas = {"dada": (I, F), "+T0": (I + 1080, F + 1080), "-1dia": (I - 1440, F - 1440), "+1dia": (I + 1440, F + 1440)}
    out = []
    for modo, (nj, (a, b)), f in itertools.product(("limite", "carregador", "entrada"), janelas.items(), (0.3, 0.5, 0.7)):
        nota, m = rodar(modo, a, b, f)
        erro = abs(nota - ALVO["nota"]) + 100 * abs(m["atendimento_pct"] - ALVO["atend"]) + abs(m["energia_kwh"] - ALVO["energia"]) / 10
        out.append((erro, modo, nj, f, nota, m["atendimento_pct"], m["energia_kwh"], m["nao_atendidos"], m["upgrades"]))
        print(f"{modo:10} {nj:6} f={f}  nota {nota:8.1f} atend {m['atendimento_pct']:.3f} energia {m['energia_kwh']:.1f} perd {m['nao_atendidos']} upg {m['upgrades']}", flush=True)
    out.sort()
    print("MELHOR:", out[0])
