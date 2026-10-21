---
title: Recarga Inteligente — plano de implementação
date: 2026-10-21
---

# Recarga Inteligente — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Motor fiel ao juiz + inferência de pesos + otimizador + operação da API + dashboard, para maximizar a nota das 6 agências pontuadas.

**Architecture:** O kit (`kit_kickoff/`) fica intacto, exceto `kickoff/motor.py` e testes novos. O código da equipe fica no pacote `recarga/` (importa `kickoff`) e o dashboard em `dashboard/`. Frentes se comunicam por `simular.avaliar`/`recarga.lote` e pelos arquivos de `resultados/`.

**Tech Stack:** Python 3.10+ (máquina: 3.14), `unittest`, numpy, streamlit, plotly.

**Spec:** `docs/superpowers/specs/2026-10-21-recarga-inteligente-design.md`

## Global Constraints

- Não alterar `kickoff/dados.py`, `validar.py`, `potencia.py`, `medicao.py`, `nota.py`, `tempo.py`, `modelo.py`, `api.py`, `simular.py`, `comparar.py`.
- `kit_kickoff/` só biblioteca padrão. `recarga/` e `dashboard/` podem usar numpy, streamlit, plotly (`requirements.txt`).
- Testes com `unittest`. Kit: `cd kit_kickoff && python -m unittest discover -s testes`. Pacote: na raiz, `python -m unittest discover -s recarga/testes -t .`. Dashboard: `python -m unittest discover -s dashboard/testes -t .`.
- A PalavraChave nunca entra em commit: `.env` no `.gitignore`. Variáveis: `GAMEDAY_URL`, `GAMEDAY_TOKEN`.
- Nenhuma chamada paga à API (teste fora de Bangkok, reenvio final) sem aprovação humana; `Juiz` exige `confirmar=True`.
- Rate limit da API: 20 req/min por equipe; cliente usa no máximo 18.
- Reserva mínima de saldo padrão: 300 m7Coins.
- Hash de cache = SHA-256 do JSON canônico (`sort_keys=True`, `separators=(",", ":")`) de `{"sub": validar.normalizar(sub, cen), "eventos": eventos_da_agencia}`.
- Tempo em minutos desde 17/10/2049 00:00 (domingo); T0 = 1080; semana = 7 × 1440.
- Desempate final em toda ordenação do motor: menor `id` alfabético.

## Review Focus

1. Mesmo minuto com devolução e retirada: carro devolvido apto (≥ 80%) sai no mesmo minuto (ordem devolução → abertura → fim de recarga → retirada → fechamento). Teste em Task A1.
2. Carro que chega a 80% com a agência fechada segura a saída até a abertura e só então outro carro pluga. Teste em Task A4.
3. Carregador de 2 saídas em que um carro absorve menos que a metade: a sobra vai para o outro. Teste em Task A2.
4. Submissões equivalentes (ordem de chaves diferente, carregador com quantidade 0, política omitida × padrão explícito) geram o mesmo hash e não são cobradas duas vezes. Teste em Task D1.
5. `429 cooldown`/`rate_limit` no meio de uma rotina (matriz de fidelidade, coleta de pesos): espera `retry_em` e segue, sem perder a rodada. Teste em Task D1.

---

## Ordem e paralelismo

| Frente | Tasks | Depende de |
|---|---|---|
| Base | 0 | — |
| A (motor) | A1 → A2 → A3 → A4 → A5 → A6 (no evento) | 0 |
| D (operação) | D1 → D2 → D3 | 0 (D3 também precisa de A5 para dar OK) |
| B (otimização) | B1 → B2 → B3 → B4 → B5 | 0 (resultados úteis só após A2+) ; B3 coleta precisa de D1 |
| C (dashboard) | C1 → C2 → C3 | 0 |

As frentes A, B, C e D podem rodar em paralelo depois da Task 0.

---

### Task 0: Base do repositório

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `recarga/__init__.py`, `recarga/testes/__init__.py`, `recarga/testes/test_base.py`
- Copy: `Bangkok/*` → `kit_kickoff/dados/Bangkok/` (não versionado)

**Interfaces:**
- Produces: `recarga.RAIZ: Path` (raiz do repo), `recarga.KIT: Path` (`RAIZ/"kit_kickoff"`), `recarga.DADOS: Path` (`KIT/"dados"`), `recarga.RESULTADOS: Path` (`RAIZ/"resultados"`); importar `recarga` coloca `KIT` em `sys.path`, permitindo `from kickoff import ...` e `import simular`.

- [ ] **Step 1: Criar `.gitignore`** com: `.env`, `__pycache__/`, `kit_kickoff/dados/*/`, `kit_kickoff/dados/catalogo.json`, `resultados/sim/`. (`resultados/juiz/`, `ledger.jsonl`, `finais.jsonl` são versionados para o time compartilhar respostas pagas.)
- [ ] **Step 2: Criar `.env.example`** com `GAMEDAY_URL=` e `GAMEDAY_TOKEN=`; criar `requirements.txt` com `numpy`, `streamlit`, `plotly`. Rodar `pip install -r requirements.txt`.
- [ ] **Step 3: Copiar os dados de Bangkok**: `cp -r Bangkok kit_kickoff/dados/Bangkok`.
- [ ] **Step 4: Escrever o teste que falha** (`recarga/testes/test_base.py`):

