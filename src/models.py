from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator
from src.utils.cnpj import normalize as normalize_cnpj


class Municipio(str, Enum):
    BELO_HORIZONTE = "BELO HORIZONTE"
    RIO_DE_JANEIRO = "RIO DE JANEIRO"
    BARUERI = "BARUERI"
    PORTO_ALEGRE = "PORTO ALEGRE"
    NOVA_LIMA = "NOVA LIMA"


class StatusExecucao(str, Enum):
    SUCESSO = "SUCESSO"
    ERRO = "ERRO"
    INDISPONIVEL = "INDISPONIVEL"
    PARCIAL = "PARCIAL"


class InputRow(BaseModel):
    id_documento: str
    empresa: Optional[str] = None
    num_documento: Optional[str] = None
    fornecedor: Optional[str] = None
    nome_fornecedor: Optional[str] = None
    cnpj_raw: str
    ccm_existente: Optional[str] = None
    referencia: Optional[str] = None
    municipio: Municipio
    cod_verificacao: str

    @field_validator("cnpj_raw")
    @classmethod
    def validate_cnpj(cls, v: str) -> str:
        normalize_cnpj(v)
        return v

    @property
    def cnpj(self) -> str:
        return normalize_cnpj(self.cnpj_raw)

    @property
    def cache_key(self) -> str:
        return f"{self.municipio.value}::{self.cnpj}"


class DownloadResult(BaseModel):
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


class CcmResult(BaseModel):
    found: bool
    ccm: Optional[str] = None
    error: Optional[str] = None


class RowResult(BaseModel):
    id_documento: str
    status: StatusExecucao
    mensagem_tecnica: Optional[str] = None
    ccm_encontrado: Optional[str] = None
    arquivo_cadastro: Optional[str] = None
    arquivo_nota_pdf: Optional[str] = None
    arquivo_nota_xml: Optional[str] = None
    arquivo_evidencia: Optional[str] = None
    municipio_estrategia: Optional[str] = None
    data_execucao: Optional[str] = None
