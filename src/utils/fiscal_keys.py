"""
Decodificação de chaves fiscais a partir do COD.VERIFICACAO da planilha.

A coluna mistura três formatos distintos, identificados pelo número de dígitos:

  - 50 dígitos  -> Chave de Acesso NFS-e Nacional (serviços, padrão ADN/SEFIN).
  - 44 dígitos  -> Chave de Acesso NF-e / NFC-e (produtos, modelos 55/65).
  - alfanumérico curto -> código de verificação proprietário do portal municipal.

As chaves de 44 e 50 dígitos são auto-contidas: carregam município/UF, CNPJ do
emitente, número, série e competência do documento, além de um dígito verificador
(módulo 11). Isso permite extrair e VALIDAR dados reais de cada nota sem depender
de portal externo — exatamente o caso de uso que os portais bloqueavam.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TipoChave(str, Enum):
    NFSE_NACIONAL = "NFSE_NACIONAL"   # 50 dígitos
    NFE = "NFE"                       # 44 dígitos (modelo 55/65)
    MUNICIPAL_CURTO = "MUNICIPAL_CURTO"  # código proprietário do portal


# Código IBGE (7 dígitos) -> município, usado na chave NFS-e Nacional.
_IBGE_MUNICIPIO = {
    "3106200": "Belo Horizonte/MG",
    "3304557": "Rio de Janeiro/RJ",
    "3505708": "Barueri/SP",
    "4314902": "Porto Alegre/RS",
    "3144805": "Nova Lima/MG",
    "4106902": "Curitiba/PR",
    "3550308": "São Paulo/SP",
}

# Código IBGE da UF (2 dígitos) -> sigla, usado na chave NF-e.
_UF_SIGLA = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

_MODELO_NFE = {"55": "NF-e", "65": "NFC-e", "67": "NFC-e (mod. 67)"}


@dataclass
class ChaveFiscal:
    tipo: TipoChave
    raw: str
    digitos: str
    # Campos preenchidos conforme o tipo:
    municipio: Optional[str] = None        # NFS-e Nacional
    uf: Optional[str] = None               # NF-e
    cnpj_emitente: Optional[str] = None
    modelo: Optional[str] = None           # NF-e
    serie: Optional[str] = None            # NF-e
    numero: Optional[int] = None
    competencia: Optional[str] = None      # AAAA-MM
    dv_valido: Optional[bool] = None

    @property
    def descricao(self) -> str:
        if self.tipo == TipoChave.NFSE_NACIONAL:
            return f"NFS-e Nacional nº {self.numero} | {self.municipio} | comp. {self.competencia}"
        if self.tipo == TipoChave.NFE:
            return (
                f"{_MODELO_NFE.get(self.modelo, 'NF-e')} nº {self.numero} série {self.serie} "
                f"| {self.uf} | comp. {self.competencia}"
            )
        return f"Código municipal: {self.raw}"


def _so_digitos(cod: str) -> str:
    return re.sub(r"\D", "", cod or "")


def _competencia(aamm: str) -> str:
    """AAMM -> AAAA-MM (assume século 2000)."""
    return f"20{aamm[:2]}-{aamm[2:]}"


def _dv_modulo11_nfe(chave43: str) -> int:
    """Dígito verificador da chave NF-e (44 dígitos), módulo 11 com pesos 2..9."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(chave43)))
    resto = soma % 11
    return 0 if resto in (0, 1) else 11 - resto


def classificar(cod: str) -> TipoChave:
    d = _so_digitos(cod)
    if len(d) == 50:
        return TipoChave.NFSE_NACIONAL
    if len(d) == 44:
        return TipoChave.NFE
    return TipoChave.MUNICIPAL_CURTO


def decode_nfse_nacional(cod: str) -> Optional[ChaveFiscal]:
    """
    Layout NFS-e Nacional (50 dígitos):
      cMunIBGE(7) AmbGerador(1) TipoInscFed(1) InscFed(14)
      nNFSe(13) AAMM(4) CodigoNumerico(9) DV(1)
    """
    d = _so_digitos(cod)
    if len(d) != 50:
        return None
    return ChaveFiscal(
        tipo=TipoChave.NFSE_NACIONAL,
        raw=cod,
        digitos=d,
        municipio=_IBGE_MUNICIPIO.get(d[0:7], f"IBGE {d[0:7]}"),
        cnpj_emitente=d[9:23],
        numero=int(d[23:36]),
        competencia=_competencia(d[36:40]),
        dv_valido=None,  # NFS-e Nacional usa SHA-1 truncado, não módulo 11 simples
    )


def decode_nfe(cod: str) -> Optional[ChaveFiscal]:
    """
    Layout NF-e/NFC-e (44 dígitos):
      cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)
    """
    d = _so_digitos(cod)
    if len(d) != 44:
        return None
    return ChaveFiscal(
        tipo=TipoChave.NFE,
        raw=cod,
        digitos=d,
        uf=_UF_SIGLA.get(d[0:2], f"UF {d[0:2]}"),
        competencia=_competencia(d[2:6]),
        cnpj_emitente=d[6:20],
        modelo=d[20:22],
        serie=d[22:25],
        numero=int(d[25:34]),
        dv_valido=_dv_modulo11_nfe(d[:43]) == int(d[43]),
    )


def decode(cod: str) -> ChaveFiscal:
    """Classifica e decodifica qualquer COD.VERIFICACAO."""
    tipo = classificar(cod)
    if tipo == TipoChave.NFSE_NACIONAL:
        return decode_nfse_nacional(cod) or ChaveFiscal(tipo, cod, _so_digitos(cod))
    if tipo == TipoChave.NFE:
        return decode_nfe(cod) or ChaveFiscal(tipo, cod, _so_digitos(cod))
    return ChaveFiscal(tipo=TipoChave.MUNICIPAL_CURTO, raw=cod, digitos=_so_digitos(cod))
