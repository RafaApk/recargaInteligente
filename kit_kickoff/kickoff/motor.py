"""Esqueleto do simulador de eventos discretos.

O laço de eventos, o estado e a medição estão prontos. As regras de operação são os métodos
marcados com `# TODO(etapa N)`: sem implementá-los, todo cliente é perdido (atendimento 0%).

Ordem no mesmo minuto (regulamento 5.1): devolução -> abertura/ponta/eventos -> fim de recarga
-> retirada -> fechamento (constantes PRIO_*).
"""
import heapq
import math
from dataclasses import dataclass, field
from typing import Optional

from . import potencia, tempo, validar
from .medicao import Medidor, Retirada
from .modelo import Cenario, Carregador, ModeloVeiculo

PRIO_DEVOLUCAO = 0
PRIO_ABERTURA = 1  # abertura, início/fim da ponta e eventos
PRIO_FIM_RECARGA = 2
PRIO_RETIRADA = 3
PRIO_FECHAMENTO = 4

EPS = 1e-9  # tolerância de SOC (%) nas comparações com o alvo

# Fila de T0 com a agência aberta: True = plugada de uma vez, na ordem da política (leitura de 6.3.3,
# "entram todos no mesmo instante"); False = carro a carro em ordem de id, como `_agendar_inicio` chama
# `entrar_patio`. A CONFIRMAR no juiz com comparar.py numa agência aberta no domingo às 18:00.
PLUG_T0_EM_LOTE = True


@dataclass(eq=False)
class Veiculo:
    id: str
    modelo: ModeloVeiculo
    rank: int
    soc: float
    alvo: float = validar.SOC_ALVO
    plugado: bool = False
    na_fila: bool = False
    entrou_fila_t: Optional[float] = None
    carregador: Optional["Ponto"] = None
    potencia_kw: float = 0.0
    token: int = 0  # incrementar para invalidar 'fim_recarga' já agendado
    soc_limite: Optional[float] = None  # teto do degrau atual; `avancar` nunca passa dele


@dataclass(eq=False)
class Ponto:
    """Instância de carregador (ex.: 'ac_7-0')."""
    id: str
    modelo: Carregador
    conectados: list = field(default_factory=list)
    quebrado: bool = False

    @property
    def livres(self) -> int:
        return self.modelo.saidas - len(self.conectados)


@dataclass
class Resultado:
    retiradas: list
    nao_atendidos: list
    bins: dict
    trace: list
    violacoes: list


