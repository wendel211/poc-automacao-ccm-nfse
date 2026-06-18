"""Testes dos decodificadores de chave fiscal, com chaves reais da amostra."""
from src.utils.fiscal_keys import (
    TipoChave,
    classificar,
    decode,
    decode_nfe,
    decode_nfse_nacional,
)

# Chaves reais extraídas de input/janabril2026_amostra_5x5.xlsx
_NFSE_BH = "31062002228203865000174000000000002426013942565090"   # 50 dígitos
_NFSE_RJ = "33045572212977432000136000000000001026010690267031"   # 50 dígitos
_NFE_BH = "31260207221102000186550010000045801593623410"          # 44 dígitos
_NFE_POA = "43260209262608001645670030000055311045694070"         # 44 dígitos


def test_classificar_por_tamanho():
    assert classificar(_NFSE_BH) == TipoChave.NFSE_NACIONAL
    assert classificar(_NFE_BH) == TipoChave.NFE
    assert classificar("YVSC-ARGB") == TipoChave.MUNICIPAL_CURTO
    assert classificar("1f3be52b") == TipoChave.MUNICIPAL_CURTO


def test_classificar_com_espacos():
    espacada = "3126 0207 2211 0200 0186 5500 1000 0045 8015 9362 3410"
    assert classificar(espacada) == TipoChave.NFE


def test_decode_nfse_nacional_bh():
    c = decode_nfse_nacional(_NFSE_BH)
    assert c is not None
    assert c.municipio == "Belo Horizonte/MG"
    assert c.cnpj_emitente == "28203865000174"
    assert c.numero == 24
    assert c.competencia == "2026-01"


def test_decode_nfse_nacional_rj():
    c = decode_nfse_nacional(_NFSE_RJ)
    assert c.municipio == "Rio de Janeiro/RJ"
    assert c.cnpj_emitente == "12977432000136"
    assert c.numero == 10


def test_decode_nfe_valida_dv():
    c = decode_nfe(_NFE_BH)
    assert c is not None
    assert c.uf == "MG"
    assert c.cnpj_emitente == "07221102000186"
    assert c.modelo == "55"
    assert c.numero == 4580
    assert c.competencia == "2026-02"
    assert c.dv_valido is True


def test_decode_nfe_poa_dv_valido():
    c = decode_nfe(_NFE_POA)
    assert c.uf == "RS"
    assert c.dv_valido is True


def test_decode_dv_invalido_quando_chave_corrompida():
    corrompida = _NFE_BH[:-1] + ("0" if _NFE_BH[-1] != "0" else "1")
    c = decode_nfe(corrompida)
    assert c.dv_valido is False


def test_decode_municipal_curto():
    c = decode("YVSC-ARGB")
    assert c.tipo == TipoChave.MUNICIPAL_CURTO
    assert c.cnpj_emitente is None


def test_decode_tamanho_errado_retorna_none():
    assert decode_nfse_nacional("123") is None
    assert decode_nfe("123") is None
