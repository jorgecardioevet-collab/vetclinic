# -*- coding: utf-8 -*-
"""
Cliente mínimo para a API HTTP do Turso (libSQL) — sem dependências externas.
Usa apenas a biblioteca padrão do Python (urllib).

Documentação da API: https://docs.turso.tech/sdk/http/reference
"""

import base64
import json
import operator
import urllib.error
import urllib.request


class TursoError(Exception):
    """Erro de comunicação ou de SQL retornado pelo Turso."""


def _enc_valor(v):
    """Converte um valor Python para o formato da API (hrana over HTTP)."""
    if v is None:
        return {"type": "null", "value": None}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"type": "blob", "value": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, float):
        return {"type": "float", "value": float(v)}
    try:
        # cobre int e inteiros do numpy/pandas
        return {"type": "integer", "value": str(operator.index(v))}
    except TypeError:
        pass
    return {"type": "text", "value": str(v)}


def _dec_valor(cell):
    """Converte uma célula da resposta da API de volta para Python."""
    tipo = cell.get("type")
    valor = cell.get("value")
    if tipo == "null" or valor is None:
        return None
    if tipo == "integer":
        return int(valor)
    if tipo == "float":
        return float(valor)
    if tipo == "blob":
        return base64.b64decode(valor)
    return valor


def _post(url: str, token: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/v2/pipeline",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        raise TursoError(f"HTTP {e.code} ao acessar {url}. {detalhe}".strip())
    except urllib.error.URLError as e:
        raise TursoError(f"Não foi possível conectar a {url} ({e.reason}).")


def executar(url: str, token: str, sql: str, params=()):
    """
    Executa um statement SQL e devolve (colunas, linhas, linhas_afetadas).
    Levanta TursoError em caso de erro de rede ou de SQL.
    """
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [_enc_valor(p) for p in params]}},
            {"type": "close"},
        ]
    }
    data = _post(url, token, payload)
    results = data.get("results")
    if not results:
        raise TursoError("Resposta vazia do servidor Turso.")
    primeiro = results[0]
    if primeiro.get("type") == "error":
        msg = primeiro.get("error", {}).get("message", "erro desconhecido")
        raise TursoError(msg)
    resultado = primeiro.get("response", {}).get("result", {})
    colunas = [c["name"] for c in resultado.get("cols", [])]
    linhas = [[_dec_valor(cell) for cell in row] for row in resultado.get("rows", [])]
    return colunas, linhas, resultado.get("affected_row_count", 0)
