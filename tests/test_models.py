import pytest
from pydantic import ValidationError
from src.models import InputRow, Municipio


def _base_row(**kwargs):
    defaults = dict(
        id_documento="2652712",
        cnpj_raw="28.203.865/0001-74",
        municipio=Municipio.BELO_HORIZONTE,
        cod_verificacao="YVSC-ARGB",
    )
    defaults.update(kwargs)
    return defaults


def test_valid_row():
    row = InputRow(**_base_row())
    assert row.cnpj == "28203865000174"
    assert row.cache_key == "BELO HORIZONTE::28203865000174"


def test_invalid_cnpj():
    with pytest.raises(ValidationError):
        InputRow(**_base_row(cnpj_raw="123"))


def test_invalid_municipio():
    with pytest.raises(ValidationError):
        InputRow(**_base_row(municipio="CIDADE INEXISTENTE"))