```python
class Base(unittest.TestCase):
    def test_importa_kit(self):
        import recarga
        from kickoff import dados
        cen = dados.carregar(recarga.DADOS, "Bangkok")
        self.assertEqual(cen.agencia.vagas, 6)
        self.assertEqual(len(cen.contratos), 271)
```

- [ ] **Step 5: Rodar** `python -m unittest discover -s recarga/testes -t .` → FAIL (`No module named 'recarga'` ou atributo ausente).
- [ ] **Step 6: Implementar `recarga/__init__.py`** com as quatro constantes e a inserção de `KIT` em `sys.path` (só se ainda não estiver).
- [ ] **Step 7: Rodar** os dois comandos de teste da seção Global Constraints → PASS; o kit mostra 11 testes OK sem `skipped`.
- [ ] **Step 8: Commit** `chore: base do repositório (gitignore, requirements, pacote recarga)`.

---

## Frente A — motor (`kit_kickoff/kickoff/motor.py`)

Cada task implementa os `# TODO(etapa N)` correspondentes, seguindo as docstrings de `motor.py` e o `kit_kickoff/AGENTS.md`.

### Task A1: Apoio de testes + etapa 2 (retirada e devolução)

**Files:**
- Create: `kit_kickoff/testes/apoio.py`, `kit_kickoff/testes/test_etapa2.py`
- Modify: `kit_kickoff/kickoff/motor.py` (`soc_devolucao`, `entrar_patio`, `escolher_carro`, `on_devolucao`)

**Interfaces:**
- Produces (`testes/apoio.py`, usado por A2–A5):
  - `TEM_DADOS: bool` (existe `dados/Bangkok`); testes que usam curvas reais usam `@unittest.skipUnless(TEM_DADOS, ...)`.
  - `base() -> Cenario`: `dados.carregar(RAIZ/"dados", "Bangkok")` com cache em módulo.
  - `veiculo(id, modelo, situacao="estoque_a_carregar", soc=50.0, devolucao_t=None, soc_devolucao=None) -> VeiculoT0` (categoria/rank vindos de `base().modelos[modelo]`).
  - `contrato(id, categoria, retirada_t, devolucao_t=None, km_devolucao=None) -> Contrato` (rank de `base().categorias`).
  - `cenario(veiculos, contratos=(), vagas=6, horario=None, existente="b3_45") -> Cenario`: copia modelos/carregadores/entradas/categorias de `base()`; `horario=None` = aberta 24 h todos os dias (`[(0, 1440)] * 7`).
  - `motor(cen, carregadores, entrada=None, demanda=None, politica=None, eventos=()) -> Motor`: monta a sub com `agencia=cen.agencia.nome`, entrada padrão = `existente`, valida (falha o teste se inválida) e normaliza.
  - `fim_plug(res, a_partir=T0) -> float`: primeiro `t` do `res.trace` após `a_partir` em que `plugados` cai.

- [ ] **Step 1: Escrever `apoio.py`** conforme as interfaces acima.
- [ ] **Step 2: Escrever os testes que falham** (`test_etapa2.py`):

```python
# 6.3.1: contrato Prata; pátio montado à mão em m.patio
def test_6_3_1_sai_geely(self):          # Geely 82 livre, Dolphin Mini 95 plugado, MG4 100, JAC 100
    self.assertEqual(self.escolher().id, "geely")
def test_6_3_1_geely_78_sai_dolphin_mini(self):
    self.assertEqual(self.escolher(geely_soc=78).id, "dmini")
def test_6_3_1_sem_prata_sai_mg4(self):
    self.assertEqual(self.escolher(sem_prata=True).id, "mg4")
def test_soc_devolucao_km_sobre_autonomia_com_teto(self):
    # Geely (289 km) sai a 80%: 144.5 km -> 50%; 300 km -> teto 80
    self.assertAlmostEqual(m.soc_devolucao(v_geely_80, contrato(km_devolucao=144.5)), 50.0)
    self.assertAlmostEqual(m.soc_devolucao(v_geely_80, contrato(km_devolucao=300)), 80.0)
def test_devolvido_apto_sai_no_mesmo_minuto(self):   # Review Focus 1
    # único carro em contrato, volta às 1440+600 com 90%; contrato Prata retira às 1440+600
    res = m.rodar(); self.assertEqual(len(res.retiradas), 1); self.assertEqual(res.nao_atendidos, [])
def test_estoque_abaixo_80_nao_sai(self):
    # carro a 50% no estoque, 1x ac_7, contrato com retirada em T0 + 1 (tempo insuficiente
    # para chegar a 80% em qualquer etapa): contrato perdido
    self.assertEqual(len(res.nao_atendidos), 1)
```

(`escolher()` é um helper da classe: cria Motor com os 4 carros no pátio — `m.patio[v.id] = v`, `v.plugado=True` no Dolphin Mini — e chama `m.escolher_carro(c, t)`.)

- [ ] **Step 3: Rodar** `cd kit_kickoff && python -m unittest testes.test_etapa2 -v` → FAIL.
- [ ] **Step 4: Implementar** os 4 métodos. `escolher_carro`: filtra `self.patio` por `v.rank >= c.rank and v.soc >= 80 - 1e-9` e não na fila; `min` pela chave `(v.rank - c.rank, v.soc, v.plugado, v.id)`.
- [ ] **Step 5: Rodar** a suíte do kit inteira → PASS; `python simular.py exemplo_submissao.json` → `atendimento_pct` > 0.
- [ ] **Step 6: Commit** `feat(motor): etapa 2 — retirada e devolução`.

