# Hackathon Recarga Inteligente — Regulamento das equipes

**Versão para as equipes.** Entregue na abertura. Os pesos da pontuação e os custos de obra em pontos saem num anexo separado, publicado só na **revelação (H4)**.

---

## Sumário

1. Objetivo e princípios
2. Formato do dia
3. Equipes
4. Cenário e dados
5. Regras de operação simuladas pelo juiz
6. O que a equipe decide (a submissão)
7. Catálogos
8. Pontuação
9. Economia de m7Coins
10. Fases Neblina e Clara
11. Eventos ao vivo
12. API do juiz
13. Entregáveis, apresentação e premiação
14. Integridade

---

## 1. Objetivo e princípios

**O jogo:** cada equipe projeta e opera a recarga de uma rede de agências de aluguel de carros elétricos. Em cada agência, a equipe escolhe:

- os **carregadores**;
- a **entrada elétrica** (manter a existente ou ampliar);
- a **demanda contratada** (só em média tensão);
- a **política de recarga**, por um menu de parâmetros.

Um **juiz** (simulador oficial) reproduz o dia a dia da agência com essas escolhas e calcula a pontuação. A equipe consulta o juiz pela API (seção 12).

**Princípios:**

1. **Uma moeda só: pontos.** Clientes atendidos, upgrades, clientes perdidos, demanda contratada, energia na ponta e custo de obra entram na mesma nota da agência. Prioridade: atender o cliente → entregar a categoria certa → gastar pouca infraestrutura e potência. Um carregador a mais só vale se evitar perdas suficientes para pagar a própria obra.
2. **O juiz não confia em números declarados.** Toda nota vem de uma simulação feita pelo juiz.
3. **Generalização acima de ajuste fino.** A nota final é calculada em semanas que as equipes nunca veem.
4. **m7Coins só limitam a exploração.** Cada consulta ao juiz custa m7Coins. O que sobrar **não** vale pontos. Quem constrói um bom modelo próprio precisa de menos consultas.
5. **Informação incompleta na primeira metade.** Os pesos da pontuação e os custos de obra só são revelados em H4. Até lá, vocês sabem **o que** pontua, mas não **quanto**.

---

## 2. Formato do dia

**Duração total: 12 h** = 1 h de abertura + 8 h de jogo + 3 h de apresentações. **H0** é o início do jogo, logo após a abertura.

| Momento | O que acontece |
|---|---|
| H−1 a H0 | **Abertura:** regras, demonstração da API, **tutorial em Bangkok** (testes grátis, não pontua), entrega das PalavrasChave, **QR code no telão** para a página de instruções `/docs` (seção 12.1), teste de conexão de todas as equipes |
| H0 a H7:30 | **Jogo.** São **6 agências pontuadas**, liberadas aos poucos, em horários que a organização define. Os dados de cada agência só aparecem na API quando ela é liberada. Algumas agências abrem só na segunda metade do jogo |
| H4 | **Revelação:** publicação do anexo com os pesos da pontuação e os custos de obra. A partir daí os testes trazem a cascata de pontos |
| Durante o jogo | **Eventos operacionais** podem ser anunciados ao vivo (seção 11) |
| H7:30 | **Congelamento:** fim dos testes e dos envios finais |
| H7:30 a H8 | Preparação da apresentação. A API fica só em leitura |
| H8 a H11 | **Apresentações:** 12 min + 5 min de perguntas por equipe |
| H10:50 a H11 | Revelação do placar final ao vivo e premiação |

Não há relógio automático: cada etapa acontece quando a organização a ativa. Atrasos e pausas são possíveis; vale o que a organização anunciar e o que a API (`GET /status`) mostrar.

---

## 3. Equipes

- **Tamanho:** 4 a 6 pessoas. Recomendamos misturar cursos, com pelo menos uma pessoa de elétrica e uma de computação ou sistemas de informação.
- **Grupos predefinidos:** cada equipe já tem um nome `Grupo N`, com **número N fixo**. A equipe pode **trocar o próprio nome uma única vez**, pela API (`PUT /equipe/nome`, seção 12). Telão e placar mostram sempre `#número + nome`.
- **PalavraChave:** cada equipe recebe uma PalavraChave da API e um saldo inicial de **1.000 m7Coins** (seção 9).
- **Ferramentas livres:** qualquer linguagem. **IA generativa é permitida.**
- **Kit de kickoff (opcional).** Está na página `/docs` desde o início: leitores dos dados, helpers de potência, medição, nota e validação, cliente da API e um motor-esqueleto com o laço de eventos pronto. As regras de operação do motor e a fidelidade ao juiz continuam sendo trabalho da equipe. Usar o kit é opcional.
- **Proibido:**
  - compartilhar a PalavraChave;
  - consultar o juiz por outra equipe;
  - tentar extrair dados ocultos por qualquer meio que não seja a API (seção 14).

---

## 4. Cenário e dados

### 4.1 Natureza dos dados

Os dados são **fictícios**. As agências têm nomes de cidade apenas como identificadores. Os nomes não correspondem a cidades nem a agências reais. Volumes, frotas, vagas e horários são do cenário e podem ser citados como tal.

**Veículos e curvas de recarga:** os 8 modelos elétricos têm nome e especificações (bateria, autonomia, potências AC e DC) tirados de **dados públicos de mercado**. Eles **não representam** compras ou frota de nenhuma empresa. A curva de recarga de cada modelo é estimada a partir dessas especificações.

**Categorias:** Bronze < Prata < Ouro < Diamante.

**Contratos:** todo contrato é **ida e volta na mesma agência**. Por isso, as agências são **independentes** entre si.

**Devolução em km:** o carro volta com **km de autonomia restante**, não com SOC. O SOC de devolução é obtido pela autonomia do modelo que atendeu:

```
SOC = km ÷ autonomia_máxima_do_modelo × 100        (nunca acima do SOC com que o carro saiu)
```

**Disponibilidade:** com recarga ilimitada, **todos os contratos são atendíveis**. Todo cliente perdido vem da estratégia da equipe, não de falta de frota.

### 4.2 Período

Os horários de eventos e de contratos contam em minutos desde **00:00 de domingo, 17/10/2049**. O instante **T0** é **domingo, 17/10/2049, 18:00** (minuto 1080), início da simulação.

| Bloco | Uso |
|---|---|
| **Semanas públicas (1 a 4)**, 4 semanas a partir de T0 | Dados entregues. Os **testes** são avaliados aqui |
| **Semanas ocultas**, 4 semanas depois do período público | Nunca entregues. Os **envios finais** (e a nota final) são avaliados aqui |

