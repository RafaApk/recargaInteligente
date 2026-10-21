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

## Estado atual (21/10/2026, fase Clara — após H4)

**Pesos oficiais (GET /catalogo, iguais aos que inferimos na Neblina)** — `pesos_estimados/pesos_bangkok_confirmados.json`
e `kit_kickoff/dados/catalogo.json`:
- certo **+15**, upgrade **+8**, não atendido **−200**, energia na ponta **−0,5/kWh**, demanda **−2/kW**, infraestrutura **−1/ponto**.
- Obra: ac_7 250, ac_11 1100, ac_22x2 1500, dc_30 3500, dc_60x2 7300, dc_120x2 15800;
  b3_75 5000, a4_150 6500, a4_225 8200, a4_300 10000, se_500 18800, se_750 24400, se_1000 30000, se_1500 41200, se_2000 52500.
- Mesmos pesos em todas as agências liberadas.

**Fidelidade do motor:** reproduz exatamente as notas do juiz (38 testes em Bangkok, Istanbul 7095=7095; Hanoi e Zurich
com erro < 1%). Corrigido: empate exato de km em `menor_soc` (arredondamento do ponto flutuante).
`fila_max` difere só na medição. **Eventos (etapa 7): implementação provisória NÃO verificada** (ver pendências).

**Lição principal:** a obra domina a nota. AC barato em quantidade costuma vencer DC caro
(Bangkok: 3× ac_7 proxima_retirada ≈ 3100; 1× dc_30 = 565). A nota final usa **só as 4 semanas ocultas** —
escolher pela **pior semana**, não pela melhor média (Zurich caiu de 3003 público para 132 oculto: perdas concentradas).

**Envios finais (vigentes):**

| Agência | Config | Nota pública (juiz) | Nota oculta (placar) |
|---|---|---|---|
| Istanbul | dc_60x2, b3_75, proxima_retirada, evitar_ponta, igual | 7095 | 6685 |
| Hanoi | ac_7×2 + dc_60x2, b3_75, proxima_retirada, sem evitar_ponta, igual | 3519 | 3093 |
| Zurich | ac_7 + dc_60x2, b3_75 (existente), proxima_retirada, sem evitar_ponta, prioridade | 3003 | 132 |
| Marrakech | **sem envio — pronta para enviar: `configs/marrakech/final-pronto.json`** (7×ac_7 + ac_22x2 + dc_30, a4_150, 130 kW, proxima_retirada, evitar_ponta, igual) | 4842 (juiz) | — |

Placar às 17:10 UTC: total 9909,93; saldo **920 m7Coins**; 2 agências ainda a liberar. Reenvio final custa 80/160/320.

**Em andamento:** `resultados/exaustivo.py` (busca exaustiva com nota robusta pela pior semana) → `resultados/exaustivo.json`.


**Pronta para enviar depois (Zurich):** `configs/zurich/conservadora-pronta.json` (ac_7×2 + dc_60x2, b3_75, proxima_retirada, prioridade) — melhor sob estresse de potência; reenvio custa 80.

## Pendências

1. **Evento de Marrakech** (`["corte","Marrakech",31680,34560,0.7]`, carta "Pedido da concessionária"): nenhum fator
   simples (limite × f na janela) reproduz o juiz. Precisa da série do juiz (`detalhe=completo`, 30 m7Coins) para
   descobrir a regra. Nas semanas ocultas ocorre evento equivalente em horário desconhecido.
2. Reavaliar Zurich e Hanoi com a busca exaustiva/robusta e decidir reenvio (80 m7Coins cada).
3. Marrakech: fazer o 1º envio final (grátis) — agência sem envio vale 0.
4. `objetivo.chave_lexicografica` ignora ponta/demanda/entrada (irrelevante agora que há pesos oficiais).
5. `operacao.Monitor` não recupera estado inicial; falta CLI guardado de envio final; recarregar catálogo na Clara.

Detalhes da execução e decisões: `docs/superpowers/` e o ledger local `.superpowers/sdd/.../progress.md` (git-ignored, só na máquina do Caio).
