# Dashboard Os Caórdicos · Recarga Inteligente

Dashboard obrigatório (regulamento, seção 13.1), adaptado do projeto Figma Make original para os dados reais da equipe e para a paleta Localiza.

## Rodar

```bash
python kit_kickoff/gerar_dados_dashboard.py   # motor + placar -> dashboard_localiza/public/data/*.json (opcional)
cd dashboard_localiza
npm install
npm run dev                                   # http://localhost:5173
```

Os dados de `public/data` já vêm commitados (foto das 20:30 UTC de 21/10), então o dashboard abre sem rodar o Python.
Para atualizar, o script precisa de `kit_kickoff/dados/<Agencia>/` e `kit_kickoff/dados/catalogo.json`, de `GAMEDAY_URL` e
`GAMEDAY_TOKEN` (placar) e, para os eventos ativos, de um `kit_kickoff/eventos.json` copiado de `GET /status`.
Sem a API, use `--offline` (reaproveita o `placar.json` salvo).

## De onde vêm os números

| Parte | Fonte |
|---|---|
| Placar, nota por agência, evolução da nota | `GET /placar` (semanas **ocultas**) |
| Envios vigentes | `resultados/finais.jsonl` do repositório da equipe |
| Cascata, potência, ocupação, fila, SOC, perdidos | motor local, 4 semanas **públicas**, com os pesos de `dados/catalogo.json` |
| m7Coins por agência | `resultados/ledger.jsonl` (não inclui testes feitos pelo site) |
| Eventos ao vivo | `eventos.json` (cópia de `GET /status`): quebra de Istanbul e corte de Marrakech, marcados nos gráficos |
| Pendências e próximos envios | agências do placar sem nota da equipe (hoje, Lisbon) e `envios/*_candidata.json` simulados no motor |

Os eventos entram no motor como suposições, ainda não confirmadas pelo juiz: o corte de Marrakech reduz o limite da agência a 70%, e a quebra de Istanbul deixa os 2 maiores carregadores fora de operação por 48 h.

Para atualizar depois de novos envios: `git pull`, copie o `/status` para `kit_kickoff/eventos.json` e rode o script de dados de novo.

## O que mudou em relação ao projeto original

- Dados de exemplo trocados pelos reais (`src/data.ts` lê `public/data`).
- Paleta Localiza: verde escuro `#01602A` e verde claro `#78DE1F` (referência de brandcolorcode.com). O amarelo é uma aproximação.
- Sem logotipo nem nome da marca: a identidade é a da equipe.
- Textos de 7 a 9 px passaram para 11 a 13 px.
- Seletor de período virou seletor de semana (os dados são 4 semanas, não horas).
- Bangkok saiu das abas (não pontua) e Vienna entrou. Novo cartão com o placar completo.
- Build mínimo (React + Vite): os plugins do Figma Make não são necessários.