O juiz simula sempre o horizonte completo, para manter a continuidade do estado da frota, e pontua só a janela pedida.

### 4.3 Kit de dados de cada agência

A cada agência liberada, a API passa a servir:

| Dado | Rota | Conteúdo |
|---|---|---|
| Dados da agência | `GET /agencias/{id}` | vagas elétricas, horário de funcionamento por dia, frota, entrada existente e **kW úteis** da entrada |
| Contratos públicos | `GET /agencias/{id}/contratos` | contratos das **semanas públicas**: id, categoria pedida, retirada, devolução, `autonomia_min_retirada_km`, `km_devolucao` |
| Frota em T0 | `GET /agencias/{id}/frota-t0` | estado de cada veículo em T0: modelo, categoria, situação, SOC, devolução prevista |
| Catálogo | `GET /catalogo` | veículos, curvas de recarga, categorias, carregadores e entradas elétricas. **Sem custo** até H4 (seção 7) |
| Kit em arquivos | `GET /agencias/{id}/kit` | `{id}.zip` com os mesmos dados em CSV/MD (agência, contratos públicos, frota T0, catálogo, curvas e um `LEIAME.md`). **Sem custos** |

O campo `kit_url` de `GET /agencias/{id}` aponta para a rota do kit. O jeito mais simples de baixar é a página **`/docs`** (seção 12.1): ela lista as agências liberadas, com um botão de download para cada uma, e avisa quando uma nova agência é liberada.

---

## 5. Regras de operação simuladas pelo juiz

Estas regras são o "contrato" do jogo. Foram escritas com precisão para que a equipe consiga **replicar o juiz** num modelo próprio. Exemplos numéricos de cada regra da política estão na seção 6.3.

### 5.1 Atendimento do cliente

- Na hora da retirada, o juiz procura no pátio um carro da **categoria pedida ou superior** com **SOC ≥ 80%**. Upgrade é permitido; **downgrade nunca**.
- **SOC alvo fixo em 80%:** todo carro carrega até 80% e só é entregue com 80% ou mais. Não é parâmetro da submissão.
- **Escolha do carro:** menor upgrade → menor SOC → não plugado → menor `id` do veículo, em ordem alfabética (o `id` de `/frota-t0`). A ordem por `id` é relevante porque muitos carros empatam em 80% ou 100%.
- O mesmo último desempate (menor `id`) vale em todas as ordenações da fila de recarga (seção 6.3.3).
- **Sem carro apto, o cliente é perdido.** Não existe espera nem reserva posterior.
- Com a agência **fechada**, ninguém retira carro, nem o que já está plugado. Todos os contratos têm retirada em horário de funcionamento.
- Carro retirado plugado é desplugado na hora.
- **No mesmo minuto, a ordem é:** devoluções → abertura da agência, início/fim da ponta e eventos → fim de recarga → retiradas → fechamento. Um carro devolvido apto pode sair no mesmo minuto.

### 5.2 Pátio, vagas e fila

- O carro devolvido entra na **fila de recarga** se o SOC estiver abaixo de 80%.
- O número de carros plugados nunca passa do total de **saídas** instaladas, e o total de saídas nunca passa das **vagas elétricas** da agência.
- **Plugar e desplugar só acontece com a agência aberta.** A recarga continua com a agência fechada.
- Ao atingir 80%, o carro é desplugado se a agência estiver aberta. Se estiver fechada, ele **segura a saída** até a abertura.
- A ordem da fila é definida pela política (`prioridade`).

### 5.3 Potência

- **Carro:** a potência é limitada pela curva do modelo no degrau de SOC atual (AC ou DC, conforme o carregador). As curvas são em **degraus de 5% de SOC**. Num degrau, a potência do carro é a **média das duas linhas** da tabela de curva. `GET /catalogo` já traz isso pronto: para cada modelo, `curvas[modelo].ac` e `.dc` têm **20 valores em kW**; o valor usado é o do índice `min(19, floor(SOC ÷ 5))`.
- **Carregador de 2 saídas:** a potência nominal é dividida entre os carros conectados. A sobra de um carro que não consegue absorver a sua parte vai para o outro.
- **Limite da agência:** a soma das potências nunca passa do limite:
  - em **B3** (baixa tensão), a potência útil da entrada;
  - em **A4 ou subestação (SE)**, a **demanda contratada**.
- **Divisão do limite:** igual entre os carros ou em ordem de prioridade (`divisao`, seção 6.3.5).
- **Ponta:** de **segunda a sexta, das 18:00 às 21:00**. Sábado e domingo não têm ponta. Com `evitar_ponta`, nenhum carro carrega nesse intervalo (os carros continuam plugados).
- **Medição:** energia e pico são medidos em **janelas de 15 minutos**.

### 5.4 O que o juiz não modela

- Perdas de conversão AC/DC e eficiência do carregador no passo a passo da simulação (considerados 100%; a eficiência agregada de 90% já entra no kW útil da entrada — seção 5.5).
- Fator de potência (considerado 1).
- Manobra de veículos entre vagas: o carro não troca de carregador no meio da recarga.
- Detalhes de instalação além do fator 0,9 do kW útil (ex.: transformador elevador).
- Degradação de bateria.

### 5.5 Entrada elétrica

kW útil = kVA × FP (1,0) × 0,9. É a potência contínua de projeto, servida no catálogo (`kw_util`). O fator **0,9 (= 90%)** é a eficiência agregada dos equipamentos da instalação (cabos, transformadores, carregadores etc.).

---

## 6. O que a equipe decide (a submissão)

Uma submissão por agência, em JSON.

```json
{
  "agencia": "Bangkok",
  "carregadores": {"dc_60x2": 1, "ac_7": 2},
  "entrada": "a4_150",
  "demanda_contratada_kw": 60,
  "politica": {
    "prioridade": "proxima_retirada",
    "evitar_ponta": false,
    "divisao": "prioridade"
  }
}
```

Exemplo mínimo (agência mantém a entrada existente, política padrão):

```json
{"carregadores": {"ac_7": 3, "dc_30": 1}, "entrada": "b3_45"}
```

O campo `agencia` do corpo é opcional. Se vier, deve ser igual ao da rota.

### 6.1 Menu de política

| Parâmetro | Opções | Padrão | Significado |
|---|---|---|---|
| `prioridade` | `menor_soc`, `chegada`, `proxima_retirada` | `menor_soc` | ordem da fila: menor autonomia restante primeiro / ordem de chegada / quem tem a próxima reserva compatível mais cedo |
| `divisao` | `igual`, `prioridade` | `igual` | como o limite da agência e a potência do carregador são repartidos: partes iguais ou em sequência pela ordem de prioridade |
| `evitar_ponta` | `true`, `false` | `false` | não carregar de segunda a sexta, das 18h às 21h |