### Task A2: Etapa 3 (fila, plug, curva, fim de recarga — camada 1)

**Files:**
- Create: `kit_kickoff/testes/test_etapa3.py`
- Modify: `kit_kickoff/kickoff/motor.py` (`ordenar_fila` para `chegada`/`menor_soc`, `escolher_ponto`, `plugar_fila`, `recalcular_potencias` camada 1, `agendar_fim_degrau`, `on_fim_recarga`)

**Interfaces:**
- Consumes: `testes/apoio.py` (Task A1).
- Produces: `Motor._plugados_ordenados(t) -> list[Veiculo]` (plugados ainda carregando, na ordem da `prioridade`; usado na camada 2 pela Task A3).

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_6_3_2_dolphin_gs_20_a_80_em_36_7_min(self):
    # único carro, estoque a 20%, 1x dc_60x2, entrada se_2000 demanda 1800 (limite folgado)
    res = m.rodar()
    self.assertAlmostEqual(apoio.fim_plug(res) - T0, 36.7, delta=0.1)
    self.assertAlmostEqual(sum(res.bins.values()), 0.6 * 44.9, places=3)
def test_6_3_4_escolhe_dc60(self):
    # dc_60x2 com Geely 30% plugado; ac_22x2 vazio; Dolphin GS 20% chega
    self.assertEqual(m.escolher_ponto(dolphin).modelo.id, "dc_60x2")
def test_sobra_do_carregador_vai_para_o_outro(self):   # Review Focus 3
    # dc_60x2 com JAC 75% (curva DC 16.45) e Geely 30% (71.5): Geely recebe 60 - 16.45
    self.assertAlmostEqual(geely.potencia_kw, 43.55, places=6)
    self.assertAlmostEqual(jac.potencia_kw, 16.45, places=6)
def test_6_3_3_chegada_e_menor_soc(self):
    # A Kwid 30% (fila 10:00), B Dolphin Mini 20% (10:20), C MG4 55% (10:40), D Leapmotor 40% (10:55)
    self.assertEqual(ordem("chegada"), ["A", "B", "C", "D"])
    self.assertEqual(ordem("menor_soc"), ["A", "B", "D", "C"])
def test_bangkok_sem_violacao_e_atendimento_sobe(self):
    # exemplo_submissao.json: violacoes == [] e atendimento_pct > o da etapa 2 (registrar o valor medido)
```

- [ ] **Step 2: Rodar** `python -m unittest testes.test_etapa3 -v` → FAIL.
- [ ] **Step 3: Implementar.** Camada 1 com `divisao=igual` (padrão): para cada ponto, `potencia.enchimento_agua(ponto.modelo.potencia_kw, [curva de cada carro que ainda carrega])`. A variante `divisao=prioridade` da camada 1 entra na Task A3. Nesta task, ignorar `self.limite_kw`.
- [ ] **Step 4: Rodar** suíte do kit → PASS.
- [ ] **Step 5: Medir** `time python simular.py exemplo_submissao.json`; anotar o tempo no commit.
- [ ] **Step 6: Commit** `feat(motor): etapa 3 — fila, plug e recarga (camada 1)`.

### Task A3: Etapa 4 (limite da agência e `divisao`)

**Files:**
- Create: `kit_kickoff/testes/test_etapa4.py`
- Modify: `kit_kickoff/kickoff/motor.py` (`recalcular_potencias`, camada 2)

**Interfaces:**
- Consumes: `Motor._plugados_ordenados(t)` (Task A2).

- [ ] **Step 1: Escrever os testes que falham** (2× `dc_60x2`; carregador 1: Geely 30%, Dolphin GS 50%; carregador 2: Kwid 40%, JAC 75%; `prioridade=menor_soc`):

```python
def test_6_3_5_igual_40_5(self):        self.assertPot({"geely": 10.125, "dolphin": 10.125, "kwid": 10.125, "jac": 10.125})
def test_6_3_5_prioridade_40_5(self):   self.assertPot({"kwid": 26.6, "geely": 13.9, "jac": 0, "dolphin": 0})
def test_6_3_5_igual_80(self):          self.assertPot({"jac": 16.45, "geely": 21.18333, "dolphin": 21.18333, "kwid": 21.18333})
def test_6_3_5_prioridade_80(self):     self.assertPot({"kwid": 26.6, "geely": 53.4, "jac": 0, "dolphin": 0})
def test_pico_nunca_passa_do_limite_bangkok(self):
    # exemplo_submissao.json (b3_45): metricas["pico_kw"] <= 40.5 + 1e-6
