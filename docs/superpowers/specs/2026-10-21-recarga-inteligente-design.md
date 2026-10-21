---
title: Recarga Inteligente — design da solução
date: 2026-10-21
---

# Recarga Inteligente — design da solução

Hackathon Recarga Inteligente (regulamento: `REGULAMENTO_EQUIPES.md`). Este documento define a arquitetura, os componentes e o modo de operação da equipe durante as 8 h de jogo.

## 1. Objetivo e critérios de sucesso

**Objetivo:** maximizar a soma das notas das 6 agências pontuadas nas semanas ocultas, escolhendo por agência carregadores, entrada elétrica, demanda contratada e política de recarga.

**Critérios de sucesso:**

1. Motor próprio fiel ao juiz: `comparar.py` imprime `OK: bate com o juiz` em Bangkok para toda a matriz de fidelidade (seção 7.2).
2. Toda agência pontuada tem envio final vigente antes de H7:00 (congelamento em H7:30).
3. Pesos e custos de obra estimados na Neblina, comparáveis ao Anexo H4.
4. Dashboard obrigatório (regulamento 13.1) completo, alimentado pelos dados reais do dia.
5. m7Coins gastos de forma rastreável (registro por chamada).

**Fora de escopo:** otimizar o saldo final de m7Coins (não pontua); reescrever o kit em outra linguagem; gerador de cenários sintéticos (extra opcional, só se sobrar tempo).

## 2. Decisões tomadas

| Decisão | Escolha | Motivo |
|---|---|---|
| Base do simulador | Completar `kit_kickoff/kickoff/motor.py` (Python) | Helpers já batem com o juiz; caminho mais curto até a fidelidade |
| Organização | Time de 4–6 pessoas em 4 frentes paralelas | Jogo de 8 h; frentes com arquivos disjuntos |
| Dashboard | Streamlit + Plotly | Lê direto do motor e de `resultados/`; mais rápido de construir |
| Momento | Construção a partir de H0 | ~8 h disponíveis |

## 3. Arquitetura

O kit permanece intacto, exceto `motor.py` e os testes novos. O código da equipe fica no pacote `recarga/`, que importa `kickoff`.

```
recargaInteligente/
├── kit_kickoff/
│   ├── kickoff/motor.py          Frente A: etapas 2–7
│   ├── testes/test_etapaN.py     Frente A: um teste por etapa
│   └── dados/{Agencia}/          kits baixados (não versionados)
├── recarga/
│   ├── juiz.py                   Frente D: cliente da API com cache, ledger e travas
│   ├── operacao.py               Frente D: monitor de /status e /placar
│   ├── fidelidade.py             Frente A/D: matriz de fidelidade em Bangkok
│   ├── lote.py                   Frente B: avaliação paralela de submissões
│   ├── pesos.py                  Frente B: inferência de pesos (Neblina)
│   ├── otimizador.py             Frente B: busca por agência
│   └── robustez.py               Frente B: nota por semana e critério de escolha
├── dashboard/app.py              Frente C
├── resultados/                   contrato de dados entre as frentes (seção 3.2)
├── .env                          GAMEDAY_URL e GAMEDAY_TOKEN (no .gitignore)
└── docs/superpowers/specs/       este documento
```

Dependências: o kit continua só com biblioteca padrão. O pacote `recarga/` e o dashboard podem usar `numpy`, `streamlit` e `plotly` (`requirements.txt` na raiz).

**Segredo:** a PalavraChave nunca entra em commit. `.env` e `kit_kickoff/dados/` ficam no `.gitignore`.

### 3.1 Interfaces entre as frentes

- `simular.avaliar(sub, cenarios, dados, cat, eventos, series)` (já existe no kit) devolve métricas no formato de `POST /teste`. Frentes B e C dependem só disso e podem começar com o motor vazio.
- `recarga.juiz.Juiz` é a única porta para a API. Métodos: `status()`, `catalogo()`, `placar()`, `kit(ag)`, `teste(ag, sub, detalhe, confirmar=False)`, `final(ag, sub, confirmar=False)`.
- `recarga.lote.avaliar_lote(ag, subs, semanas=True) -> list[dict]`: métricas públicas e por semana (1–4) de cada submissão, com cache em `resultados/sim/`.

