"""Porto Alegre connector: SIAT ISSQN registration + NFS-e Nacional."""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.services.nfse_municipal import PORTAL_POA, baixar_nota
from src.services.poa_siat import consultar_comprovante_issqn_poa
from src.utils.cnpj import is_nfse_nacional_key
from src.utils.fiscal_keys import TipoChave, decode

_nfse_nacional = NfseNacionalConnector("PORTO ALEGRE")


class PortoAlegreConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "PORTO ALEGRE"

    @property
    def estrategia(self) -> str:
        return "SIAT ISSQN Porto Alegre + NFS-e Nacional (chave longa)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("POA: consultando inscricao ISSQN no SIAT para CNPJ {}", row.cnpj)
        dest_dir = Path("output") / "evidencias" / "PORTO_ALEGRE" / row.cnpj
        result = consultar_comprovante_issqn_poa(row.cnpj, dest_dir)
        return CcmResult(found=result.success, ccm=result.inscricao, error=result.error)

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        logger.info("POA: baixando comprovante municipal ISSQN via SIAT para CNPJ {}", row.cnpj)
        result = consultar_comprovante_issqn_poa(row.cnpj, dest_dir)
        return DownloadResult(success=result.success, file_path=result.file_path, error=result.error)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("POA: chave NFS-e Nacional - delegando para NfseNacionalConnector")
            return _nfse_nacional.download_invoice(row, dest_dir)

        chave = decode(row.cod_verificacao)
        if chave.tipo != TipoChave.MUNICIPAL_CURTO:
            return DownloadResult(
                success=False,
                error=f"Chave {chave.tipo.value} nao e NFS-e municipal de Porto Alegre",
            )

        numero = _format_referencia_poa(row.referencia)
        if not numero:
            return DownloadResult(success=False, error="Referencia POA ausente/invalida para codigo curto")

        logger.info("POA: tentando NFS-e municipal {} / {}", numero, row.cod_verificacao)
        result = baixar_nota(
            PORTAL_POA,
            row.cnpj,
            numero,
            row.cod_verificacao,
            dest_dir,
            f"nfse_{numero.replace('/', '_')}",
            tem_captcha=False,
        )
        return DownloadResult(success=result.success, file_path=result.file_path, error=result.error)


def _format_referencia_poa(referencia: str | None) -> str | None:
    digits = "".join(c for c in str(referencia or "") if c.isdigit())
    if len(digits) >= 5:
        year = digits[:4]
        number = str(int(digits[4:]))
        return f"{year}/{number}"
    return None