O SOC alvo **não** é escolha: é fixo em 80% (seção 5.1).

### 6.2 Validação

**Submissão inválida não é simulada, não custa m7Coins, e a API devolve `422 invalido` com a lista `erros`.** Regras:

- Agência e modelos de carregador existentes; quantidades inteiras ≥ 0; **pelo menos 1 carregador**.
- **Σ saídas ≤ vagas elétricas** da agência (carregador de 2 saídas conta como 2).
- **Entrada:**
  - pode manter a existente ou subir de nível, **nunca descer**;
  - o `b3_45` só vale como entrada existente (não dá para "comprar" `b3_45`);
  - quem tem `b3_45` pode ampliar para `b3_75`, que continua B3 (sem demanda contratada; limite = kW útil).
- **Demanda contratada:**
  - **só existe com entrada acima de 75 kVA** (A4 ou subestação); em B3, o campo é **rejeitado**;
  - em A4/SE, vale em **passos de 10 kW, sem casas decimais**, de **30 kW** até o kW útil da entrada arredondado para baixo ao múltiplo de 10 (coluna "Demanda contratada máx." da seção 7.2; nunca acima de 2000 kW);
  - o juiz **arredonda** o valor recebido para o múltiplo de 10 mais próximo (o 5 sobe: 75 → 80; 87,3 → 90) e só depois confere a faixa. Fora da faixa após o arredondamento, a submissão é rejeitada;
  - **independe da entrada escolhida**: a equipe pode contratar bem menos que a entrada permite;
  - se omitida, vale a demanda máxima da entrada (ex.: 130 kW no `a4_150`);
  - pesa na nota por kW contratado (seção 8).
- **Política:** só valores do menu. Chaves desconhecidas são rejeitadas.
- O corpo só pode ter as chaves `agencia`, `carregadores`, `entrada`, `demanda_contratada_kw` e `politica`.

### 6.3 Exemplos do menu

Números tirados do catálogo e das curvas do dataset. Lembrete: num degrau de 5% de SOC, a potência do carro é a média das duas linhas da curva.

#### 6.3.1 Qual carro sai na retirada

Contrato **Prata** às 10:00. No pátio:

| Carro | Categoria | SOC | Plugado? | Apto? |
|---|---|---:|---|---|
| Geely EX2 Pro | Prata | 82% | não | sim |
| BYD Dolphin Mini GS | Prata | 95% | sim | sim |
| MG4 Urban Comfort | Ouro | 100% | não | sim (upgrade) |
| JAC E-JS1 | Bronze | 100% | não | não (downgrade) |

- Sai o **Geely**: sem upgrade e com o menor SOC entre os aptos. O juiz guarda os carros mais cheios para depois.
- Se o Geely estivesse a 78%, sairia o **Dolphin Mini** (desplugado na hora).
- Se nenhum Prata estivesse apto, sairia o **MG4**: o cliente é atendido, mas com upgrade.

#### 6.3.2 Recarga até 80% (regra fixa, fora do menu)

O carro só entra na fila se voltar abaixo de 80%, e carrega até 80%. Na retirada, o juiz exige SOC ≥ 80%.

**Exemplo:** BYD Dolphin GS (Ouro, 44,9 kWh), devolvido a 20%, sozinho num DC-60, sem limite da agência. Cada degrau de 5% = 2,245 kWh.

| Trecho | Potência da curva no degrau | Tempo |
|---|---|---:|
| 20% → 80% | de 58,4 kW caindo até 27,2 kW | 36,7 min |

- O carro ocupa a saída por 36,7 min e fica apto para qualquer contrato Ouro (ou inferior, como upgrade).
- Devolvido a 82%, ele nem entra na fila: já está apto.
- Acima de 80% a curva cai muito. Ir de 80% a 100% levaria mais 48,9 min, mais do que os 60% anteriores.

#### 6.3.3 `prioridade`: quem pluga primeiro

A fila é ordenada toda vez que o juiz tenta plugar: quando um carro volta, quando um carro termina a recarga, quando a agência abre e quando um carregador volta de uma indisponibilidade. **Só com a agência aberta.** O juiz pluga na ordem enquanto houver saída livre.

- **`menor_soc`:** menor autonomia restante em km primeiro (`autonomia_km × SOC`). Conta **km, não SOC**. Empate: menor `id`.
- **`chegada`:** ordem de entrada na fila (FIFO). Empate: menor `id`. Os carros que já estão na fila em T0 entram todos no mesmo instante, então valem pelo `id`.
- **`proxima_retirada`:** primeiro o carro cuja próxima reserva compatível é mais cedo. **Próxima reserva compatível** = o primeiro contrato ainda não retirado, em ordem de horário, cuja categoria é ≤ a categoria do carro. Como depende só da categoria, todos os carros da mesma categoria têm a mesma reserva, e carros de categoria alta tendem a ter a reserva mais cedo (servem a todos). Carros sem reserva compatível vão para o fim. Empate: maior SOC primeiro; depois, menor `id`.

O último desempate, em todas as ordenações (retirada e fila), é o menor `id` do veículo, em ordem alfabética (o `id` de `/frota-t0`). Na retirada a ordem completa é menor upgrade → menor SOC → não plugado → menor `id`. Essa ordem por `id` importa porque muitos carros empatam em 80% ou 100%.

**Exemplo:** às 11:00 uma saída libera. Próximos contratos ainda não retirados: 12:30 Ouro, 13:15 Prata, 14:00 Bronze.

| Carro | Categoria | SOC | Autonomia restante | Entrou na fila | Próxima reserva compatível |
|---|---|---:|---:|---|---|
| A — Renault Kwid E-Tech | Bronze | 30% | 185 × 0,30 = 55,5 km | 10:00 | 14:00 (só o Bronze serve) |
| B — BYD Dolphin Mini GS | Prata | 20% | 280 × 0,20 = 56,0 km | 10:20 | 13:15 (o Ouro das 12:30 não serve) |
| C — MG4 Urban Comfort | Ouro | 55% | 299 × 0,55 = 164,5 km | 10:40 | 12:30 |
| D — Leapmotor B10 BEV | Diamante | 40% | 288 × 0,40 = 115,2 km | 10:55 | 12:30 |

| Opção | Ordem | Por quê |
|---|---|---|
| `menor_soc` | A, B, D, C | A tem SOC maior que B, mas menos km |
| `chegada` | A, B, C, D | ordem de entrada |
| `proxima_retirada` | C, D, B, A | C e D empatam em 12:30 e C tem SOC maior; depois B (13:15) e A (14:00) |