### 3.2 Contrato de dados (`resultados/`)

| Arquivo | Escrito por | Conteúdo |
|---|---|---|
| `juiz/{ag}/{hash}.json` | `juiz.py` | resposta do juiz para a submissão normalizada + eventos ativos |
| `sim/{ag}/{hash}.json` | `lote.py` | saída do nosso motor, com `series` |
| `ledger.jsonl` | `juiz.py` | uma linha por chamada: horário, rota, agência, hash, taxa, saldo, autor |
| `status.json` | `operacao.py` | último `GET /status` |
| `eventos.json` | `operacao.py` | `eventos_ativos` no formato aceito por `simular.py --eventos` |
| `placar.jsonl` | `operacao.py` | `GET /placar` a cada 5 min |
| `finais.jsonl` | `juiz.py` | histórico de envios finais aceitos |
| `otimizador/{ag}/ranking.json` | `otimizador.py` | top candidatos com nota pública, por semana e critério de robustez |
| `otimizador/{ag}/demanda.json` | `otimizador.py` | varredura nota × demanda contratada |
| `pesos/estimativa.json` | `pesos.py` | pesos e custos estimados, resíduo, nº de testes usados |

O `hash` é o SHA-256 do JSON canônico (chaves ordenadas) de `{"sub": validar.normalizar(sub), "eventos": eventos_ativos_da_agencia}` — a mesma noção de "teste idêntico" do regulamento 9.1.

## 4. Frente A — motor fiel ao juiz

Implementar os `# TODO(etapa N)` de `kickoff/motor.py` na ordem do `kit_kickoff/LEIAME.md` (etapas 2 a 7), seguindo as docstrings e o `AGENTS.md` do kit. Uma etapa por vez, com `testes/test_etapaN.py` usando os exemplos numéricos do regulamento (6.3.1 a 6.3.7).

- Etapas 2–6 antes de H4. Etapa 7 (eventos) implementada quando o primeiro evento for anunciado, a partir do formato de `params` divulgado.
- Logo após a etapa 3, medir o tempo de uma simulação de Bangkok. Meta: < 2 s por simulação em agências grandes; acima disso, a Frente B reduz a busca.
- Pronto quando a matriz de fidelidade (7.2) passa inteira.

## 5. Frente B — pesos, otimizador e robustez

### 5.1 Inferência de pesos (`pesos.py`)

Modelo linear da nota de um teste na Neblina, com as quantidades calculadas pelo nosso motor:

```
nota = a·certos + b·upgrades − c·nao_atendidos − d·kW_contratado − e·kWh_ponta
       − Σ_i (qtd_i · k_i) − k_entrada
```

- `k_i` e `k_entrada` são o produto (peso da obra × custo de obra); não é preciso separá-los.
- Incógnitas: `a, b, c, d, e`, 6 `k_i` de carregadores e 9 `k_entrada` (todas as entradas exceto `b3_45`, que custa 0 como existente).
- Como `certos + upgrades + nao_atendidos = T` é constante numa agência, o termo `−c·T` age como intercepto; `c` continua identificável.
- Solução por mínimos quadrados (`numpy.linalg.lstsq`). Saída com estimativas, resíduo RMS e nº de testes.

**Pré-requisito:** métricas físicas do motor iguais às do juiz (`atendimento_pct`, `energia_kwh`, `pico_kw`) para as submissões usadas. Resíduo RMS acima de 1% da nota média marca a estimativa como não confiável.

**Desenho de experimentos em Bangkok** (grátis, cooldown 1 min):

| Bloco | Variação | Isola |
|---|---|---|
| Demanda | A4 com demanda acima do pico, passos de 10 kW | `d` |
| Ponta | `evitar_ponta` ligado e desligado | `e` |
| Carregadores | variações de quantidade e tipo | `k_i` |
| Entradas | mesma operação com cada nível de entrada | `k_entrada` |
| Operação | infra fraca (muitas perdas) e forte | `a, b, c` |

