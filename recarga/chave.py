"""Hash canônico de uma submissão (chave de cache do ledger)."""
import hashlib
import json


def chave(sub_normalizada: dict, eventos: list) -> str:
    canon = json.dumps({"sub": sub_normalizada, "eventos": eventos},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
