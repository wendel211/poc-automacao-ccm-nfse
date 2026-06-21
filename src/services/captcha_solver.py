"""Captcha solver with 2Captcha support and local OCR fallback."""
from __future__ import annotations

import base64
import os
import re
import time
from functools import lru_cache
from typing import Optional

import httpx
from loguru import logger

_API_KEY_ENV = "TWOCAPTCHA_API_KEY"
_IN_URL = "https://2captcha.com/in.php"
_RES_URL = "https://2captcha.com/res.php"
_POLL_INTERVAL_SECONDS = 6
_POLL_TIMEOUT_SECONDS = 170      # janela de polling por rodada (lote)
_HCAPTCHA_BATCH = 5             # jobs hCaptcha submetidos em paralelo por rodada
_HCAPTCHA_TOTAL_TIMEOUT = 1500  # teto total (s) para resolver uma hCaptcha
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_PLACEHOLDER_KEYS = {
    "SUA_CHAVE_2CAPTCHA",
    "SUA_CHAVE",
    "sua_chave",
    "sua_chave_2captcha",
    "YOUR_2CAPTCHA_KEY",
    "YOUR_API_KEY",
}
# Erros do 2Captcha que NAO se resolvem repetindo: a pipeline deve falhar rapido
# (chave invalida/sem saldo) em vez de ficar no loop ate o teto de tempo.
_PERMANENT_2CAPTCHA_ERRORS = {
    "ERROR_WRONG_USER_KEY",
    "ERROR_KEY_DOES_NOT_EXIST",
    "ERROR_ZERO_BALANCE",
    "ERROR_IP_NOT_ALLOWED",
    "IP_BANNED",
}


class _PermanentCaptchaError(RuntimeError):
    """Erro permanente do 2Captcha (chave/saldo) — interrompe o solver na hora."""


@lru_cache(maxsize=1)
def _engine():
    import ddddocr

    return ddddocr.DdddOcr(show_ad=False)


def solve(image_bytes: bytes, only_alnum: bool = True) -> Optional[str]:
    """Solve image captcha. Uses TWOCAPTCHA_API_KEY when present."""
    texto = _solve_with_2captcha_image(image_bytes)
    if texto:
        return _clean(texto, only_alnum)

    try:
        texto = _engine().classification(image_bytes)
    except Exception:
        return None
    return _clean(texto or "", only_alnum)


