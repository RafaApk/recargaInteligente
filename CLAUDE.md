---
title: Recarga Inteligente — contexto para o Claude
date: 2026-10-21
---

# Recarga Inteligente — contexto do projeto

Equipe **#14** no Hackathon Recarga Inteligente (Localiza / m7). Responda em **português**.

## O jogo em 1 minuto

Operamos uma rede fictícia de agências de aluguel de carros elétricos. Para cada agência enviamos um JSON com:
**carregadores**, **entrada elétrica**, **demanda contratada** (só A4/SE) e **política de recarga**.
Um **juiz** (simulador oficial) reproduz a operação e dá a nota.

- O cliente chega → precisa de carro da **categoria pedida ou superior** com **SOC ≥ 80%**. Sem carro apto = cliente perdido.
- Nota = + atendidos certos + upgrades − perdidos − kW de demanda contratada − kWh na ponta (seg–sex 18–21h) − custo de obra.
- **Neblina (H0–H4):** pesos e custos ocultos. **Clara (H4+):** publicados em `GET /catalogo`.
- Testes avaliam as **4 semanas públicas**; a nota final usa **4 semanas ocultas** → generalizar, não decorar.
- 6 agências pontuadas, liberadas ao longo do dia. **Bangkok** é tutorial: testes grátis, não pontua.
- A regra completa e autoritativa está em `REGULAMENTO_EQUIPES.md` (seções 5 e 6.3 = regras do simulador).

## ⚠️ Regras de segurança (obrigatórias)

1. **Nunca gaste m7Coins sem autorização explícita do humano.** Teste placar = 20, completo = 50, reenvio final = 80/160/320…
   Testes em **Bangkok são grátis** (cooldown 1 min). 1º envio final de cada agência é grátis, mas **só envie com ok do humano**.
2. Toda chamada à API passa por `recarga.juiz.Juiz` (cache, ledger, travas). Chamadas pagas exigem `confirmar=True`.
3. **A PalavraChave nunca entra em commit.** Fica em `.env` (ignorado). Use `.env.example` como modelo:
   `GAMEDAY_URL=https://z8tfjfyhgj.execute-api.us-east-1.amazonaws.com/prod` e `GAMEDAY_TOKEN=<sua PalavraChave>`.
4. Rate limit da API: 20 req/min **por equipe** (somando todos os membros e a página `/docs` aberta).
5. Não altere os arquivos do kit (`kit_kickoff/kickoff/*.py`), **exceto `motor.py`**. Eles já batem com o juiz.

## Estrutura

```
REGULAMENTO_EQUIPES.md        regras oficiais (fonte da verdade)
kit_kickoff/                  kit oficial (Python, só stdlib)
  kickoff/motor.py            ★ nosso simulador (etapas 2–6 implementadas; eventos/etapa 7 pendente)
  kickoff/{dados,validar,potencia,medicao,nota,tempo,api}.py   helpers do kit — não alterar
  simular.py, comparar.py     simular submissão / comparar com resposta do juiz
  testes/                     testes do kit + test_etapa2..6.py + apoio.py
  dados/<Agencia>/            kits das agências (git-ignored)
recarga/                      nosso pacote (importar `recarga` põe kit_kickoff no sys.path)
  juiz.py                     cliente da API: cache por hash, ledger, travas de m7Coins, kit em base64
  operacao.py                 monitor de /status e /placar (python -m recarga.operacao)
  fidelidade.py               matriz de 24 submissões em Bangkok vs juiz (python -m recarga.fidelidade)
  lote.py                     avalia submissões no motor (cache em resultados/sim, métricas por semana)
  objetivo.py                 funções objetivo (nota com pesos; lexicográfica sem pesos)
  pesos.py                    inferência de pesos por mínimos quadrados (Neblina)
  otimizador.py               busca por agência (python -m recarga.otimizador AG --modo rapido|completo)
  robustez.py                 escolha pela melhor pior semana
  melhores.py                 gera melhores-resultados.json (python -m recarga.melhores)
  chave.py                    hash canônico de submissão (chave de cache)
dashboard/                    Streamlit (streamlit run dashboard/app.py)
configs/<agencia>/*.json      configs candidatas/recomendadas
resultados/                   saídas (contrato entre módulos; ver abaixo)
data/<Agencia>/               kits baixados à mão pelo site (git-ignored na prática; sincronizados por recarga.melhores)
melhores-resultados.json      melhor config por agência (teste) + situação do final
docs/superpowers/specs|plans  spec de design e plano de implementação
```

### `resultados/` (formato fixo — o dashboard depende dele)

| Arquivo | Escrito por |
|---|---|
| `juiz/<Ag>/<hash>_<placar\|completo>.json` | `juiz.py` (resposta crua do juiz) |
| `ledger.jsonl` | `juiz.py` (uma linha por cobrança: t, rota, agencia, hash, taxa, saldo, autor) |
| `finais.jsonl` | `juiz.py` (envios finais aceitos, com `sub` normalizada) |
| `status.json`, `eventos.json`, `placar.jsonl` | `juiz.py` / `operacao.py` |
| `sim/<Ag>/<hash>.json` | `lote.py` (git-ignored) |
| `otimizador/<Ag>/ranking.json`, `demanda.json` | `otimizador.py` |
| `testes-juiz-bangkok.json` | consolidado dos testes do juiz em Bangkok |

Hash = SHA-256 do JSON canônico de `{"sub": validar.normalizar(sub, cen), "eventos": [...]}` (mesma regra de "teste idêntico" do juiz).

## Comandos