```

Limite 40,5 = entrada `b3_45`; limite 80 = `a4_150` com `demanda=80`. `assertPot` compara `v.potencia_kw` com `places=4`. Na camada 1 com `divisao=prioridade`, o carregador usa `potencia.sequencial` na ordem de prioridade (Geely leva 60, Dolphin 0 — 6.3.5).

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar** camada 1 com `divisao=prioridade` (`potencia.sequencial` na ordem de prioridade dentro de cada carregador) e camada 2: tetos = resultado da camada 1; `igual` → `enchimento_agua(self.limite_kw, tetos)`; `prioridade` → `sequencial(self.limite_kw, tetos na ordem de _plugados_ordenados)`.
- [ ] **Step 4: Rodar** suíte do kit → PASS.
- [ ] **Step 5: Commit** `feat(motor): etapa 4 — limite da agência e divisão`.

### Task A4: Etapa 5 (horário e `evitar_ponta`)

**Files:**
- Create: `kit_kickoff/testes/test_etapa5.py`
- Modify: `kit_kickoff/kickoff/motor.py` (`on_abertura`, `on_fechamento`, `on_ponta`, e potência 0 na ponta em `recalcular_potencias`)

- [ ] **Step 1: Escrever os testes que falham** (MG4 devolvido segunda 18/10 17:00 = minuto 2460 com 29%, 1× `ac_22x2`, limite folgado):

```python
def test_6_3_6_sem_evitar_ponta_termina_19h(self):
    self.assertAlmostEqual(apoio.fim_plug(res, 2460), 2460 + 120, delta=3)
    self.assertAlmostEqual(m["energia_ponta_kwh"], 11.0, delta=0.3)
def test_6_3_6_com_evitar_ponta_termina_22h(self):
    self.assertAlmostEqual(apoio.fim_plug(res, 2460), 2460 + 300, delta=3)
    self.assertEqual(m["energia_ponta_kwh"], 0.0)
def test_80_com_agencia_fechada_segura_saida(self):   # Review Focus 2
    # horário seg-sex 08:00-18:00; mesmo MG4 sem evitar_ponta chega a 80% às ~19:00 fechada:
    # continua plugado até terça 08:00 (minuto 2880+480), quando despluga
    self.assertEqual(apoio.fim_plug(res, 2460), 2880 + 480)
def test_fechada_nao_pluga(self):
    # carro devolvido às 19:00 (fechada) só pluga na abertura seguinte: plugados == 0 até 08:00
```

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar** os três métodos.
- [ ] **Step 4: Rodar** suíte do kit → PASS.
- [ ] **Step 5: Commit** `feat(motor): etapa 5 — horário e evitar_ponta`.

### Task A5: Etapa 6 (`proxima_retirada`)

**Files:**
- Create: `kit_kickoff/testes/test_etapa6.py`
- Modify: `kit_kickoff/kickoff/motor.py` (`ordenar_fila`)

- [ ] **Step 1: Escrever o teste que falha**: mesmos A, B, C, D da Task A2; contratos não retirados 12:30 Ouro, 13:15 Prata, 14:00 Bronze (dia 18/10):

```python
self.assertEqual(ordem("proxima_retirada"), ["C", "D", "B", "A"])
```

e um teste em que, após retirar o contrato de 12:30, a próxima reserva de C passa a ser 13:15.

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.** Manter contratos ordenados por `retirada_t` e um conjunto de contratos já processados (retirados ou perdidos, marcados em `on_retirada`); a próxima reserva de um rank é o primeiro contrato não processado com `c.rank <= rank`. Guardar um ponteiro por rank para não varrer a lista inteira a cada ordenação. Chave: `(t_reserva or inf, -v.soc, v.id)`.
- [ ] **Step 4: Rodar** suíte do kit → PASS; medir tempo de `simular.py` com as 3 prioridades.
- [ ] **Step 5: Commit** `feat(motor): etapa 6 — prioridade proxima_retirada`.

### Task A6: Etapa 7 (eventos) — executar quando o 1º evento for anunciado

**Files:**
- Create: `kit_kickoff/testes/test_etapa7.py`, `docs/eventos.md`
- Modify: `kit_kickoff/kickoff/motor.py` (`agendar_eventos`, `on_evento`), `recarga/robustez.py` (`deslocar_evento`)

**Interfaces:**
- Produces: `recarga.robustez.deslocar_evento(params: list, delta_min: int) -> list` (mesmo evento deslocado no tempo).

- [ ] **Step 1: Registrar** em `docs/eventos.md` o anúncio (título, agência, significado e formato de `params`) e salvar `eventos_ativos` (já feito por `operacao.py` em `resultados/eventos.json`).
- [ ] **Step 2: Escrever o teste que falha** com um cenário mínimo que exercite o evento conforme o anúncio (ex.: limite reduzido → `pico_kw` na janela do evento ≤ novo limite; carregador fora → nenhum carro pluga nele e, na volta, a fila é replugada).
- [ ] **Step 3: Implementar** os dois métodos e `deslocar_evento`.
- [ ] **Step 4: Validar contra o juiz** (Bangkok grátis, se o evento estiver lá): `python comparar.py sub.json resp.json --eventos ../resultados/eventos.json` → `OK: bate com o juiz`.
- [ ] **Step 5: Commit** `feat(motor): etapa 7 — eventos`.

---

## Frente D — operação

### Task D1: `recarga/juiz.py`

**Files:**
- Create: `recarga/juiz.py`, `recarga/testes/test_juiz.py`

**Interfaces:**
- Consumes: `kickoff.api.Cliente`, `kickoff.api.ErroApi`, `kickoff.dados.carregar`, `kickoff.validar`.
- Produces:
  - `carregar_env(path: Path = RAIZ/".env") -> None` (popula `os.environ` sem sobrescrever).
  - `chave(sub_normalizada: dict, eventos: list) -> str` (hash da Global Constraints).
  - `class Limitador(max_por_min=18, relogio=time.monotonic, dormir=time.sleep)` com `esperar() -> None`.
  - `class Juiz(cliente=None, raiz=RESULTADOS, dados=DADOS, reserva=300, teto_por_agencia: dict | None = None, autor: str = os.environ.get("USERNAME", "?"), limitador=None, dormir=time.sleep)`:
    - `status() -> dict` (também grava `raiz/"status.json"`), `catalogo() -> dict`, `placar() -> dict`, `kit(ag) -> Path`
    - `teste(ag, sub, detalhe="placar", confirmar=False) -> dict`
    - `final(ag, sub, confirmar=False) -> dict`
    - `eventos(ag) -> list` (params dos `eventos_ativos` da agência, do último status salvo)
  - Exceção `Recusado(Exception)` para travas locais (inválida, sem `confirmar`, reserva, teto, violação no nosso motor, idêntica ao vigente).

- [ ] **Step 1: Escrever os testes que falham** com um `ClienteFalso` (registra chamadas; respostas configuráveis):

```python
def test_cache_nao_chama_rede(self):       # 2ª chamada igual: len(falso.chamadas_teste) == 1
def test_hash_equivalentes(self):          # Review Focus 4
    a = {"agencia": "Bangkok", "carregadores": {"ac_7": 2, "dc_30": 1, "ac_11": 0}, "entrada": "b3_45"}
    b = {"entrada": "b3_45", "carregadores": {"dc_30": 1, "ac_7": 2},
         "politica": {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}, "agencia": "Bangkok"}
    self.assertEqual(chave(norm(a), []), chave(norm(b), []))