#### 6.3.4 Em qual carregador o carro pluga

Entre os carregadores **em operação** com saída livre, o juiz escolhe o que daria **mais potência** ao carro. Ele estima dividindo a potência do carregador igualmente entre o carro e quem já está ali (pela curva de cada um), **sem olhar o limite da agência nem a opção `divisao`**. Empate: o primeiro da lista, em ordem alfabética do id (`ac_11`, `ac_22x2`, `ac_7`, `dc_120x2`, `dc_30`, `dc_60x2`). Depois de plugado, o carro **não troca** de carregador.

**Exemplo:** 1× DC-60 com um Geely EX2 Pro a 30% numa saída (curva DC 71,5 kW) e 1× AC-22 vazio. Chega um BYD Dolphin GS a 20% (curva DC 58,4 kW; AC 7 kW).

- No DC-60 ele receberia 60 ÷ 2 = 30 kW. No AC-22, 7 kW (limite AC do carro).
- Vai para o **DC-60**. O próximo carro, com o DC-60 cheio, vai para o AC-22.

#### 6.3.5 `divisao`: como a potência é repartida

A divisão acontece em duas camadas, recalculadas a cada mudança (carro pluga ou despluga, troca de degrau, início ou fim da ponta, evento):

1. **Dentro do carregador de 2 saídas:** a potência nominal é dividida entre os carros que ainda estão carregando.
2. **No limite da agência** (entrada útil em B3 ou demanda contratada em A4/SE): o que cada carro recebeu na camada 1 é o máximo que ele pode levar.

- **`igual`:** partes iguais. Quem não consegue absorver a sua parte (pela curva) fica com o que absorve, e a sobra é redistribuída entre os outros ("enchimento de água").
- **`prioridade`:** em sequência, na ordem da `prioridade`. Cada carro leva o mínimo entre o que pode absorver e o que sobrou. Os últimos podem ficar com 0.

**Exemplo:** limite da agência 40,5 kW, 2× DC-60, 4 carros plugados, `prioridade` = `menor_soc`.

| Carregador | Carro | SOC | Curva DC no degrau | Km restantes |
|---|---|---:|---:|---:|
| 1 | Geely EX2 Pro (Prata) | 30% | 71,5 kW | 86,7 |
| 1 | BYD Dolphin GS (Ouro) | 50% | 47,75 kW | 145,5 |
| 2 | Renault Kwid E-Tech (Bronze) | 40% | 26,6 kW | 74,0 |
| 2 | JAC E-JS1 (Bronze) | 75% | 16,45 kW | 135,8 |

Ordem `menor_soc`: Kwid (74,0), Geely (86,7), JAC (135,8), Dolphin GS (145,5).

| Carro | Camada 1 `igual` | Final `igual` | Camada 1 `prioridade` | Final `prioridade` |
|---|---:|---:|---:|---:|
| Geely EX2 Pro | 30 | 10,125 | 60 | 13,9 |
| BYD Dolphin GS | 30 | 10,125 | 0 | 0 |
| Renault Kwid | 26,6 | 10,125 | 26,6 | 26,6 |
| JAC E-JS1 | 16,45 | 10,125 | 16,45 | 0 |
| **Total** | 103,05 | **40,5** | 103,05 | **40,5** |

- **`igual`:** a parte de cada um seria 40,5 ÷ 4 = 10,125 kW. Os quatro absorvem mais que isso, então cada um fica com 10,125 kW. Todos andam devagar.
- **`prioridade`:** o Kwid leva tudo o que pode (26,6), o Geely leva o resto (13,9), JAC e Dolphin GS ficam parados. No carregador 1, o Geely já tinha pego os 60 kW na camada 1, então o Dolphin GS fica com 0 mesmo havendo folga no limite depois. Concentrar potência faz o primeiro da fila ficar pronto antes.
- Com limite de **80 kW** no lugar dos 40,5, a parte igual seria 80 ÷ 4 = 20 kW. O JAC só absorve 16,45, e a sobra (3,55) vai para os outros três, 21,18 kW cada ("enchimento de água"). Em `prioridade`: Kwid 26,6, Geely 53,4, JAC 0, Dolphin GS 0.

#### 6.3.6 `evitar_ponta`

De segunda a sexta, das 18:00 às 21:00, **todos os carros ficam a 0 kW**. Eles continuam plugados, e plugar continua permitido: o carro pluga, mas só carrega a partir das 21:00. Sábado e domingo não têm ponta.

**Exemplo:** MG4 Urban Comfort (43 kWh) pluga numa segunda às 17:00 num AC-22, a 11 kW, de 29% a 80%: 22 kWh, ou 2 h de carga.

| | Sem `evitar_ponta` | Com `evitar_ponta` |
|---|---|---|
| Carga | 17:00–19:00 | 17:00–18:00, parado 18:00–21:00, 21:00–22:00 |
| Termina | 19:00 | 22:00 (3 h a mais segurando a saída) |
| Energia na ponta | 11 kWh (de 18:00 a 19:00) | 0 |

Numa agência que fecha às 20:00, uma retirada às 19:30 encontraria o carro pronto sem `evitar_ponta`. Com `evitar_ponta`, ele estaria perto de 55% e não sairia. Nessa agência o carro termina às 22:00 com a agência fechada e segura a saída até a abertura do dia seguinte. Evitar a ponta reduz a energia na ponta, mas pode custar um cliente.

#### 6.3.7 `demanda_contratada_kw` (só A4/SE)

**Exemplo:** entrada `a4_150` (135 kW úteis) com `demanda_contratada_kw` = 80.

- O limite da agência passa a ser **80 kW**, como **teto rígido**: o juiz nunca deixa passar e reparte os 80 kW pela `divisao` (exemplo em 6.3.5). Não há multa por ultrapassagem, porque ela nunca acontece.
- Omitir o campo vale a demanda máxima da entrada (130 kW), e a demanda contratada de 130 kW pesa na nota.
- Enviar 84 vira 80; enviar 85 vira 90; enviar 135 vira 140 e é rejeitado (acima de 130).
- Em B3, o campo é rejeitado e não há parcela de demanda contratada na nota. O mínimo em A4/SE é 30 kW.

---

## 7. Catálogos

`GET /catalogo` devolve tudo o que está abaixo. **Até H4, o catálogo não traz custo.** Os custos de obra em pontos saem no **Anexo H4** e passam a aparecer no campo `custo` depois da revelação.

Carregadores e ampliação de entrada custam **pontos de obra**, descontados **só na nota da agência** onde foram instalados. Não custam m7Coins.

### 7.1 Carregadores

