# Anexo H4 — Pesos da pontuação e custos de obra

**Publicado na revelação (H4).** Complementa o Regulamento das equipes (seções 7, 8 e 10).

---

## 1. Pesos da pontuação

Valores padrão, aplicados a cada agência pontuada:

| Item | Peso | Medida |
|---|---:|---|
| Cliente atendido na categoria certa | **+15** | por contrato |
| Cliente atendido com upgrade | **+8** | por contrato |
| Cliente não atendido | **−200** | por contrato |
| Demanda contratada | **−2** | por kW contratado (só em A4/SE; B3 não paga) |
| Energia carregada na ponta | **−0,5** | por kWh (seg–sex, 18–21h) |
| Infraestrutura | **−1** | por ponto de custo de obra (seção 2): carregadores + ampliação de entrada |

```
nota = 15 × certos + 8 × upgrades − 200 × não atendidos
       − 2 × demanda contratada (kW) − 0,5 × kWh na ponta − custo de obra (pontos)
```

- O custo de obra e a demanda contratada entram **inteiros** em cada janela avaliada (teste ou envio final).
- Omitir `demanda_contratada_kw` em A4/SE vale a demanda máxima da entrada (kW útil arredondado para baixo ao múltiplo de 10; ex.: 130 kW no `a4_150`). Valores enviados são arredondados ao múltiplo de 10 mais próximo.

### Ajuste de pesos pela organização

A organização **pode ajustar os pesos por agência durante o dia**. Os valores se aplicam na hora, aos testes e ao placar, inclusive aos envios finais já feitos (sem nova simulação).

Os **valores vigentes** de cada agência liberada estão sempre em **`GET /catalogo`**, no campo **`pesos`**, depois de H4. Consulte esse campo antes de decidir; este anexo traz os valores padrão.

---

## 2. Custos de obra (em pontos)

O custo de obra é descontado **só na nota da agência** em que o item foi instalado, como o item "Infraestrutura" (−1 por ponto). Não passa pelo saldo de m7Coins.

### 2.1 Carregadores

| Id | Modelo | Tipo | kW | Saídas | Custo de obra (pontos) |
|---|---|---|---:|---:|---:|
| `ac_7` | AC-7 | AC | 7 | 1 | 250 |
| `ac_11` | AC-11 | AC | 11 | 1 | 1.100 |
| `ac_22x2` | AC-22 (2 saídas) | AC | 22 | 2 | 1.500 |
| `dc_30` | DC-30 | DC | 30 | 1 | 3.500 |
| `dc_60x2` | DC-60 (2 saídas) | DC | 60 | 2 | 7.300 |
| `dc_120x2` | DC-120 (2 saídas) | DC | 120 | 2 | 15.800 |

O custo é **por unidade** do carregador instalado (um `dc_60x2` custa 7.300 pontos e tem 2 saídas).

### 2.2 Entrada elétrica

| Id | Nível | kVA | kW útil | Custo de obra (pontos) |
|---|---|---:|---:|---:|
| `b3_45` | B3 45 kVA | 45 | 40,5 | só como entrada existente |
| `b3_75` | B3 75 kVA | 75 | 67,5 | 5.000 |
| `a4_150` | A4 em poste 150 kVA | 150 | 135 | 6.500 |
| `a4_225` | A4 em poste 225 kVA | 225 | 202,5 | 8.200 |
| `a4_300` | A4 em poste 300 kVA | 300 | 270 | 10.000 |
| `se_500` | Subestação 500 kVA | 500 | 450 | 18.800 |
| `se_750` | Subestação 750 kVA | 750 | 675 | 24.400 |
| `se_1000` | Subestação 1 MVA | 1000 | 900 | 30.000 |
| `se_1500` | Subestação 1,5 MVA | 1500 | 1350 | 41.200 |
| `se_2000` | Subestação 2 MVA | 2000 | 1800 | 52.500 |

**Regra de cobrança:**

- **Ampliar** a entrada custa o valor **cheio** do novo nível, sem crédito pela entrada existente.
- **Manter** a entrada existente custa **0**. Se a existente já for A4 ou subestação, manter também custa 0.
- O `b3_45` só vale como entrada existente da agência.
- Ampliar de `b3_45` para `b3_75` custa **5.000** pontos (valor cheio do `b3_75`). O `b3_75` continua B3: sem demanda contratada.

Depois de H4, os mesmos valores aparecem no campo `custo` de `GET /catalogo`, e o envio final devolve `custo_infra` em pontos.