**Pesos por agência:** o regulamento permite pesos diferentes por agência. Custos de obra são tratados como globais. Em cada agência pontuada: 1 teste placar (20 m7Coins) compara nota prevista e real; se o erro passar de 5%, mais 2–3 testes reajustam só a escala de `a, b, c, d, e` daquela agência.

A partir de H4, pesos e custos vêm de `GET /catalogo` (`dados/catalogo.json`) e a nota passa a ser exata (`nota.pontuar`). A estimativa é guardada para comparação.

### 5.2 Otimizador (`otimizador.py`)

Busca decomposta:

1. **Política:** para 3–5 infraestruturas razoáveis, avaliar as 12 combinações (`prioridade` × `divisao` × `evitar_ponta`); manter as 2–3 melhores.
2. **Carregadores:** busca local a partir de uma configuração mínima. Movimentos: adicionar um carregador, trocar tipo (AC↔DC, 1↔2 saídas), remover um. Aceita o melhor movimento que melhora a nota; respeita Σ saídas ≤ vagas. Alguns reinícios.
3. **Demanda e entrada:** para os carregadores escolhidos, varrer demanda de 30 kW até a soma das potências nominais, em passos de 10; a entrada é a mais barata que comporta a demanda. Comparar também com manter B3 (`b3_45`/`b3_75`, sem demanda).
4. **Objetivo:** antes da estimativa de pesos, ordem lexicográfica (maior atendimento → mais certos → menor kW instalado); com a estimativa, nota estimada; após H4, nota exata.

Todo candidato passa por `validar.validar` antes de ser simulado. Modo rápido (passos 1 e 2 com uma única partida) para o primeiro envio; modo completo para os seguintes.

### 5.3 Robustez (`robustez.py`)

Uma simulação produz a nota de cada semana pública (1–4) via `medicao.metricas` com a janela da semana. Critério de escolha: entre os 10 melhores pela nota pública, a configuração com **melhor pior semana**; desempate pela média.

## 6. Frente D — operação ao vivo

### 6.1 `juiz.py`

- Lê `GAMEDAY_URL` e `GAMEDAY_TOKEN` do `.env`; usa `kickoff.api.Cliente`.
- Valida localmente antes de enviar; inválida não vai à rede.
- Cache por hash (3.2): hit não chama a rede.
- Chamada paga exige `confirmar=True`; é recusada se o saldo após a taxa ficar abaixo da reserva mínima (padrão 300 m7Coins, configurável) ou se exceder o teto por agência.
- Rate limit no cliente (≤ 18 req/min) e, em `429`, espera `retry_em` e tenta de novo uma vez.
- `final()` só envia se: validação local ok, nossa simulação sem violações e submissão diferente da vigente.
- Ledger só registra taxa efetivamente cobrada (resposta de sucesso).

**Dono da carteira:** só a pessoa da Frente D faz chamadas pagas e envios finais. A página `/docs` fica fechada durante o jogo (conta no rate limit).

### 6.2 `operacao.py`

Laço com `GET /status` a cada 60 s e `GET /placar` a cada 5 min. Sobrevive a exceções.

| Detecção | Ação |
|---|---|
| Agência nova liberada | baixa o kit para `kit_kickoff/dados/{Ag}`, roda `kickoff.dados`, alerta no console |
| Carta ou evento novo | grava `resultados/eventos.json`, alerta |
| Fase `clara` | baixa `GET /catalogo` para `kit_kickoff/dados/catalogo.json` |
| Sempre | grava `status.json`; placar em `placar.jsonl` |

### 6.3 Fluxo por agência

1. Liberou: kit baixado automaticamente.
2. Até 10 min depois: otimizador em modo rápido e **1º envio final** (grátis).
3. Otimizador completo + robustez.
4. 1 teste placar de calibração (5.1).
5. Reenvio só se o ganho estimado for relevante (custo 80, 160, 320…; cooldown 15 min).
6. Em H4: rodada com pesos exatos; reenviar onde a escolha mudou.

### 6.4 Eventos

- Etapa 7 do motor implementada no anúncio do primeiro evento.
- Reação avaliada primeiro no nosso motor (e em Bangkok, se o evento for lá).
- Nas semanas ocultas o evento cai em horário desconhecido: simular o evento deslocado para vários dias e horários e escolher pelo melhor pior caso.