```bash
pip install -r requirements.txt                         # numpy, streamlit, plotly
cd kit_kickoff && python -m unittest discover -s testes # 60 testes do motor
python -m unittest discover -s recarga/testes -t .      # pacote (rodar da raiz)
python -m unittest discover -s dashboard/testes -t .    # dashboard (~70 s)
python -m recarga.melhores                              # sincroniza data/ e atualiza melhores-resultados.json
python -m recarga.otimizador Istanbul --modo rapido     # busca de config (sem API)
cd kit_kickoff && python simular.py ../configs/bangkok/recomendada.json
streamlit run dashboard/app.py
```

Kit de uma agência nova: baixe pelo site, coloque em `data/<Agencia>` e rode `python -m recarga.melhores`
(ou, com `.env`, `python -c "import recarga.juiz as j; j.carregar_env(); j.Juiz().kit('Agencia')"`).

## Convenções

- Python 3.10+ (máquina usa 3.14), `unittest`, TDD: teste falhando → implementação → suíte verde → commit.
- Tempo em **minutos desde domingo 17/10/2049 00:00**; T0 = 1080; dia = 1440; semana = 10080.
- Desempate final em toda ordenação do motor: menor `id` alfabético.
- `multiprocessing` precisa funcionar no Windows (spawn): workers em funções de módulo.
- Commits em português, estilo `feat(area): ...`/`fix(area): ...`. Branch de trabalho: `design/recarga-inteligente`.

## Estado atual (21/10/2026 ~21h UTC, fase Clara, etapa H6 — todas as 6 agências com envio)

**Pesos oficiais por agência** (`GET /catalogo` → `kit_kickoff/dados/catalogo.json`; use `recarga.melhores.pesos_agencia(ag)`):
- Todas: certo **+15**, upgrade **+8**, não atendido **−200**, demanda **−2/kW**, infraestrutura **−1/ponto**.
- Energia na ponta: **−0,5/kWh**, exceto **Lisbon: −5/kWh** (10×). Os pesos podem mudar por agência durante o dia.
- Obra: ac_7 250, ac_11 1100, ac_22x2 1500, dc_30 3500, dc_60x2 7300, dc_120x2 15800;
  b3_75 5000, a4_150 6500, a4_225 8200, a4_300 10000, se_500 18800, se_750 24400, se_1000 30000, se_1500 41200, se_2000 52500.

**Fidelidade do motor** (`resultados/calibracao.py`, 9 notas do juiz fora Bangkok + 38 em Bangkok):
- Exato: Bangkok, Istanbul (7095 e 8826,28), Marrakech 4842, Vienna 11630. Hanoi/Zurich/Marrakech: erro de 13 a 243.
- Correções: empate exato de km em `menor_soc`; **fila de T0 plugada carro a carro em ordem de id**
  (`PLUG_T0_EM_LOTE = False`, confirmado em Istanbul).
- Divergência aberta: filas longas com várias saídas liberando no mesmo minuto (`proxima_retirada`) — o motor é
  otimista (Marrakech ac_22x2×5: motor 807, juiz −3759; Lisbon: motor 10455, juiz 9310).
- `fila_max` difere só na medição (juiz registra só aumentos).

**Eventos ao vivo** (motor, `agendar_eventos`/`on_evento`):
- Carta 1, Marrakech `["corte", ag, ini, fim, f]`: limite da agência × f na janela — **confirmado** (77 kW = 0,7 × 110).
- Carta 2, Istanbul `["quebra_maiores", ag, n, ini, fim]`: os n carregadores de maior potência ficam a 0 kW
  (carro segue plugado) na janela; na volta a fila é replugada — **não validado no juiz**, placar coerente.
- Nas semanas ocultas o evento equivalente cai em horário desconhecido → avaliar com o evento deslocado.

**Lições:** a obra domina a nota (AC barato em quantidade > DC caro); a nota final usa **só as semanas ocultas**
(escolher pela pior semana/cenário); confira os pesos de cada agência no catálogo (Lisbon!).

**Envios finais vigentes:**

| Agência | Envio | Config | Pública (juiz) | Oculta (placar) |
|---|---|---|---|---|
| Istanbul | 3º | ac_7 + dc_30×3, b3_75, proxima_retirada, igual (resistente à quebra) | — | 1703 |
| Hanoi | 2º | ac_7×5 + dc_30, b3_75, proxima_retirada, igual (Matheus) | 6211 | 5763 |
| Marrakech | 1º | ac_7×9 + dc_30, a4_150 100 kW, proxima_retirada, evitar_ponta, prioridade (Antonio) | 5152 | 6898 |
| Zurich | 2º | ac_7×2 + dc_60x2, b3_75, proxima_retirada, prioridade | — | 40 |
| Vienna | 2º | ac_7×4, a4_150 30 kW, evitar_ponta, igual | — | 12077 |
| Lisbon | 1º | ac_7×4 + dc_30×2, a4_150 100 kW, proxima_retirada, **evitar_ponta**, igual | 9310 | (aguardando) |

Saldo **135 m7Coins**. Próximo reenvio: Hanoi/Vienna/Zurich 160, Marrakech/Lisbon 80, Istanbul 320.
Alternativa guardada: `configs/zurich/anterior-pronta.json` (1º envio, oculta 131,86 > 40 atual; reenvio custa 160 > saldo).

## Pendências

1. Divergência de fila longa em `proxima_retirada` (afeta Marrakech, Hanoi, Lisbon) — regra exata desconhecida.
2. Validar `quebra_maiores` com um teste do juiz (Istanbul).
3. `operacao.Monitor` não recupera estado inicial; falta CLI guardado de envio final; recarregar catálogo na Clara.

Detalhes da execução e decisões: `docs/superpowers/` e o ledger local `.superpowers/sdd/.../progress.md` (git-ignored, só na máquina do Caio).