def test_invalida_nao_vai_para_rede(self):  # Recusado, falso sem chamadas
def test_paga_sem_confirmar_recusada(self): # agência != Bangkok, confirmar=False -> Recusado
def test_bangkok_nao_exige_confirmar(self):
def test_reserva_minima(self):              # saldo 310, placar 20 -> Recusado (310-20 < 300)
def test_429_espera_retry_em(self):         # Review Focus 5: 1ª resposta ErroApi(429,"cooldown",corpo={"retry_em":...}),
                                            # 2ª sucesso; dormir chamado 1x com segundos >= 0; resultado é o 2º
def test_ledger_so_registra_cobranca(self): # sucesso com taxa 20 -> 1 linha em ledger.jsonl; erro -> nenhuma
def test_final_identico_recusado_localmente(self)  # finais.jsonl tem o mesmo hash vigente -> Recusado
```

`retry_em` vem em ISO 8601 UTC; espera = `max(0, retry_em - agora)`. Agência pontuada nos testes = cenário de Bangkok copiado com nome `"Teste"` (use `dados` apontando para uma pasta temporária).

- [ ] **Step 2: Rodar** `python -m unittest recarga.testes.test_juiz -v` → FAIL.
- [ ] **Step 3: Implementar.** Taxa estimada antes da chamada: placar 20, completo 50 (30 se o placar do mesmo hash está no cache), Bangkok 0. Saldo vem de `status()`. Cache em `raiz/"juiz"/ag/f"{chave}_{detalhe}.json"`. Ledger: `{"t", "rota", "agencia", "hash", "taxa", "saldo", "autor"}`. `final()` simula com `recarga.lote.avaliar` só se o módulo existir (Task B1); antes disso, valida e checa idêntico.
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Teste manual com a API real** (precisa de `.env`): `python -c "import recarga.juiz as j; j.carregar_env(); print(j.Juiz().status()['fase'])"`.
- [ ] **Step 6: Commit** `feat(operacao): cliente do juiz com cache, ledger e travas`.

### Task D2: `recarga/operacao.py`

**Files:**
- Create: `recarga/operacao.py`, `recarga/testes/test_operacao.py`

**Interfaces:**
- Consumes: `Juiz` (Task D1).
- Produces: `class Monitor(juiz, raiz=RESULTADOS, dados=DADOS)` com `passo(agora: float) -> list[str]` (alertas da iteração) e `rodar(intervalo=60, placar_a_cada=300)`. CLI: `python -m recarga.operacao`.

- [ ] **Step 1: Escrever os testes que falham** com `JuizFalso` devolvendo uma sequência de status:

```python
def test_agencia_nova_baixa_kit(self):     # 2º status traz "Tokyo": juiz.kit("Tokyo") chamado 1x; alerta contém "Tokyo"
def test_evento_novo_grava_eventos_json(self):  # eventos.json == lista de eventos_ativos
def test_fase_clara_baixa_catalogo(self):  # dados/catalogo.json escrito 1x
def test_placar_a_cada_5_min(self):        # passos em agora=0,60,...,600 -> 3 linhas em placar.jsonl
def test_excecao_nao_derruba(self):        # status() levanta ErroApi: passo devolve alerta de erro, não propaga
```

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.** Estado anterior = `raiz/"status.json"` lido antes de sobrescrever. Alerta = `print` + `"\a"`.
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(operacao): monitor de status, kits, eventos e placar`.

### Task D3: `recarga/fidelidade.py`

**Files:**
- Create: `recarga/fidelidade.py`, `recarga/testes/test_fidelidade.py`

**Interfaces:**
- Consumes: `Juiz.teste` (D1), `simular.avaliar` e `comparar.comparar_metricas` / `comparar.comparar_series`.
- Produces: `matriz() -> list[dict]` (24 subs de Bangkok); `rodar(juiz, subs=None) -> list[dict]` com `{"sub", "ok": bool, "diverge": list[str]}`; CLI `python -m recarga.fidelidade` imprime tabela e `N/24 OK`.

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_matriz_24_validas_e_distintas(self):
    subs = matriz(); self.assertEqual(len(subs), 24)
    self.assertEqual(len({chave(norm(s), []) for s in subs}), 24)
    for s in subs: self.assertEqual(validar.validar(s, cen), [])
