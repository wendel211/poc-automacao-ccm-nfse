from pathlib import Path
from src.excel_handler import read_rows
from src.models import Municipio

SAMPLE = Path("input/janabril2026_amostra_5x5.xlsx")


def test_read_all_rows():
    rows = list(read_rows(SAMPLE))
    assert len(rows) == 25


def test_municipalities_present():
    rows = list(read_rows(SAMPLE))
    municipios = {r.municipio for r in rows}
    assert Municipio.BELO_HORIZONTE in municipios
    assert Municipio.BARUERI in municipios
    assert Municipio.RIO_DE_JANEIRO in municipios
    assert Municipio.PORTO_ALEGRE in municipios
    assert Municipio.NOVA_LIMA in municipios


def test_cnpj_normalized():
    rows = list(read_rows(SAMPLE))
    for row in rows:
        assert len(row.cnpj) == 14
        assert row.cnpj.isdigit()


def test_cache_key_unique_per_cnpj_municipio():
    rows = list(read_rows(SAMPLE))
    # 2 linhas com mesmo CNPJ no mesmo município devem ter mesmo cache_key
    keys = [r.cache_key for r in rows]
    # cache_key = municipio::cnpj — fornecedores duplicados devem reutilizar cache
    assert len(set(keys)) < len(keys)  # existe ao menos 1 duplicata na amostra
