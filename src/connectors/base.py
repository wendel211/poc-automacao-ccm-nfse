"""Interface abstrata que todo conector municipal deve implementar."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path

from src.models import CcmResult, DownloadResult, InputRow


class MunicipalConnector(ABC):
    """
    Cada município implementa este contrato.
    O pipeline principal não conhece detalhes de nenhum portal.
    """

    @property
    @abstractmethod
    def municipio(self) -> str: ...

    @property
    @abstractmethod
    def estrategia(self) -> str:
        """Descrição da estratégia usada (ex: 'API NFS-e Nacional', 'Playwright BHISS')."""
        ...

    @abstractmethod
    def lookup_ccm(self, row: InputRow) -> CcmResult:
        """Consulta CCM/Inscrição Municipal da empresa no portal do município."""
        ...

    @abstractmethod
    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        """Baixa cadastro municipal da empresa (PDF/XML/screenshot)."""
        ...

    @abstractmethod
    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        """Baixa documento da nota fiscal (PDF/XML)."""
        ...