class Motor:
    def __init__(self, cenario: Cenario, sub: dict, eventos=()):
        """`sub` é a submissão normalizada (validar.normalizar)."""
        self.cen = cenario
        self.sub = sub
        self.pol = sub["politica"]
        self.limite_kw = validar.limite_kw(sub, cenario)
        self.t = tempo.T0
        self.heap: list = []
        self.seq = 0
        self.medidor = Medidor()
        self.retiradas: list = []
        self.nao_atendidos: list = []
        self.trace: list = []
        self.violacoes: list = []
        self.patio: dict = {}
        self.fila: list = []
        self.aberta = tempo.aberta(cenario.agencia, tempo.T0)
        self.em_ponta = self.pol["evitar_ponta"] and tempo.eh_ponta(tempo.T0)
        self.contratos = {c.id: c for c in cenario.contratos}
        self.veiculos = {
            v.id: Veiculo(v.id, cenario.modelos[v.modelo], v.rank, v.soc) for v in cenario.veiculos
        }
        self.pontos = []
        for modelo_id in sorted(sub["carregadores"]):  # 6.3.4: empate pelo id em ordem alfabética
            for i in range(sub["carregadores"][modelo_id]):
                self.pontos.append(Ponto(f"{modelo_id}-{i}", cenario.carregadores[modelo_id]))
        self.eventos = eventos
        self._abertura_t0 = False  # abertura extra em T0 para plugar a fila inicial (entrar_patio)
        # proxima_retirada (6.3.3): contratos em ordem de horário, os já processados (retirados ou
        # perdidos) e um ponteiro por rank para o primeiro contrato compatível ainda não processado
        self._contratos_ordem = sorted(cenario.contratos, key=lambda c: (c.retirada_t, c.id))
        self._processados: set = set()
        self._ptr_reserva: dict = {}

    # ---------- pronto: laço de eventos ----------

    def agendar(self, t: float, prio: int, tipo: str, *payload) -> None:
        self.seq += 1
        heapq.heappush(self.heap, (t, prio, self.seq, tipo, payload))

    def _agendar_inicio(self) -> None:
        cen, ag = self.cen, self.cen.agencia
        fim_dados = max((c.devolucao_t if c.devolucao_t is not None else c.retirada_t) for c in cen.contratos) \
            if cen.contratos else tempo.T0
        horizonte = fim_dados + 4 * tempo.DIA
        d0, d1 = tempo.T0 // tempo.DIA, horizonte // tempo.DIA

        # abertura/fechamento: junta dias seguidos (ex.: 24h) e só marca as bordas
        blocos = []
        for d in range(d0 - 1, d1 + 2):
            j = ag.horario[(6 + d) % 7]
            if j is None:
                continue
            ini, fim = d * tempo.DIA + j[0], d * tempo.DIA + j[1]
            if blocos and blocos[-1][1] == ini:
                blocos[-1][1] = fim
            else:
                blocos.append([ini, fim])
        for ini, fim in blocos:
            if ini >= tempo.T0:
                self.agendar(ini, PRIO_ABERTURA, "abertura")
            if tempo.T0 < fim <= horizonte + tempo.DIA:
                self.agendar(fim, PRIO_FECHAMENTO, "fechamento")

        if self.pol["evitar_ponta"]:
            for d in range(d0, d1 + 1):
                if (6 + d) % 7 < 5:
                    ini, fim = d * tempo.DIA + tempo.PONTA[0], d * tempo.DIA + tempo.PONTA[1]
                    if ini > tempo.T0:
                        self.agendar(ini, PRIO_ABERTURA, "ponta", True)
                    if fim > tempo.T0:
                        self.agendar(fim, PRIO_ABERTURA, "ponta", False)

        for vt in sorted(cen.veiculos, key=lambda x: x.id):
            if vt.situacao == "em_contrato":
                self.agendar(max(vt.devolucao_t, tempo.T0), PRIO_DEVOLUCAO, "devolucao", vt.id, vt.soc_devolucao)
            else:
                self.entrar_patio(self.veiculos[vt.id], tempo.T0)
        for c in cen.contratos:
            self.agendar(c.retirada_t, PRIO_RETIRADA, "retirada", c.id)
        self.agendar_eventos(self.eventos)
        self.anotar(tempo.T0)

    def rodar(self) -> Resultado:
        self._agendar_inicio()
        while self.heap:
            t, _, _, tipo, p = heapq.heappop(self.heap)
            self.avancar(t)
            if tipo == "devolucao":
                self.on_devolucao(p[0], p[1], t)
            elif tipo == "abertura":
                self.on_abertura(t)
            elif tipo == "fechamento":
                self.on_fechamento(t)
            elif tipo == "ponta":
                self.on_ponta(p[0], t)
            elif tipo == "evento":
                self.on_evento(t, *p)
            elif tipo == "fim_recarga":
                self.on_fim_recarga(p[0], p[1], t)
            elif tipo == "retirada":
                self.on_retirada(p[0], t)
            self.anotar(t)
        return Resultado(self.retiradas, self.nao_atendidos, self.medidor.bins, self.trace, self.violacoes)

    def avancar(self, t: float) -> None:
        """Integra a recarga de self.t até t com as potências vigentes e mede a energia."""
        dt = t - self.t
        if dt > 0:
            for ponto in self.pontos:
                for v in ponto.conectados:
                    if v.potencia_kw > 0 and v.soc < v.alvo:
                        teto = min(v.alvo, v.soc_limite) if v.soc_limite is not None else v.alvo
                        novo = min(teto, v.soc + v.potencia_kw * dt / 60.0 / v.modelo.bateria_kwh * 100.0)
                        self.medidor.adicionar(self.t, t, (novo - v.soc) / 100.0 * v.modelo.bateria_kwh)
                        v.soc = novo
            self.t = t

    def anotar(self, t: float) -> None:
        """Registra (t, plugados, fila) quando muda."""
        ponto = (sum(1 for v in self.patio.values() if v.plugado), len(self.fila))
        if not self.trace or self.trace[-1][1:] != ponto:
            self.trace.append((t, *ponto))

    # ---------- pronto: auxiliares de estado ----------

    def plugar(self, v: Veiculo, ponto: Ponto) -> None:
        """Só contabilidade: conecta v em ponto e tira da fila. Não decide nem calcula potência."""
        if v.na_fila:
            self.fila.remove(v)
            v.na_fila = False
        ponto.conectados.append(v)
        v.plugado, v.carregador = True, ponto

    def desplugar(self, v: Veiculo) -> None:
        if v.carregador is not None:
            v.carregador.conectados.remove(v)
        v.plugado, v.carregador, v.potencia_kw, v.soc_limite = False, None, 0.0, None
        v.token += 1

    def sair_do_patio(self, v: Veiculo) -> None:
        if v.plugado:
            self.desplugar(v)
        if v.na_fila:
            self.fila.remove(v)
            v.na_fila = False
        v.token += 1
        self.patio.pop(v.id, None)

    def violar(self, msg: str) -> None:
        self.violacoes.append(f"{tempo.texto(self.t)}: {msg}")

    def checar_ocupacao(self) -> None:
        """plugados <= saídas instaladas <= vagas (5.2)."""
        saidas = sum(p.modelo.saidas for p in self.pontos)
        plugados = sum(len(p.conectados) for p in self.pontos)
        if plugados > saidas:
            self.violar(f"{plugados} plugados > {saidas} saídas")
        if saidas > self.cen.agencia.vagas:
            self.violar(f"{saidas} saídas > {self.cen.agencia.vagas} vagas")

    # ---------- pronto: retirada ----------

    def on_retirada(self, contrato_id: str, t: float) -> None:
        self.avancar(t)
        self._processados.add(contrato_id)  # sai da "próxima reserva" (proxima_retirada), atendido ou não
        c = self.contratos[contrato_id]
        v = self.escolher_carro(c, t)
        if v is None:
            self.nao_atendidos.append(t)
            return
        estava_plugado = v.plugado
        self.sair_do_patio(v)
        self.retiradas.append(Retirada(t, c.id, v.id, c.rank, v.rank, v.soc))
        if c.devolucao_t is not None:
            self.agendar(max(c.devolucao_t, t), PRIO_DEVOLUCAO, "devolucao", v.id, self.soc_devolucao(v, c))
        if estava_plugado:
            self.recalcular_potencias(t)

    # ================= TODO: regras de operação =================

    def soc_devolucao(self, v: Veiculo, c) -> float:
        """SOC com que o carro volta (regulamento 4.1).

        SOC = km_devolucao / autonomia_km do modelo que atendeu * 100, nunca acima do SOC com que saiu
        (`v.soc` neste momento). `c.km_devolucao` é a autonomia restante em km.
        """
        if c.km_devolucao is None:
            return v.soc
        return min(v.soc, c.km_devolucao / v.modelo.autonomia_km * 100.0)

    def entrar_patio(self, v: Veiculo, t: float) -> None:
        """Carro entra no pátio (T0 ou devolução).

        Abaixo do SOC alvo (80%) vai para a fila de recarga (5.2), registrando `entrou_fila_t`;
        acima, fica apto no pátio. Depois tente plugar (`plugar_fila`) e recalcule as potências.
        """
        self.patio[v.id] = v
        if v.soc < v.alvo - EPS:
            v.na_fila = True
            v.entrou_fila_t = t
            self.fila.append(v)
        if PLUG_T0_EM_LOTE and not self.trace:
            # Ainda em _agendar_inicio (o trace só começa no fim dele): a fila de T0 entra toda no
            # mesmo instante (6.3.3) e é plugada de uma vez, na ordem da política, numa abertura em T0.
            if v.na_fila and self.aberta and not self._abertura_t0:
                self._abertura_t0 = True
                self.agendar(t, PRIO_ABERTURA, "abertura")
            return
        self.plugar_fila(t)
        self.recalcular_potencias(t)

    def escolher_carro(self, c, t: float) -> Optional[Veiculo]:
        """Carro do pátio para o contrato c, ou None (cliente perdido). Regulamento 5.1 e 6.3.1.

        Elegível: categoria >= pedida (`v.rank >= c.rank`; upgrade sim, downgrade nunca) e SOC >= 80%.
        Ordem: menor upgrade -> menor SOC -> não plugado -> menor `id` (alfabético).
        Ex. 6.3.1 (contrato Prata): Geely 82% sem upgrade e menor SOC entre os aptos sai antes do
        Dolphin Mini 95% plugado; com o Geely a 78%, sai o Dolphin Mini; sem Prata apto, sai o MG4 (upgrade).
        Com a agência fechada, ninguém retira (os contratos já vêm em horário de funcionamento).
        """
        aptos = [v for v in self.patio.values() if v.rank >= c.rank and v.soc >= v.alvo - EPS and not v.na_fila]
        if not aptos:
            return None
        return min(aptos, key=lambda v: (v.rank - c.rank, v.soc, v.plugado, v.id))

    def ordenar_fila(self, t: float) -> None:
        """Ordena `self.fila` pela política (`self.pol['prioridade']`). Regulamento 6.3.3.

        Chamar a cada tentativa de plugar. Último desempate sempre o menor `id`.
        - `chegada`: FIFO por `entrou_fila_t` (os carros da fila em T0 entram todos no mesmo instante).
        - `menor_soc`: menor autonomia restante em km (`autonomia_km * soc / 100`) primeiro; km, não SOC.
        - `proxima_retirada`: primeiro quem tem a próxima reserva compatível mais cedo = primeiro contrato
          ainda não retirado, em ordem de horário, com categoria <= a do carro; sem reserva vai para o fim.
          Empate: maior SOC, depois menor `id`.
        Ex. 6.3.3: A(Bronze 30%, 55.5 km), B(Prata 20%, 56.0 km), C(Ouro 55%), D(Diamante 40%) ->
        menor_soc A,B,D,C; chegada A,B,C,D; proxima_retirada C,D,B,A.
        """
        self.fila.sort(key=lambda v: self._chave_prioridade(v, t))

    def _chave_prioridade(self, v: Veiculo, t: float) -> tuple:
        """Chave de ordenação da `prioridade` (6.3.3); vale para a fila e para `divisao: prioridade`."""
        pr = self.pol["prioridade"]
        if pr == "chegada":
            return (v.entrou_fila_t, v.id)
        if pr == "menor_soc":
            # km arredondado: o SOC de devolução vem de km/autonomia*100, e o caminho de volta
            # (autonomia*SOC/100) erra no ponto flutuante — sem isso, empates exatos em km (desempate
            # por id, 6.3.3) viram desigualdades espúrias.
            return (round(v.modelo.autonomia_km * v.soc / 100.0, 6), v.id)
        r = self._proxima_reserva(v.rank)
        return (math.inf if r is None else r, -round(v.soc, 9), v.id)

    def _proxima_reserva(self, rank: int) -> Optional[float]:
        """Horário do primeiro contrato ainda não retirado com categoria <= `rank` (None se não houver)."""
        lista = self._contratos_ordem
        i = self._ptr_reserva.get(rank, 0)
        while i < len(lista) and (lista[i].rank > rank or lista[i].id in self._processados):
            i += 1
        self._ptr_reserva[rank] = i
        return lista[i].retirada_t if i < len(lista) else None

    def _plugados_ordenados(self, t: float) -> list:
        """Plugados que ainda carregam (SOC abaixo do alvo), na ordem da `prioridade`."""
        carregando = [v for p in self.pontos for v in p.conectados if v.soc < v.alvo - EPS]
        carregando.sort(key=lambda v: self._chave_prioridade(v, t))
        return carregando

    def escolher_ponto(self, v: Veiculo) -> Optional[Ponto]:
        """Em qual carregador v pluga (6.3.4), ou None se não houver saída livre.

        Entre os pontos em operação (`not quebrado`) com saída livre, o que daria MAIS potência a v:
        potência nominal do carregador dividida igualmente entre v e quem já está ali, cada um limitado
        pela sua curva (`potencia.potencia_curva`, AC/DC conforme o carregador). Ignora o limite da agência
        e a `divisao`. Empate: o primeiro de `self.pontos` (ordem alfabética do id).
        Ex.: DC-60 com um Geely 30% e AC-22 vazio; chega Dolphin GS 20%: no DC-60 teria 60/2 = 30 kW,
        no AC-22 só 7 kW -> DC-60.
        """
        melhor, kw_melhor = None, -1.0
        for p in self.pontos:
            if p.quebrado or p.livres <= 0:
                continue
            tipo = p.modelo.tipo
            caps = [potencia.potencia_curva(x.modelo, x.soc, tipo) for x in p.conectados if x.soc < x.alvo - EPS]
            caps.append(potencia.potencia_curva(v.modelo, v.soc, tipo))
            kw = potencia.enchimento_agua(p.modelo.potencia_kw, caps)[-1]
            if kw > kw_melhor + EPS:
                melhor, kw_melhor = p, kw
        return melhor

    def plugar_fila(self, t: float) -> None:
        """Pluga a fila (5.2, 6.3.3): só com a agência aberta, na ordem da fila, enquanto houver saída livre.

        Ordene (`ordenar_fila`), escolha o ponto (`escolher_ponto`), conecte (`plugar`) e recalcule as
        potências. Chamar quando um carro volta, termina a recarga, a agência abre ou um carregador volta.
        Respeite plugados <= saídas (`checar_ocupacao`).
        """
        if not self.aberta or not self.fila:
            return
        self.ordenar_fila(t)
        plugou = False
        for v in list(self.fila):
            p = self.escolher_ponto(v)
            if p is None:
                break
            self.plugar(v, p)
            plugou = True
        if plugou:
            self.checar_ocupacao()
            self.recalcular_potencias(t)

    def recalcular_potencias(self, t: float) -> None:
        """Define `v.potencia_kw` de cada plugado (5.3, 6.3.5) e reagenda os fins de degrau.

        Recalcular a cada mudança: carro pluga/despluga, troca de degrau, início/fim da ponta, evento.
        Carro quebrado/em ponta com `evitar_ponta` -> 0 kW (continua plugado). Carro com SOC >= alvo -> 0.
        Camada 1: dentro de cada carregador, a potência nominal vai para os carros que ainda carregam,
        com teto na curva do carro (`potencia.potencia_curva`). Camada 2: o limite da agência
        (`self.limite_kw`) é repartido, e o que cada carro recebeu na camada 1 é o seu máximo.
        `divisao`: `igual` -> `potencia.enchimento_agua`; `prioridade` -> `potencia.sequencial` na ordem
        da `prioridade` (ordenar a lista de plugados pela mesma regra da fila).
        Ex. 6.3.5 (limite 40.5, 2x DC-60, Kwid 26.6, Geely 71.5, JAC 16.45, Dolphin GS 47.75):
        igual -> 10.125 kW para cada um; prioridade (menor_soc) -> Kwid 26.6, Geely 13.9, JAC 0, Dolphin 0.
        Com limite 80: igual -> JAC 16.45 e os outros 21.18333; prioridade -> Kwid 26.6, Geely 53.4, demais 0.
        Depois chame `agendar_fim_degrau` para cada carro.
        """
        dividir = potencia.sequencial if self.pol["divisao"] == "prioridade" else potencia.enchimento_agua
        # ainda carregando, na ordem da `prioridade`; na ponta com `evitar_ponta`, ninguém carrega
        ordenados = [] if self.em_ponta else self._plugados_ordenados(t)
        pos = {v.id: i for i, v in enumerate(ordenados)}
        for p in self.pontos:
            for v in p.conectados:
                v.potencia_kw = 0.0
        # camada 1: potência nominal do carregador entre os carros que ainda carregam, teto na curva
        for p in self.pontos:
            carregando = sorted((v for v in p.conectados if v.id in pos), key=lambda v: pos[v.id])
            if p.quebrado or not carregando:
                continue
            caps = [potencia.potencia_curva(v.modelo, v.soc, p.modelo.tipo) for v in carregando]
            for v, kw in zip(carregando, dividir(p.modelo.potencia_kw, caps)):
                v.potencia_kw = kw
        # camada 2: limite da agência; o que cada carro levou na camada 1 é o seu teto
        for v, kw in zip(ordenados, dividir(self.limite_kw, [v.potencia_kw for v in ordenados])):
            v.potencia_kw = kw
        for p in self.pontos:
            for v in p.conectados:
                self.agendar_fim_degrau(v, t)

    def agendar_fim_degrau(self, v: Veiculo, t: float) -> None:
        """Agenda 'fim_recarga' para quando v chega ao próximo degrau de 5% ou ao alvo (5.3, 6.3.2).

        A potência é constante dentro do degrau [5i, 5i+5). Próximo limite = min(alvo, (i+1)*5) com
        i = int(soc/5 + 1e-9). Tempo = (limite - soc)/100 * bateria_kwh / potencia_kw * 60 min.
        Defina `v.soc_limite` = esse limite, incremente `v.token` (invalida agendamentos antigos) e use
        `self.agendar(t + dt, PRIO_FIM_RECARGA, 'fim_recarga', v.id, v.token)`. Potência 0 -> não agende.
        Ex. 6.3.2: Dolphin GS (44.9 kWh) de 20% a 80% sozinho num DC-60 leva 36,7 min.
        """
        i = int(v.soc / 5 + 1e-9)
        limite = min(v.alvo, (i + 1) * 5.0)
        v.soc_limite = limite
        v.token += 1
        if v.soc >= v.alvo - EPS:
            # Chegou ao alvo, mas outro evento no mesmo instante recalculou antes e invalidou o
            # 'fim_recarga' dele: reagenda em t para desplugar agora (5.2), na ordem de 5.1.
            if v.plugado and self.aberta:
                self.agendar(t, PRIO_FIM_RECARGA, "fim_recarga", v.id, v.token)
            return
        if v.potencia_kw <= 0:
            return
        dt = (limite - v.soc) / 100.0 * v.modelo.bateria_kwh / v.potencia_kw * 60.0
        self.agendar(t + dt, PRIO_FIM_RECARGA, "fim_recarga", v.id, v.token)

    def on_fim_recarga(self, vid: str, token: int, t: float) -> None:
        """Chegou ao fim do degrau. Ignore se `token` != `v.token` (agendamento velho).

        Ao atingir o alvo (80%): desplugar se a agência estiver aberta; se fechada, segura a saída até
        a abertura (5.2). Depois tente plugar a fila (`plugar_fila`) e recalcule as potências.
        """
        v = self.veiculos[vid]
        if token != v.token or not v.plugado:
            return
        # token válido = potência constante desde o agendamento: o carro está no limite do degrau
        # (fixa o valor exato para não acumular erro de ponto flutuante na troca de degrau)
        if v.soc_limite is not None:
            v.soc = max(v.soc, v.soc_limite)
        if v.soc >= v.alvo - EPS and self.aberta:
            self.desplugar(v)
            self.plugar_fila(t)
        self.recalcular_potencias(t)

    def on_devolucao(self, vid: str, soc: float, t: float) -> None:
        """Carro volta do contrato com `soc` e entra no pátio. Um carro devolvido apto pode sair no mesmo minuto (5.1)."""
        v = self.veiculos[vid]
        v.soc = soc
        self.entrar_patio(v, t)

    def on_abertura(self, t: float) -> None:
        """Agência abre. Com ela aberta, plugar e desplugar voltam a valer (5.2).

        Desplugue quem está parado no alvo (80%) segurando saída, depois `plugar_fila`.
        """
        self.aberta = True
        parados = [v for p in self.pontos for v in p.conectados if v.soc >= v.alvo - EPS]
        for v in parados:
            self.desplugar(v)
        self.plugar_fila(t)
        if parados:
            self.recalcular_potencias(t)

    def on_fechamento(self, t: float) -> None:
        """Agência fecha: ninguém retira nem pluga/despluga; a recarga continua (5.2).

        Quem atinge 80% com a agência fechada segura a saída até a abertura.
        """
        self.aberta = False  # a recarga continua; plugar/desplugar esperam a abertura

    def on_ponta(self, inicio: bool, t: float) -> None:
        """Início/fim da ponta (seg-sex 18:00-21:00) com `evitar_ponta` (5.3, 6.3.6).

        Na ponta todos a 0 kW, continuam plugados e plugar continua permitido. Recalcule as potências.
        """
        self.em_ponta = inicio
        self.recalcular_potencias(t)

    def agendar_eventos(self, eventos) -> None:
        """Agenda os eventos ao vivo (seção 11). `eventos`: lista de `params` (minutos desde 17/10/2049 00:00).

        O significado e o formato de `params` são explicados no anúncio de cada evento; vêm de
        `eventos_ativos` de GET /status. Ex. de uso: `self.agendar(t, PRIO_ABERTURA, 'evento', params)`.
        """
        for params in eventos:
            tipo = params[0]
            if tipo == "corte":  # ["corte", agencia, inicio_min, fim_min, fator]: limite da agência × fator
                _, _, ini, fim, fator = params
                self.agendar(ini, PRIO_ABERTURA, "evento", "corte_ini", fator)
                self.agendar(fim, PRIO_ABERTURA, "evento", "corte_fim", fator)
            elif tipo == "quebra_maiores":  # ["quebra_maiores", agencia, n, inicio_min, fim_min]: n maiores fora
                _, _, n, ini, fim = params
                self.agendar(ini, PRIO_ABERTURA, "evento", "quebra_ini", n)
                self.agendar(fim, PRIO_ABERTURA, "evento", "quebra_fim", n)
            else:
                self.violar(f"evento desconhecido: {params!r}")

    def on_evento(self, t: float, *params) -> None:
        """Aplica um evento no instante t (ex.: limite da concessionária, carregador fora de operação).

        Recalcule as potências; ao voltar um carregador, tente plugar a fila (6.3.3).
        """
        acao = params[0]
        if acao == "corte_ini":
            self._limite_base = self.limite_kw
            self.limite_kw = self._limite_base * params[1]
        elif acao == "corte_fim":
            self.limite_kw = getattr(self, "_limite_base", self.limite_kw)
        elif acao == "quebra_ini":
            # maiores por potência nominal; empate pela ordem dos pontos (id alfabético)
            for ponto in sorted(self.pontos, key=lambda p: -p.modelo.potencia_kw)[:params[1]]:
                ponto.quebrado = True
        elif acao == "quebra_fim":
            for ponto in self.pontos:
                ponto.quebrado = False
            self.recalcular_potencias(t)
            self.plugar_fila(t)
        self.recalcular_potencias(t)


def simular(cenario: Cenario, sub_normalizada: dict, eventos=()) -> Resultado:
    return Motor(cenario, sub_normalizada, eventos).rodar()
