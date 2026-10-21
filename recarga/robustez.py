"""Escolha robusta (spec 5.3): entre os melhores pela nota pública, a de melhor pior semana."""
from statistics import fmean


def escolher(ranking: list, obj_semana, top: int = 10) -> dict:
    """Entre os `top` primeiros do ranking, o de maior mínimo de `obj_semana(metricas_semana, sub_norm)`
    sobre as semanas; desempate pela média; empate total fica com o mais bem colocado no ranking."""
    cands = ranking[:top]
    if not cands:
        raise ValueError("ranking vazio")
    melhor, chave_melhor = None, None
    for r in cands:
        vals = [obj_semana(m, r["sub"]) for m in r["semanas"]]
        chave = (min(vals), fmean(vals))
        if chave_melhor is None or chave > chave_melhor:
            melhor, chave_melhor = r, chave
    return melhor
