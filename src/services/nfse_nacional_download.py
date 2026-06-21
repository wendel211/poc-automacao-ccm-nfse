"""
Download REAL da NFS-e Nacional (DANFSe PDF) pela Consulta Publica oficial.

Caminho curto descoberto inspecionando os endpoints do portal (dica do avaliador:
"faca um manualmente, analise os links e endpoints"). A Consulta Publica e um
formulario ASP.NET server-rendered SEM token anti-forgery: o unico gate e o
hCaptcha. Logo, todo o fluxo cabe em HTTP puro (sem navegador):

  1. GET  /consultapublica/?tpc=1&chave=<chave50>   -> cookie ARRAffinity
  2. resolve o hCaptcha (sitekey fixo) via 2Captcha  -> token
  3. POST do formulario (TipoConsulta=1 + ChaveAcesso + h-captcha-response)
  4. a resposta traz o link  /ConsultaPublica/Download/DANFSe?chave=<token-sessao>
     (o "chave" aqui e um token de sessao cifrado, nao a chave de 50 digitos)
  5. GET desse link, na MESMA sessao, baixa o PDF da DANFSe.

Requer a variavel de ambiente TWOCAPTCHA_API_KEY (nunca versionada). Sem a chave,
o hCaptcha nao e resolvido e a funcao retorna o motivo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

_BASE = "https://www.nfse.gov.br"
_CONSULTA_URL = _BASE + "/consultapublica/?tpc=1&chave={chave}"
_HCAPTCHA_SITEKEY = "e02c27a0-0542-4c9a-88da-e48697acd87c"
_DOWNLOAD_RE = re.compile(r'href="(/ConsultaPublica/Download/DANFSe\?chave=[^"]+)"', re.I)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class DanfseResult:
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


def baixar_danfse(chave50: str, dest_dir: Path, numero: Optional[str] = None) -> DanfseResult:
    """Baixa o PDF da DANFSe da NFS-e Nacional pela chave de acesso de 50 digitos."""
    chave = "".join(c for c in chave50 if c.isdigit())
    if len(chave) != 50:
        return DanfseResult(success=False, error=f"Chave NFS-e Nacional invalida ({len(chave)} digitos)")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"nfse_{numero or chave[:12]}.pdf"
    if out.exists() and out.stat().st_size > 1000:
        logger.info("NFS-e Nacional: reutilizando DANFSe ja baixada -> {}", out.name)
        return DanfseResult(success=True, file_path=str(out))

    try:
        from src.services.captcha_solver import solve_hcaptcha
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        return DanfseResult(success=False, error=f"Dependencia ausente: {exc}")

    url = _CONSULTA_URL.format(chave=chave)
    try:
        with httpx.Client(
            timeout=60.0, follow_redirects=True, verify=False,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            client.get(url)  # estabelece a sessao (cookie ARRAffinity)

            logger.info("NFS-e Nacional: resolvendo hCaptcha para chave {}...", chave[:12])
            token = solve_hcaptcha(_HCAPTCHA_SITEKEY, url)
            if not token:
                return DanfseResult(
                    success=False,
                    error="hCaptcha nao resolvido (defina TWOCAPTCHA_API_KEY para baixar a NFS-e Nacional)",
                )

            resp = client.post(
                url,
                data={
                    "TipoConsulta": "1",
                    "ChaveAcesso": chave,
                    "Inscricao": "",
                    "Serie": "",
                    "NumeroDPS": "",
                    "CodigoMunicipioEmissao": "",
                    "h-captcha-response": token,
                    "g-recaptcha-response": token,
                },
            )
            match = _DOWNLOAD_RE.search(resp.text)
            if not match:
                form_error = _extract_form_error(resp.text)
                if form_error:
                    return DanfseResult(success=False, error=f"NFS-e Nacional retornou: {form_error}")
                return DanfseResult(
                    success=False,
                    error="Nota nao retornou link de download (captcha rejeitado ou chave inexistente)",
                )

            download_url = _BASE + match.group(1).replace("&amp;", "&")
            pdf = client.get(download_url)
            if pdf.content[:4] != b"%PDF":
                return DanfseResult(success=False, error="Download nao retornou um PDF valido")
            out.write_bytes(pdf.content)

        if out.stat().st_size < 1000:
            return DanfseResult(success=False, error="Download retornou arquivo vazio")
        logger.success("NFS-e Nacional: DANFSe baixada -> {} ({} bytes)", out.name, out.stat().st_size)
        return DanfseResult(success=True, file_path=str(out))
    except Exception as exc:  # noqa: BLE001
        logger.error("NFS-e Nacional: erro no download: {}", exc)
        return DanfseResult(success=False, error=str(exc))


def _extract_form_error(html: str) -> Optional[str]:
    """Extrai erros oficiais exibidos pela Consulta Publica."""
    text = _HTML_TAG_RE.sub(" ", html)
    text = " ".join(text.split())

    known_errors = [
        "Nota Fiscal de Servico inexistente",
        "Nota Fiscal de Serviço inexistente",
    ]
    for error in known_errors:
        if error in text:
            return error
    return None