def test_rodar_marca_ok_quando_igual(self):   # JuizFalso devolve a própria simulação: todos ok
```

Matriz: carregadores `{"dc_60x2": 1, "ac_22x2": 1, "ac_7": 2}` (6 saídas); 3 `prioridade` × 2 `divisao` × 2 `evitar_ponta` × 2 limites (`b3_45`; `a4_150` com `demanda_contratada_kw` 130).

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar** (`detalhe="completo"`; captura o `print` de `comparar` com `contextlib.redirect_stdout`).
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Rodar contra o juiz** (grátis, ~24 min): `python -m recarga.fidelidade`. Meta final (após A5): `24/24 OK`. Divergências viram issues para a Frente A.
- [ ] **Step 6: Commit** `feat(operacao): matriz de fidelidade em Bangkok`.

---

## Frente B — otimização

### Task B1: `recarga/lote.py`

**Files:**
- Create: `recarga/lote.py`, `recarga/testes/test_lote.py`

**Interfaces:**
- Consumes: `kickoff.dados.carregar`, `validar`, `motor.simular`, `medicao.metricas`, `medicao.series`, `recarga.juiz.chave`.
- Produces:
  - `cenario(ag: str) -> Cenario` (cache por processo; usa `DADOS/"catalogo.json"` se existir).
  - `avaliar(ag, sub, eventos=(), series=False) -> dict` com chaves `hash`, `sub` (normalizada), `valido`, `erros`, `violacoes`, `metricas` (janela pública, inclui `demanda_contratada_kw`), `semanas` (lista de 4 dicts de métricas), `series` (se pedido). Cache em `RESULTADOS/"sim"/ag/f"{hash}.json"`.
  - `avaliar_lote(ag, subs, eventos=(), processos=None) -> list[dict]` (mesma ordem de `subs`; `ProcessPoolExecutor`, `processos=None` = `os.cpu_count() - 1`).

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_semanas_somam_publico(self):
    r = avaliar("Bangkok", EXEMPLO)
    self.assertEqual(sum(s["contratos"] for s in r["semanas"]), r["metricas"]["contratos"])
def test_cache_em_disco(self):            # 2ª chamada lê o arquivo (mockar motor.simular e verificar 1 chamada)
def test_lote_paralelo_igual_sequencial(self):
    subs = [EXEMPLO, {**EXEMPLO, "politica": {"prioridade": "chegada"}}]
    self.assertEqual([r["metricas"] for r in avaliar_lote("Bangkok", subs, processos=2)],
                     [avaliar("Bangkok", s)["metricas"] for s in subs])
def test_invalida_nao_simula(self):       # valido False, erros não vazio, sem "metricas"
```

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.** Semana `w` = `[T0 + w·10080, T0 + (w+1)·10080)`. O worker do pool é uma função de módulo (spawn no Windows).
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(otimizacao): avaliação em lote com cache e métricas por semana`.

### Task B2: `recarga/objetivo.py`

**Files:**
- Create: `recarga/objetivo.py`, `recarga/testes/test_objetivo.py`

**Interfaces:**
- Produces:
  - `ITENS_OPERACAO = ("certo", "upgrade", "nao_atendido", "demanda_contratada", "energia_ponta_kwh")` (nomes de `kickoff.nota.ITENS`).
  - `@dataclass Pesos: w: dict[str, float]` (pesos com sinal, como em `catalogo["pesos"][ag]`), `k_carregador: dict[str, float]`, `k_entrada: dict[str, float]` (pontos com sinal por unidade; `k = peso_infraestrutura × custo`).
  - `nota(metricas: dict, sub_norm: dict, entrada_existente: str, p: Pesos) -> float` (entrada existente custa 0).
  - `pesos_do_catalogo(cat: dict, ag: str) -> Pesos`.
  - `chave_lexicografica(metricas: dict, sub_norm: dict, cen) -> tuple` = `(atendimento_pct, certos, -kW_instalado)` (maior é melhor).

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_nota_igual_ao_kit(self):
    # catálogo falso com pesos e custos; mesmo resultado que nota.pontuar(m, cat["pesos"][ag])["nota"]
    # com m["custo_infra"] = nota.custo_infra(s, cen)["total"]
def test_entrada_existente_custa_zero(self):
def test_lexicografica_prefere_menos_kw_com_mesmo_atendimento(self):
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar.** **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(otimizacao): funções objetivo`.

### Task B3: `recarga/pesos.py`

**Files:**
- Create: `recarga/pesos.py`, `recarga/testes/test_pesos.py`

