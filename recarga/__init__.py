"""Pacote da equipe: motor fiel ao juiz, pesos, otimizador e operação da API."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
KIT = RAIZ / "kit_kickoff"
DADOS = KIT / "dados"
RESULTADOS = RAIZ / "resultados"

if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))