| Id | Modelo | Tipo | kW | Saídas |
|---|---|---|---:|---:|
| `ac_7` | AC-7 | AC | 7 | 1 |
| `ac_11` | AC-11 | AC | 11 | 1 |
| `ac_22x2` | AC-22 (2 saídas) | AC | 22 | 2 |
| `dc_30` | DC-30 | DC | 30 | 1 |
| `dc_60x2` | DC-60 (2 saídas) | DC | 60 | 2 |
| `dc_120x2` | DC-120 (2 saídas) | DC | 120 | 2 |

### 7.2 Entrada elétrica

kW útil = kVA × FP (1,0) × 0,9 (eficiência agregada de 90% — cabos, transformadores, carregadores etc.; ver seção 5.5).

| Id | Nível | kVA | kW útil | Demanda contratada máx. (kW) |
|---|---|---:|---:|---:|
| `b3_45` | B3 45 kVA | 45 | 40,5 | — |
| `b3_75` | B3 75 kVA | 75 | 67,5 | — |
| `a4_150` | A4 em poste 150 kVA | 150 | 135 | 130 |
| `a4_225` | A4 em poste 225 kVA | 225 | 202,5 | 200 |
| `a4_300` | A4 em poste 300 kVA | 300 | 270 | 270 |
| `se_500` | Subestação 500 kVA | 500 | 450 | 450 |
| `se_750` | Subestação 750 kVA | 750 | 675 | 670 |
| `se_1000` | Subestação 1 MVA | 1000 | 900 | 900 |
| `se_1500` | Subestação 1,5 MVA | 1500 | 1350 | 1350 |
| `se_2000` | Subestação 2 MVA | 2000 | 1800 | 1800 |

- **Regra de cobrança da entrada:** ampliar custa o **valor cheio** do novo nível, sem crédito pela entrada existente. Manter a existente custa 0. O `b3_45` só vale como entrada existente; ampliar de `b3_45` para `b3_75` é permitido e segue a mesma regra.
- Cada agência já tem uma **entrada existente** (campo `entrada_existente` de `GET /agencias/{id}`).

### 7.3 Veículos

| Modelo | Categoria | Bateria (kWh) | Autonomia (km) | AC máx (kW) | DC máx (kW) |
|---|---|---:|---:|---:|---:|
| Renault Kwid E-Tech | Bronze | 26,8 | 185 | 7,4 | 30 |
| JAC E-JS1 | Bronze | 31,4 | 181 | 6,6 | 20 |
| Geely EX2 Pro | Prata | 39,0 | 289 | 6,6 | 80 |
| BYD Dolphin Mini GS | Prata | 38,9 | 280 | 6,6 | 40 |
| MG4 Urban Comfort | Ouro | 43,0 | 299 | 11,0 | 80 |
| BYD Dolphin GS | Ouro | 44,9 | 291 | 7,0 | 60 |
| BYD Dolphin Plus | Diamante | 60,5 | 427 | 11,0 | 80 |
| Leapmotor B10 BEV | Diamante | 56,2 | 288 | 11,0 | 140 |

**O juiz usa a curva, não a ficha.** O pico DC da curva pode ficar um pouco abaixo da ficha (ex.: Geely EX2 Pro, 80 kW na ficha e 73 kW na curva). Lembrete: veículos e curvas são dados públicos de mercado, sem relação com nenhuma frota real.

---

## 8. Pontuação

### 8.1 Nota da agência

A nota é calculada pelo juiz na janela avaliada (semanas públicas no teste, semanas ocultas no envio final), somando os itens abaixo. Na Neblina, **os pesos são ocultos**; em H4 saem no anexo.

A organização pode ajustar os pesos de uma agência durante o dia. O ajuste vale na hora para testes e placar, inclusive para envios finais já feitos (sem nova simulação). Os valores vigentes ficam em `GET /catalogo` (`pesos`) a partir de H4.

| Item | Efeito na nota | Medida |
|---|---|---|
| Cliente atendido na categoria certa | **soma** | por contrato |
| Cliente atendido com upgrade | **soma** (menos que o certo) | por contrato |
| Cliente não atendido | **desconta** | por contrato |
| Demanda contratada | **desconta** | por kW contratado; **só em A4/SE** (B3 não paga) |
| Energia carregada na ponta | **desconta** | por kWh carregado (seg–sex, 18–21h) |
| Custo de obra | **desconta** | por ponto de custo de obra: carregadores instalados + ampliação de entrada |

```
nota = (peso × certos) + (peso × upgrades) − (peso × não atendidos)
       − (peso × demanda contratada em kW) − (peso × kWh na ponta) − (peso × custo de obra)
```

O custo de obra e a demanda entram **inteiros** em cada janela avaliada.

O juiz também informa, **sem pontuar**: pico de 15 min (kW), energia total (kWh), % de atendimento e número de contratos.

### 8.2 Nota final da equipe

```
nota final = soma das notas das agências pontuadas (envio final, semanas ocultas)
```

- Só contam as **6 agências pontuadas**. Bangkok (tutorial) não pontua.
- **Agências maiores pesam mais**, pelo volume de contratos. Faz parte do jogo.
- **Agência sem envio final:** 0 pontos. Isso costuma ser pior que uma submissão razoável.
- **Desempate:**
  1. menor número de clientes não atendidos nas semanas ocultas;
  2. menor custo de obra total;
  3. horário do último envio final (mais cedo vence).

---

## 9. Economia de m7Coins

m7Coins existem **só para usar o juiz** (testes e reenvios finais). O saldo que sobra **não** entra na nota. **Os preços e cooldowns abaixo são públicos desde o início.**

### 9.1 Saldo e custos

| Ação | m7Coins | Cooldown |
|---|---:|---|
| Saldo inicial por equipe | **1.000** | — |
| Teste "placar" (semanas públicas) | 20 | 5 min por agência |
| Teste "completo" (placar + séries de 15 min) | 50 (30 se o mesmo teste já foi pago como placar) | 5 min por agência. Ampliar um placar já pago para completo não exige cooldown livre e **não reinicia** o cooldown |
| Teste idêntico a um já feito pela equipe | 0 (resultado guardado) | não consome cooldown |
| 1º envio final por agência | 0 | — |
| Reenvio final (2º, 3º, 4º…) | 80, 160, 320… (dobra a cada vez) | 15 min por agência |
| Reenvio idêntico ao final vigente | **recusado** | — |
| Testes em Bangkok (tutorial, até o congelamento) | 0 | 1 min (teste idêntico não consome) |

Há dois cooldowns independentes, por equipe e por agência: o de **testes** (5 min desde o último teste pago; 1 min em Bangkok) e o de **reenvio final** (15 min desde o último envio final). Um não afeta o outro.