**Interfaces:**
- Consumes: `Pesos` (B2), `lote.avaliar` (B1), `Juiz.teste` (D1).
- Produces:
  - `features(metricas: dict, sub_norm: dict, entrada_existente: str) -> dict[str, float]`: chaves `certo`, `upgrade`, `nao_atendido`, `demanda_contratada`, `energia_ponta_kwh`, `car:<id>` (quantidade), `ent:<id>` (1 se ampliou).
  - `@dataclass Estimativa: pesos: Pesos, residuo_rms: float, n: int, confiavel: bool, nao_identificados: list[str]`.
  - `estimar(amostras: list[tuple[dict, float]]) -> Estimativa` (`numpy.linalg.lstsq`; `confiavel` = `residuo_rms <= 0.01 × média(|nota|)`; `nao_identificados` = colunas sempre zero).
  - `experimentos_bangkok() -> list[dict]` (≥ 40 subs válidas cobrindo os blocos da spec 5.1).
  - `coletar(juiz, ag, subs) -> list[tuple[dict, float]]` (nota do juiz + features do nosso motor; ignora sub com métricas físicas divergentes do juiz em `atendimento_pct`/`energia_kwh`/`pico_kw`).
  - `escala(est: Estimativa, amostras_ag) -> float` (fator único sobre os pesos operacionais que minimiza o erro na agência).
  - `salvar(est, path=RESULTADOS/"pesos"/"estimativa.json")`; CLI `python -m recarga.pesos coletar|estimar`.

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_recupera_pesos_sinteticos(self):
    # pesos conhecidos, 40 amostras de features aleatórias (com certo+upgrade+nao_atendido = 271 constante)
    est = estimar(amostras); self.assertTrue(est.confiavel)
    for k, v in reais.items(): self.assertAlmostEqual(est_valor(est, k), v, places=6)
def test_coluna_nunca_variada_nao_identificada(self):   # 'car:dc_120x2' nunca aparece -> em nao_identificados
def test_experimentos_validos_e_cobrem_blocos(self):
    # todos validam em Bangkok; >= 40; cada carregador e cada entrada aparece em >= 2 subs;
    # existe par que só difere em demanda e par que só difere em evitar_ponta
def test_escala(self):  # amostras = notas reais × 1.5 nos itens operacionais -> escala ≈ 1.5
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar.** **Step 4: Rodar** → PASS.
- [ ] **Step 5: Rodar de verdade** (após D3 dar OK nas métricas físicas): `python -m recarga.pesos coletar` (Bangkok, grátis, ~40 min) e `python -m recarga.pesos estimar`.
- [ ] **Step 6: Commit** `feat(otimizacao): inferência de pesos na Neblina`.

### Task B4: `recarga/otimizador.py`

**Files:**
- Create: `recarga/otimizador.py`, `recarga/testes/test_otimizador.py`

**Interfaces:**
- Consumes: `lote.avaliar_lote`, `lote.cenario` (B1), `objetivo` (B2), `Estimativa` em `RESULTADOS/"pesos"/"estimativa.json"` (B3, opcional).
- Produces:
  - `politicas() -> list[dict]` (12 combinações).
  - `vizinhos(carregadores: dict, vagas: int) -> list[dict]` (adicionar 1, trocar tipo, remover 1; Σ saídas ≤ vagas; ≥ 1 carregador).
  - `entrada_para(demanda_kw: int | None, existente: str, cen) -> str` (mais barata pela ordem de kVA que comporta a demanda e não é abaixo da existente).
  - `objetivo_padrao(ag) -> Callable[[dict], float | tuple]` (nota exata se `catalogo.json` tem pesos; senão estimativa confiável com `escala`; senão lexicográfica).
  - `varrer_demanda(ag, carregadores, politica, obj) -> list[dict]` (`{"demanda", "entrada", "valor"}`; inclui opções B3).
  - `buscar(ag, modo="rapido", obj=None) -> list[dict]` (ranking de resultados de `lote.avaliar`, melhor primeiro, com campo `valor`). `rapido`: 1 partida, política fixa nas 2 melhores; `completo`: 4 partidas.
  - Arquivos: `RESULTADOS/"otimizador"/ag/"ranking.json"` (top 20) e `"demanda.json"`.
  - CLI: `python -m recarga.otimizador AG [--modo rapido|completo]` imprime a sub escolhida (após `robustez.escolher`, Task B5, quando existir).

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_12_politicas(self):
def test_vizinhos_respeitam_vagas(self):  # vagas=6, {"dc_60x2": 3} -> nenhum vizinho com 8 saídas; nenhum vazio
def test_entrada_para(self):              # demanda 140, existente b3_45 -> "a4_225"; None -> existente
def test_buscar_rapido_bangkok_valido_e_melhor_que_exemplo(self):
    r = buscar("Bangkok", "rapido")[0]
    self.assertTrue(r["valido"]); self.assertGreaterEqual(r["metricas"]["atendimento_pct"], exemplo_atendimento)
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar** a busca da spec 5.2 (política → busca local → varredura de demanda). **Step 4: Rodar** → PASS; anotar tempo de `buscar("Bangkok", "rapido")` (meta < 10 min).
- [ ] **Step 5: Commit** `feat(otimizacao): otimizador por agência`.

### Task B5: `recarga/robustez.py`

**Files:**
- Create: `recarga/robustez.py`, `recarga/testes/test_robustez.py`
- Modify: `recarga/otimizador.py` (CLI usa `escolher`)

**Interfaces:**
- Produces: `escolher(ranking: list[dict], obj_semana: Callable[[dict, dict], float], top=10) -> dict` — entre os `top` primeiros, maior `min` do objetivo por semana; desempate pela média. `obj_semana(metricas_semana, sub_norm)`.

- [ ] **Step 1: Escrever os testes que falham**:

```python
def test_prefere_melhor_pior_semana(self):  # A semanas [10,10,10,2], B [8,8,8,8] -> B
def test_desempate_pela_media(self):        # mesmo mínimo -> maior média
def test_so_considera_top(self):            # candidato fora do top não é escolhido
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar.** **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(otimizacao): escolha robusta pela pior semana`.