### 6.5 Política de saldo

O saldo final não pontua; só tem valor de opção. Reserva mínima de 300 m7Coins até a última agência ser liberada; depois a reserva é liberada para calibrações e reenvios. Em H7:00, checagem de que as 6 agências têm envio vigente.

| Uso previsto | m7Coins |
|---|---|
| Calibração de pesos (1–3 placar × 6 agências) | 120–360 |
| Validação completa nas 2 maiores agências | 100 |
| Reserva para eventos e agências tardias | 300+ |

## 7. Frente C — dashboard e testes

### 7.1 Dashboard (`dashboard/app.py`)

Só lê `resultados/` e roda o motor (com cache) para a submissão escolhida; nunca chama a API. Atualização a cada 60 s.

**Página Agência:** cascata de pontos (nosso modelo × juiz; "estimado" antes de H4); potência em 15 min contra o limite, com ponta e horário fechado sombreados; plugados e fila contra saídas e vagas; histograma de SOC na retirada com marca em 80%; mapa de calor de clientes perdidos (dia × hora); tabela de fidelidade (meu / juiz / diferença e primeira janela divergente).

**Página Consolidado:** m7Coins gastos e saldo ao longo do dia; custo de obra por agência; evolução da nota (placar); curva nota × demanda com o ponto escolhido (justificativa de entrada e demanda); pesos estimados × reais após H4.

### 7.2 Testes

| Alvo | Teste |
|---|---|
| Motor, por etapa | `kit_kickoff/testes/test_etapaN.py` com os exemplos 6.3.1–6.3.7; suíte inteira a cada mudança (`python -m unittest discover -s testes`) |
| Fidelidade | `recarga/fidelidade.py`: 24 submissões em Bangkok = 3 `prioridade` × 2 `divisao` × 2 `evitar_ponta` × 2 limites (`b3_45` e `a4_150` com demanda folgada); todas com `OK: bate com o juiz` |
| `pesos.py` | recupera pesos conhecidos a partir de notas sintéticas |
| `otimizador.py` | todo candidato válido e Σ saídas ≤ vagas, num cenário pequeno |
| `juiz.py` | com cliente falso: cache não chama a rede; pago sem `confirmar` recusado; reserva respeitada; `429` espera `retry_em` |
| Dashboard | teste de fumaça com arquivos de exemplo em `resultados/` |

## 8. Riscos

| Risco | Tratamento |
|---|---|
| Motor lento em agências grandes | medir após a etapa 3; reduzir reinícios e paralelizar |
| Motor não fiel | resíduo alto bloqueia a inferência de pesos; otimizador usa ordem lexicográfica e mais testes pagos |
| Pesos diferentes por agência | calibração com 1–3 testes placar por agência (5.1) |
| Overfitting às semanas públicas | critério de melhor pior semana (5.3) |
| Agência sem envio final | 1º envio grátis em até 10 min da liberação; checagem em H7:00 |
| Falha da API | `ErroApi` com código; ledger só registra cobranças efetivas; monitor tenta de novo |

## 9. Linha do tempo

| Janela | A (motor) | B (otimizador) | C (dashboard) | D (operação) |
|---|---|---|---|---|
| H0–H1 | etapas 2–3 | `lote.py`, busca em grade simples | telas com dados de exemplo | `juiz.py`, `operacao.py`, `.env` |
| H1–H3 | etapas 4–6, `comparar.py` | desenho de experimentos e `pesos.py` | integração com `simular --series` | roda testes de Bangkok para A e B |
| H3–H4 | fidelidade completa | otimizador completo e robustez | cascata e fidelidade | primeiros envios finais |
| H4–H7 | etapa 7 quando houver evento | rodada com pesos exatos | consolidado | reenvios e eventos |
| H7–H7:30 | — | — | apresentação | checagem final dos envios |

## 10. Pendências

- URL da API: o Referer do kit (`gameday.mobi7.io`) não resolve no DNS; obter o endereço real no QR code / página `/docs`.