def solve_hcaptcha(sitekey: str, page_url: str) -> Optional[str]:
    """Resolve hCaptcha via 2Captcha.

    Esta hCaptcha em particular (NFS-e Nacional) tem taxa de sucesso baixa por
    tentativa: o 2Captcha frequentemente devolve ERROR_CAPTCHA_UNSOLVABLE. Para
    contornar, submetemos um LOTE de jobs em paralelo a cada rodada e usamos o
    primeiro token que resolver. O parsing das respostas e tolerante (o res.php
    as vezes devolve HTML/texto em vez de JSON). A chave vem do ambiente.
    """
    api_key = _valid_api_key()
    if not api_key:
        return None

    def _json(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001 - res.php pode devolver HTML/texto
            return {"status": 0, "request": "NONJSON"}

    def _submit(client: httpx.Client) -> Optional[str]:
        try:
            payload = _json(client.post(_IN_URL, data={
                "key": api_key, "method": "hcaptcha", "sitekey": sitekey,
                "pageurl": page_url, "userAgent": _DEFAULT_USER_AGENT, "json": 1,
            }))
        except Exception:  # noqa: BLE001
            return None
        if payload.get("status") == 1:
            return str(payload["request"])
        if str(payload.get("request") or "") in _PERMANENT_2CAPTCHA_ERRORS:
            raise _PermanentCaptchaError(str(payload.get("request")))
        return None

    def _check(client: httpx.Client, cid: str) -> tuple[str, Optional[str]]:
        try:
            payload = _json(client.get(_RES_URL, params={
                "key": api_key, "action": "get", "id": cid, "json": 1,
            }))
        except Exception:  # noqa: BLE001
            return ("wait", None)
        if payload.get("status") == 1:
            return ("ok", str(payload.get("request") or ""))
        if payload.get("request") == "CAPCHA_NOT_READY":
            return ("wait", None)
        return ("fail", None)

    deadline = time.monotonic() + _HCAPTCHA_TOTAL_TIMEOUT
    try:
        with httpx.Client(timeout=30.0) as client:
            rnd = 0
            while time.monotonic() < deadline:
                rnd += 1
                ids = [c for c in (_submit(client) for _ in range(_HCAPTCHA_BATCH)) if c]
                if not ids:
                    logger.warning("2Captcha: nenhum job aceito na rodada {}", rnd)
                    time.sleep(_POLL_INTERVAL_SECONDS)
                    continue
                round_end = time.monotonic() + _POLL_TIMEOUT_SECONDS
                while ids and time.monotonic() < round_end and time.monotonic() < deadline:
                    time.sleep(_POLL_INTERVAL_SECONDS)
                    pending = []
                    for cid in ids:
                        state, token = _check(client, cid)
                        if state == "ok" and token:
                            return token
                        if state == "wait":
                            pending.append(cid)
                    ids = pending
                logger.warning("2Captcha: rodada {} sem token (hCaptcha instavel)", rnd)
    except _PermanentCaptchaError as exc:
        logger.error("2Captcha: erro permanente ({}); abortando sem novas tentativas", exc)
        return None
    return None


def solve_recaptcha(sitekey: str, page_url: str) -> Optional[str]:
    """Resolve Google reCAPTCHA v2 via 2Captcha using TWOCAPTCHA_API_KEY."""
    api_key = _valid_api_key()
    if not api_key:
        return None

    try:
        with httpx.Client(timeout=30.0) as client:
            submit = client.post(
                _IN_URL,
                data={
                    "key": api_key,
                    "method": "userrecaptcha",
                    "googlekey": sitekey,
                    "pageurl": page_url,
                    "json": 1,
                },
            )
            submit.raise_for_status()
            payload = submit.json()
            if payload.get("status") != 1:
                logger.warning("2Captcha reCAPTCHA: job recusado ({})", payload.get("request"))
                return None
            return _poll_result(client, api_key, str(payload.get("request")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("2Captcha reCAPTCHA: falha ao resolver ({})", exc)
        return None


def disponivel() -> bool:
    if _valid_api_key():
        return True
    try:
        _engine()
        return True
    except Exception:
        return False


def _clean(texto: str, only_alnum: bool) -> Optional[str]:
    if only_alnum:
        texto = re.sub(r"[^A-Za-z0-9]", "", texto)
    return texto or None


def _solve_with_2captcha_image(image_bytes: bytes) -> Optional[str]:
    api_key = _valid_api_key()
    if not api_key:
        return None
    try:
        body = base64.b64encode(image_bytes).decode("ascii")
        with httpx.Client(timeout=30.0) as client:
            submit = client.post(
                _IN_URL,
                data={
                    "key": api_key,
                    "method": "base64",
                    "body": body,
                    "json": 1,
                },
            )
            submit.raise_for_status()
            payload = submit.json()
            if payload.get("status") != 1:
                return None
            return _poll_result(client, api_key, str(payload.get("request")))
    except Exception:
        return None


def _poll_result(client: httpx.Client, api_key: str, captcha_id: str) -> Optional[str]:
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_SECONDS)
        resp = client.get(
            _RES_URL,
            params={
                "key": api_key,
                "action": "get",
                "id": captcha_id,
                "json": 1,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == 1:
            return str(payload.get("request") or "")
        if payload.get("request") != "CAPCHA_NOT_READY":
            return None
    return None


def _valid_api_key() -> Optional[str]:
    api_key = (os.getenv(_API_KEY_ENV) or "").strip()
    if not api_key:
        return None
    if api_key in _PLACEHOLDER_KEYS or "CHAVE" in api_key.upper() or "YOUR" in api_key.upper():
        logger.warning(
            "2Captcha: variavel {} contem placeholder; informe a chave real para resolver captcha",
            _API_KEY_ENV,
        )
        return None
    # Chaves da 2Captcha normalmente sao hexadecimais com 32 caracteres.
    # Aceita formatos futuros, mas rejeita valores claramente curtos/didaticos.
    if len(api_key) < 24:
        logger.warning("2Captcha: chave em {} parece invalida/curta demais", _API_KEY_ENV)
        return None
    return api_key