---

## Frente C — dashboard

### Task C1: `dashboard/dados.py` + dados de exemplo

**Files:**
- Create: `dashboard/__init__.py`, `dashboard/dados.py`, `dashboard/exemplo.py`, `dashboard/testes/__init__.py`, `dashboard/testes/test_dados.py`

**Interfaces:**
- Produces (todas recebem `raiz: Path`, padrão `Path(os.environ.get("RESULTADOS_DIR", RESULTADOS))`; arquivo ausente → lista/dict vazio):
  - `ledger(raiz) -> list[dict]`, `gasto_por_agencia(raiz) -> dict[str, int]`, `placar(raiz) -> list[dict]`, `finais(raiz) -> list[dict]`, `status(raiz) -> dict`
  - `respostas_juiz(raiz, ag) -> dict[str, dict]` (hash → resposta), `simulacoes(raiz, ag) -> dict[str, dict]`
  - `ranking(raiz, ag) -> list[dict]`, `demanda(raiz, ag) -> list[dict]`, `pesos(raiz) -> dict`
  - `exemplo.gerar(raiz: Path) -> None`: escreve arquivos de exemplo em todos os formatos da spec 3.2 (agência `"Bangkok"`, 2 respostas do juiz com `series`, 5 linhas de ledger, 3 de placar).

- [ ] **Step 1: Escrever os testes que falham**: gerar em `tempfile.TemporaryDirectory()` e conferir `gasto_por_agencia` igual à soma das taxas do exemplo; `respostas_juiz` com 2 itens; pasta vazia → tudo vazio sem exceção.
- [ ] **Step 2: Rodar** `python -m unittest discover -s dashboard/testes -t .` → FAIL. **Step 3: Implementar.** **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(dashboard): leitura de resultados e dados de exemplo`.

### Task C2: `dashboard/graficos.py`

**Files:**
- Create: `dashboard/graficos.py`, `dashboard/testes/test_graficos.py`

**Interfaces:**
- Produces (todas devolvem `plotly.graph_objects.Figure`):
  - `cascata(itens_meu: list, itens_juiz: list | None)` (formato `pontos.itens`: `[item, qtd, peso, pontos]`)
  - `potencia(series: dict, limite_kw: float, horario: list)` (linha de limite; retângulos de ponta seg–sex 18–21h; retângulos de horário fechado)
  - `ocupacao(series: dict, saidas: int, vagas: int)`
  - `soc_retirada(soc: list)` (linha vertical em 80)
  - `perdas(nao_atendidos_min: list, inicio_min: int)` (heatmap 7 dias × 24 h)
  - `gastos(ledger: list)`, `evolucao(placar: list, numero_equipe: int)`, `curva_demanda(demanda: list, escolhida: int | None)`, `pesos_vs_reais(estimados: dict, reais: dict | None)`

- [ ] **Step 1: Escrever os testes que falham** usando `exemplo.gerar`:

```python
def test_potencia_tem_ponta_e_limite(self):  # 4 semanas -> 20 retângulos de ponta; 1 linha horizontal em limite_kw
def test_perdas_heatmap_7x24(self):          # z tem shape 7x24; perda em inicio+60 cai em (dia de inicio, hora+1)
def test_cascata_soma_nota(self):            # soma dos y == soma de pontos
def test_tudo_funciona_vazio(self):          # cada função com listas vazias devolve Figure sem exceção
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar.** **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat(dashboard): gráficos`.

### Task C3: `dashboard/app.py`

**Files:**
- Create: `dashboard/app.py`, `dashboard/testes/test_app.py`

**Interfaces:**
- Consumes: `dashboard.dados`, `dashboard.graficos`, `recarga.lote.avaliar(ag, sub, series=True)`.
- Produces: app Streamlit com páginas "Agência" (seletor de agência e de submissão: vigente em `finais`, candidatas do `ranking`) e "Consolidado"; rodar com `streamlit run dashboard/app.py`.

- [ ] **Step 1: Escrever o teste que falha** (`streamlit.testing.v1.AppTest`):

```python
def test_app_sobe_com_exemplo(self):
    with tempfile.TemporaryDirectory() as d:
        exemplo.gerar(Path(d)); os.environ["RESULTADOS_DIR"] = d
        at = AppTest.from_file("dashboard/app.py", default_timeout=60).run()
        self.assertFalse(at.exception)
```

- [ ] **Step 2: Rodar** → FAIL. **Step 3: Implementar** os painéis da spec 7.1 (`st.cache_data(ttl=60)` na leitura; cascata marcada "estimado" quando não há `pontos` do juiz; tabela de fidelidade reaproveitando `comparar.comparar_metricas` com saída capturada).
- [ ] **Step 4: Rodar** → PASS; abrir `streamlit run dashboard/app.py` com os dados de exemplo e conferir visualmente as duas páginas.
- [ ] **Step 5: Commit** `feat(dashboard): app Streamlit`.

---

## Verificação final (antes de H7:00)

- [ ] Suíte do kit, do pacote e do dashboard → PASS.
- [ ] `python -m recarga.fidelidade` → `24/24 OK`.
- [ ] `resultados/finais.jsonl` tem envio vigente para cada agência pontuada liberada (conferir com `GET /status`, campo `vigente`).