Um teste é **idêntico** quando a submissão normalizada é a mesma e os eventos ativos na agência são os mesmos. Na normalização: política omitida vale o padrão; demanda omitida vale a demanda máxima da entrada e demanda enviada vale o valor arredondado (seção 6.2); quantidade 0 vale carregador ausente; a ordem das chaves não importa. Depois de um evento na agência, o mesmo teste volta a ser cobrado e a consumir cooldown (seção 11).

### 9.2 Regras do saldo

- **Saldo = inicial − taxas do juiz.** O custo de obra **não** passa pelo saldo: ele sai da nota da agência.
- O saldo nunca fica negativo: uma ação paga sem saldo suficiente é recusada (`402 saldo_insuficiente`). O 1º envio final de cada agência continua possível, porque é grátis.
- **Testes não cobram obra no saldo.** Testar uma subestação grande custa só a taxa do teste.
- Um teste inválido (`422`) não cobra nada.

### 9.3 Como pensar o orçamento

- 1.000 m7Coins equivalem a cerca de 50 testes "placar" ou 20 "completos".
- O cooldown permitiria muito mais que isso. Quem limita é o orçamento: escolham onde testar e **guardem saldo para as agências que abrem tarde**.
- Quem constrói um bom modelo próprio precisa de menos testes.

---

## 10. Fases Neblina e Clara

| | **Neblina (H0 até H4)** | **Clara (de H4 até o congelamento)** |
|---|---|---|
| Pesos da pontuação | ocultos (a equipe sabe **o que** pontua) | publicados no anexo e em `GET /catalogo` (`pesos`) |
| Custos de obra | ocultos (a equipe sabe **o que** custa) | publicados no anexo e em `GET /catalogo` (`custo`) |
| Preços do juiz (m7Coins) | conhecidos | conhecidos |
| Retorno do teste | **nota** (calculada com os pesos e custos ocultos) + métricas físicas, sem cascata | nota + todas as métricas + **cascata de pontos** + `custo_infra` |
| Placar | notas das semanas ocultas | notas das semanas ocultas |

- **Dilema da Neblina:** explorar (gastar m7Coins testando para inferir os pesos e os custos, por exemplo comparando notas de variações de carregadores, entrada e política) ou economizar e confiar na engenharia.
- **Virada em H4:** a nota sempre descontou a obra. O que muda é que vocês descobrem quanto ela pesou.
- **Não há reenvio barato depois da revelação.** Reenviar segue o custo que dobra (seção 9).
- A organização pode ajustar os pesos de uma agência durante o dia. O ajuste vale na hora para testes e placar, inclusive para envios finais já feitos (sem nova simulação). Os valores vigentes ficam em `GET /catalogo` (`pesos`) a partir de H4.
- Fases em `GET /status` (campo `fase`): `pre` (antes de H0), `neblina`, `clara`, `congelado` (depois do congelamento; prevalece sobre as outras).

---

## 11. Eventos ao vivo

**Eventos operacionais** podem ser anunciados ao vivo durante o jogo. Por exemplo: uma limitação da concessionária de energia, ou um carregador fora de operação.

- O evento é anunciado a **todas as equipes** ao mesmo tempo e **vale para todas**.
- A partir do anúncio, o juiz aplica o evento **nos testes e nos envios finais**, na agência afetada.
- Para que dê para testar a reação, o evento aparece também nas semanas públicas.
- Os envios finais já feitos são **reavaliados automaticamente**, e o placar pode mudar.
- **Reagir** a um evento segue o custo normal de reenvio (seção 9). Não há reenvio grátis.
- Os eventos já lançados aparecem em `GET /status`: `cartas` (número, título e agência) e `eventos_ativos` (agência e parâmetros, em minutos desde 00:00 de 17/10/2049). Nas semanas ocultas ocorre um evento equivalente, em horário que vocês não veem. `eventos_ativos` mostra só a ocorrência das semanas públicas. O significado de cada evento e o formato de `params` são explicados no anúncio.
- Depois de um evento na agência, o mesmo teste deixa de ser idêntico: volta a ser cobrado e a consumir cooldown (seção 9.1). Teste idêntico é a mesma submissão normalizada (política omitida = padrão; demanda omitida = demanda máxima da entrada, enviada = arredondada; quantidade 0 = carregador ausente; ordem das chaves irrelevante) e os mesmos eventos ativos na agência.

---

## 12. API do juiz

### 12.1 Convenções

- **Autenticação:** cabeçalho `Authorization: Bearer <PalavraChave>` em todas as chamadas. Sem a PalavraChave a chamada é recusada com `401 nao_autenticado`.
- **Erros:** todas as respostas de erro têm o formato JSON `{"codigo", "mensagem"}`, com extras quando a seção 12.6 indica.
- **Datas:** ISO 8601 em UTC.
- **Corpo:** JSON de até **10 KB** (acima disso, `413 corpo_grande`).
- **Rate limit:** **20 requisições por minuto** por equipe (`429 rate_limit`), somando todas as rotas e todos os membros (inclusive a página `/docs` aberta). Conta as requisições dos últimos 60 s; respostas `429` não entram na conta. Há também um limite por IP contra abuso.
- **Minutos de evento:** contados desde 00:00 de 17/10/2049. T0 é o minuto 1080.
- **Agência não liberada:** toda rota de equipe responde exatamente o mesmo `404 agencia_indisponivel` para agência **não liberada** e para agência **inexistente**. `GET /status` e `GET /placar` só citam as agências já liberadas.
- **Página de instruções (`/docs`):** ponto de partida do dia. Na abertura, o telão mostra um QR code com o endereço dela. Abra no navegador (celular ou notebook) e informe a PalavraChave da equipe. A página traz este regulamento (para ler ou baixar em `.md`), os kits das agências liberadas, o kit de kickoff do simulador e, depois de H4, o Anexo H4. Ela se atualiza sozinha a cada minuto. A página em si é pública, mas todo o conteúdo exige a PalavraChave.

### 12.2 Exemplos

```bash
curl -s https://URL_DA_API/status -H "Authorization: Bearer $TOKEN"

curl -s -X POST "https://URL_DA_API/teste/Bangkok?detalhe=placar" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"carregadores": {"ac_7": 3, "dc_30": 1}, "entrada": "b3_45"}'
```

