"""Nova Lima connector with NFS-e Nacional fallback.

Nova Lima migrated to the national platform in 2026 and the old municipal
portals are unavailable. Some sample rows, however, carry an NFS-e Nacional
key whose own municipality is Belo Horizonte; in those cases the municipal
registration must be searched in BH's public FIC portal.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.services.bh_fic import consultar_fic_bh
from src.services.nfse_municipal import PORTAL_BH, baixar_nota
from src.services.nova_lima_cadastro import (
    baixar_cadastro_nova_lima,
    consultar_inscricao_nova_lima,
)
from src.utils.fiscal_keys import TipoChave, decode

_nfse_nacional = NfseNacionalConnector("NOVA LIMA")


class NovaLimaConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "NOVA LIMA"

    @property
    def estrategia(self) -> str:
        return "NFS-e Nacional + e-NFS Nova Lima + FIC BH quando a chave aponta Belo Horizonte"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        if _chave_aponta_bh(row):
            logger.info(
                "Nova Lima: chave NFS-e aponta Belo Horizonte; consultando FIC BH para CNPJ {}",
                row.cnpj,
            )
            fic = consultar_fic_bh(row.cnpj)
            return CcmResult(found=fic.success, ccm=fic.ccm, error=fic.error)

        logger.info("Nova Lima: consultando inscricao municipal no e-NFS para CNPJ {}", row.cnpj)
        result = consultar_inscricao_nova_lima(row.cnpj, row.nome_fornecedor)
        if result.success:
            return CcmResult(found=True, ccm=result.inscricao)

        chave = decode(row.cod_verificacao)
        if chave.tipo == TipoChave.NFSE_NACIONAL and chave.municipio == "Nova Lima/MG":
            return CcmResult(found=False, error=result.error)

        logger.info("Nova Lima: e-NFS nao encontrou; tentando FIC BH para CNPJ {}", row.cnpj)
        fic = consultar_fic_bh(row.cnpj)
        if fic.success:
            return CcmResult(found=True, ccm=fic.ccm, error=result.error)
        return CcmResult(found=False, error=result.error or fic.error)

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if _chave_aponta_bh(row):
            cached_fic = dest_dir / f"cadastro_municipal_bh_fic_{row.cnpj}.pdf"
            if cached_fic.exists() and cached_fic.stat().st_size > 1000:
                logger.info("Nova Lima/BH: reutilizando FIC BH ja baixada para CNPJ {}", row.cnpj)
                return DownloadResult(success=True, file_path=str(cached_fic))

            logger.info("Nova Lima: chave NFS-e aponta Belo Horizonte; baixando FIC BH")
            fic = consultar_fic_bh(row.cnpj, dest_dir)
            return DownloadResult(success=fic.success, file_path=fic.file_path, error=fic.error)

        result = baixar_cadastro_nova_lima(row.cnpj, dest_dir)
        if result.success:
            return DownloadResult(success=True, file_path=result.file_path)

        chave = decode(row.cod_verificacao)
        if chave.tipo == TipoChave.NFSE_NACIONAL and chave.municipio == "Nova Lima/MG":
            return DownloadResult(success=False, error=result.error)

        logger.info("Nova Lima: cadastro e-NFS nao disponivel; tentando FIC BH")
        fic = consultar_fic_bh(row.cnpj, dest_dir)
        return DownloadResult(success=fic.success, file_path=fic.file_path, error=result.error or fic.error)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        chave = decode(row.cod_verificacao)
        if chave.tipo == TipoChave.MUNICIPAL_CURTO:
            numero = _format_referencia_bh(row.referencia)
            if not numero:
                return DownloadResult(success=False, error="Referencia BH ausente/invalida para codigo curto")
            logger.info("Nova Lima/BH: tentando NFS-e municipal BH {} / {}", numero, row.cod_verificacao)
            nota = baixar_nota(
                PORTAL_BH,
                row.cnpj,
                numero,
                row.cod_verificacao,
                dest_dir,
                f"nfse_{numero.replace('/', '_')}",
                tem_captcha=True,
            )
            return DownloadResult(success=nota.success, file_path=nota.file_path, error=nota.error)

        logger.info("Nova Lima: roteando nota para NFS-e Nacional")
        return _nfse_nacional.download_invoice(row, dest_dir)


def _chave_aponta_bh(row: InputRow) -> bool:
    chave = decode(row.cod_verificacao)
    return chave.tipo == TipoChave.NFSE_NACIONAL and chave.municipio == "Belo Horizonte/MG"


def _format_referencia_bh(referencia: str | None) -> str | None:
    ref = str(referencia or "").strip()
    if "/" in ref:
        year, number = ref.split("/", 1)
        digits_year = "".join(c for c in year if c.isdigit())
        digits_number = "".join(c for c in number if c.isdigit())
        if len(digits_year) == 4 and digits_number:
            return f"{digits_year}/{int(digits_number)}"
    digits = "".join(c for c in ref if c.isdigit())
    if len(digits) > 4:
        return f"{digits[:4]}/{int(digits[4:])}"
    return None
