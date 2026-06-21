"""Belo Horizonte connector using public FIC and BH NFS-e portals."""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.services.bh_fic import consultar_fic_bh
from src.services.nfse_municipal import PORTAL_BH, baixar_nota
from src.utils.cnpj import is_nfse_nacional_key
from src.utils.fiscal_keys import TipoChave, decode

_nfse_nacional = NfseNacionalConnector("BELO HORIZONTE")


class BeloHorizonteConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "BELO HORIZONTE"

    @property
    def estrategia(self) -> str:
        return "BH FIC publica + BHISS/NFS-e com captcha"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("BH: consultando FIC publica para CNPJ {}", row.cnpj)
        fic = consultar_fic_bh(row.cnpj)
        return CcmResult(found=fic.success, ccm=fic.ccm, error=fic.error)

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        cached_fic = dest_dir / f"cadastro_municipal_bh_fic_{row.cnpj}.pdf"
        if cached_fic.exists() and cached_fic.stat().st_size > 1000:
            logger.info("BH: reutilizando FIC ja baixada para CNPJ {}", row.cnpj)
            return DownloadResult(success=True, file_path=str(cached_fic))

        logger.info("BH: baixando FIC publica para CNPJ {}", row.cnpj)
        fic = consultar_fic_bh(row.cnpj, dest_dir)
        return DownloadResult(success=fic.success, file_path=fic.file_path, error=fic.error)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("BH: chave NFS-e Nacional detectada para {}", row.id_documento)
            return _nfse_nacional.download_invoice(row, dest_dir)

        chave = decode(row.cod_verificacao)
        if chave.tipo != TipoChave.MUNICIPAL_CURTO:
            return DownloadResult(
                success=False,
                error=f"Chave {chave.tipo.value} nao e NFS-e municipal de Belo Horizonte",
            )

        numeros = _numeros_nfse_bh(row.referencia)
        if not numeros:
            return DownloadResult(success=False, error="Referencia da NFS-e BH ausente/invalida")

        erros = []
        for numero in numeros:
            nota = baixar_nota(
                PORTAL_BH,
                row.cnpj,
                numero,
                row.cod_verificacao.strip(),
                dest_dir,
                f"nota_bh_{row.id_documento}_{numero.replace('/', '_')}",
                tem_captcha=True,
            )
            if nota.success:
                return DownloadResult(success=True, file_path=nota.file_path)
            if nota.error:
                erros.append(f"{numero}: {nota.error}")

        return DownloadResult(success=False, error="; ".join(erros[-4:]) or "NFS-e BH nao encontrada")


def _numeros_nfse_bh(referencia: str | None) -> list[str]:
    digits = "".join(ch for ch in str(referencia or "") if ch.isdigit())
    if not digits:
        return []
    if "/" in str(referencia or ""):
        return [str(referencia).strip()]
    numero = int(digits)
    return [f"{ano}/{numero}" for ano in range(2026, 2022, -1)]