```python
import requests

URL, TOKEN = "https://URL_DA_API", "sua-palavrachave"
H = {"Authorization": f"Bearer {TOKEN}"}

sub = {
    "carregadores": {"dc_60x2": 1, "ac_7": 2},
    "entrada": "a4_150",
    "demanda_contratada_kw": 60,
    "politica": {"prioridade": "proxima_retirada", "evitar_ponta": False, "divisao": "prioridade"},
}
r = requests.post(f"{URL}/teste/Bangkok", params={"detalhe": "placar"}, json=sub, headers=H)
print(r.status_code, r.json())   # em erro: {"codigo": ..., "mensagem": ...}
```

### 12.3 Rotas das equipes

| Método | Rota | Corpo | Retorno |
|---|---|---|---|
| GET | `/status` | — | `equipe` {numero, nome, pode_renomear}, `fase`, `etapa` {n, rotulo}, `agora`, `h0`, `saldo`, `agencias` (só liberadas: `aberta`, `cooldown_teste_ate`, `cooldown_final_ate`, `envios`, `vigente`), `cartas` lançadas {n, titulo, agencia}, `eventos_ativos` {agencia, params} |
| GET | `/equipe` | — | {numero, nome, pode_renomear} |
| PUT | `/equipe/nome` | `{"nome": "..."}` | o mesmo de `/equipe`. **Uma única troca** por equipe. Nome com 3 a 30 caracteres (letras, números, espaço, `-`, `_`); único, sem diferenciar maiúsculas |
| GET | `/agencias/{id}` | — | `vagas`, `horario` por dia, `entrada_existente`, `entrada_kw`, `frota`, `aberta`, `kit_url` (caminho da rota do kit) |
| GET | `/agencias/{id}/kit` | — | arquivo `{id}.zip` (`application/zip`) com o kit da agência (seção 4.3) |
| GET | `/kit-kickoff` | — | arquivo `kit_kickoff.zip` (`application/zip`): kit de kickoff do simulador; liberado para todas as equipes |
| GET | `/instrucoes` | — | `regulamento` (este documento em Markdown) e `anexo_h4` (Markdown a partir de H4; `null` antes) |
| GET | `/agencias/{id}/contratos` | — | `agencia`, `contratos` das semanas públicas: `id`, `categoria`, `retirada`, `devolucao`, `autonomia_min_retirada_km`, `km_devolucao` |
| GET | `/agencias/{id}/frota-t0` | — | `agencia`, `veiculos`: `id`, `modelo`, `categoria`, `situacao` (`estoque_pronto` se SOC ≥ 80%, `estoque_a_carregar`, `em_contrato`), `soc_pct`, `devolucao_prevista`, `soc_devolucao_pct` |
| GET | `/catalogo` | — | `veiculos` (modelo, categoria, bateria_kwh, autonomia_km, ac_max_kw, dc_max_kw), `categorias` (grupo, rank), `curvas` (por modelo: `ac` e `dc`, 20 valores em kW), `carregadores` (id, modelo, tipo, potencia_kw, saidas), `entradas` (id, descricao, kva, kw_util). **A partir de H4:** `custo` (pontos) em carregadores e entradas, e `pesos` efetivos de cada agência liberada |
| POST | `/teste/{id}?detalhe=placar\|completo` | submissão (seção 6) | ver "Retorno do teste" |
| POST | `/final/{id}` | submissão (seção 6) | `agencia`, `n` (nº do envio), `taxa`, `saldo`, `aceito`, `custo_infra` (`"pendente"` antes de H4) |
| GET | `/placar` | — | ver seção 12.4 |

Sobre as rotas de teste e final:

- O campo `agencia` do corpo é opcional. Se vier e for diferente da rota: `422 agencia_divergente`.
- Submissão inválida: `422 invalido`, com `erros`; **não cobra m7Coins**.
- **Ordem das checagens** em teste e final: autenticação (`401`) → rate limit (`429 rate_limit`) → corpo (`413 corpo_grande`, `422 json_invalido`) → agência liberada (`404 agencia_indisponivel`) → `agencia` do corpo (`422 agencia_divergente`) → no teste, `detalhe` (`422 detalhe_invalido`); no final, Bangkok (`403 nao_pontua`) → jogo não congelado (`403 jogo_congelado`) → submissão válida (`422 invalido`) → no final, idêntico ao vigente (`409 identico`) → cooldown (`429 cooldown`) → saldo (`402 saldo_insuficiente`) → no final, simulação sem violação (`422 violacao`).
- `detalhe` aceita só `placar` (padrão) ou `completo`; outro valor dá `422 detalhe_invalido`.

**Retorno do teste:**

| Campo | Significado |
|---|---|
| `agencia`, `periodo` | agência e janela avaliada (`"publico"`) |
| `valido`, `erros`, `violacoes` | validade da simulação e violações apontadas pelo juiz |
| `nota` | nota da janela pública (0 se houver violação; `pontos.nota` também fica 0) |
| `metricas` | métricas físicas (varia por fase, abaixo) |
| `taxa`, `saldo` | m7Coins cobrados neste teste e saldo restante |
| `repetido` | `true` se a própria equipe já pagou esse mesmo teste |
| `series` | só em `detalhe=completo` |
| `pontos`, `custo_infra` | só na Clara |

| Fase | `detalhe=placar` | `detalhe=completo` |
|---|---|---|
| Neblina | `nota`, `metricas` físicas (`contratos`, `atendimento_pct`, `pico_kw`, `energia_kwh`), validação | + `series` |
| Clara | + todas as métricas (`certos`, `upgrades`, `nao_atendidos`, `energia_ponta_kwh`, `demanda_contratada_kw`, `custo_infra`), `pontos` e `custo_infra` | o mesmo, com `series` |

`pontos` tem o formato `{"itens": [[item, quantidade, peso, pontos], ...], "nota": x}`. `item` é um de `certo`, `upgrade`, `nao_atendido`, `demanda_contratada`, `energia_ponta_kwh`, `infraestrutura`. Com violação, `nota` do teste e `pontos.nota` valem 0.

`series`: `inicio_min`, `passo_min` (15), `potencia_kw`, `plugados_max`, `fila_max` (uma posição por janela de 15 min, a partir de `inicio_min`), `nao_atendidos_min` e `soc_retirada` (uma posição por evento, tamanhos diferentes; `nao_atendidos_min` em minutos desde `inicio_min`).

**Envio final:**

- O juiz simula o envio final antes de aceitar. Se a simulação apontar violação, o envio é recusado com `422 violacao` (extra `violacoes`), **sem cobrar e sem registrar**. Violação é uma inconsistência apontada pela simulação do juiz (não deve ocorrer com submissão válida; se ocorrer, avisem a organização).
- Aceito, devolve a taxa de m7Coins cobrada e a confirmação. O custo de obra em pontos só aparece a partir de H4.
- A nota das semanas ocultas aparece **apenas no placar**; a resposta do envio não traz detalhes das ocultas.
- O envio final vigente de cada agência é o **último aceito**.

### 12.4 Placar (`GET /placar`) e telão

- Campos: `fase`, `etapa`, `h0`, `atualizado_em`, `recalculando`, `agencias` (pontuadas e já liberadas), `a_liberar` (só a **contagem**), `cartas` e `equipes`. Cada equipe traz `posicao`, `numero`, `nome`, `nota`, `agencias` (nota oculta por agência, ou `null` sem envio), `finais`, `saldo`, `nao_atendidos` e `custo_infra`.
- `recalculando` é `true` quando alguma nota ainda está sendo recalculada depois de um evento. A nota mostrada é a anterior até terminar.
- `finais` é o número de agências com envio final vigente.
- **Nota** = soma das notas ocultas dos envios finais vigentes nas agências liberadas. Agência sem envio vale 0. Bangkok não entra.
- `nao_atendidos` e `custo_infra` só aparecem a partir de H4 (`null` antes).
- **Ordem:** maior nota → menos clientes não atendidos → menor custo de obra → último envio final mais cedo. Equipe sem nenhum final (nota 0) fica acima de equipes com nota negativa.
- **Telão:** a organização projeta o placar numa tela. Ele só lê `/placar`, mostra `#número + nome`, nota total e por agência, finais enviados, saldo de m7Coins e as agências liberadas. Atualiza a cada minuto. Nada além do que está no placar aparece nele. No pré-jogo (abertura), o telão mostra por cima um QR code com o endereço da página `/docs`.

### 12.5 Reenvio e cooldown na prática

- Reenviar uma submissão diferente da vigente custa o valor da tabela (80, 160, 320…) e exige 15 min desde o último envio final **da mesma agência**.
- Os testes não alteram o envio final. Para a nota final valer, **faça o envio final** antes de H7:30.

### 12.6 Códigos de erro

Todas as respostas de erro têm o formato JSON `{"codigo", "mensagem"}`. Algumas acrescentam extras, indicados abaixo.

| HTTP | `codigo` | Quando |
|---|---|---|
| 401 | `nao_autenticado` | PalavraChave ausente ou inválida |
| 402 | `saldo_insuficiente` | taxa maior que o saldo (extras `saldo`, `taxa`) |
| 403 | `jogo_congelado` · `nao_pontua` | teste ou final depois do congelamento · envio final em Bangkok |
| 403 | *(WAF)* | requisição barrada pelas regras de proteção da AWS (corpo pode não ser JSON) |
| 404 | `agencia_indisponivel` · `nao_encontrado` | agência não liberada **ou** inexistente (resposta idêntica) · rota inexistente, ou kit/instruções indisponíveis |
| 405 | `metodo_invalido` | método HTTP não aceito na rota |
| 409 | `identico` · `nome_ja_alterado` · `nome_em_uso` | reenvio igual ao vigente · segunda troca de nome · nome repetido |
| 413 | `corpo_grande` | corpo maior que 10 KB |
| 422 | `invalido` · `json_invalido` · `detalhe_invalido` · `agencia_divergente` · `nome_invalido` · `violacao` | submissão inválida (extra `erros`), corpo malformado, valor de `detalhe` inválido, agência do corpo diferente da rota, nome fora das regras, simulação do envio final com violação (extra `violacoes`; sem cobrar e sem registrar) |
| 429 | `cooldown` · `rate_limit` | cooldown ativo (extra `retry_em`) · mais de 20 req/min por equipe (ou abuso por IP) |
| 500 | `erro_interno` | falha interna; avisem a organização |
| 503 | `jogo_nao_configurado` | o jogo ainda não foi preparado |

---

## 13. Entregáveis, apresentação e premiação

### 13.1 Dashboard obrigatório

Por agência:

- **cascata de pontos** ganhos e perdidos, recalculada pelo **modelo da equipe** e comparada ao juiz;
- curva de potência em 15 min contra o limite (entrada ou demanda contratada) e a janela de ponta;
- ocupação de vagas e tamanho da fila ao longo do tempo;
- distribuição de SOC na retirada e clientes perdidos por dia e hora.

No consolidado:

- m7Coins gastos no juiz e custo de obra (pontos) por agência;
- evolução da nota ao longo do dia;
- justificativa da escolha de entrada e demanda contratada.

### 13.2 Apresentação (12 min + 5 min de perguntas)

Roteiro sugerido:

1. estratégia;
2. como inferiram os pesos na Neblina;
3. modelo próprio e quanto ele bate com o juiz;
4. decisões por agência;
5. reação aos eventos;
6. o que fariam com mais tempo.

### 13.3 Premiação

- **Classificação geral (1º ao 3º):** nota final técnica (seção 8.2), sem interferência do júri.
- **Prêmios especiais, escolhidos pelo júri:**
  - **Melhor dashboard:** clareza, completude e fidelidade ao juiz.
  - **Melhor engenharia elétrica:** racional de entrada, demanda e ponta.
  - **Melhor modelagem:** menor erro do modelo próprio contra o juiz, com menos m7Coins gastos.
  - **Melhor leitura da Neblina:** inferência dos pesos mais próxima dos reais.
- **Rubrica do júri (0 a 5 por critério):** clareza, rigor técnico, uso de dados, qualidade visual, resposta às perguntas. A rubrica escolhe os prêmios especiais e **não** entra na classificação geral.

**O que as equipes podem levar:** o próprio código, o dashboard e os aprendizados. Os dados são fictícios e podem ser citados como tal.

---

## 14. Integridade

| Risco | Como o jogo trata |
|---|---|
| Ajuste fino aos dados públicos | a nota final é calculada só nas semanas ocultas |
| Extrair as semanas ocultas pelo placar ao vivo | cada reenvio custa o dobro do anterior; reenvio idêntico é recusado |
| Força bruta no juiz | cada teste custa m7Coins e há cooldown; o saldo é só um orçamento e não vale pontos |
| Escolher o modelo pela bateria | a devolução vem em km de autonomia |
| Números declarados pela equipe | o juiz refaz tudo; nada declarado entra na nota |
| Deixar uma agência sem envio | agência sem envio final vale 0 |
| Compartilhamento entre equipes | PalavrasChave individuais; todas as chamadas são registradas; submissões idênticas entre equipes podem ser analisadas |

**Regras para a equipe:**

- Use só a API oficial. Não tente acessar dados ocultos, o servidor ou a PalavraChave de outra equipe.
- Não compartilhe a sua PalavraChave nem consulte o juiz em nome de outra equipe.
- Se achar um erro ou comportamento estranho na API, **avise a organização** em vez de explorá-lo.
