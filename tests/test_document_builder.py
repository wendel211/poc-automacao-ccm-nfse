"""Testes da geração de artefatos baixáveis (PDF de cadastro e JSON da nota)."""
import json

from src.services.cnpj_lookup import CompanyData
from src.services.document_builder import (
    build_company_registration_pdf,
    build_note_data_file,
)
from src.utils.fiscal_keys import decode

_NFSE_BH = "31062002228203865000174000000000002426013942565090"


def test_gera_pdf_de_cadastro(tmp_path):
    company = CompanyData(
        cnpj="28203865000174",
        razao_social="EMPRESA TESTE LTDA",
        situacao_cadastral="ATIVA",
        municipio="Belo Horizonte",
        uf="MG",
        atividade_principal="Serviços",
        fonte="ReceitaWS",
    )
    pdf = build_company_registration_pdf(company, tmp_path)
    assert pdf.exists()
    assert pdf.suffix == ".pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert "28203865000174" in pdf.name


def test_gera_json_da_nota(tmp_path):
    chave = decode(_NFSE_BH)
    out = build_note_data_file(chave, tmp_path, cnpj_confere="OK")
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["tipo_documento"] == "NFSE_NACIONAL"
    assert data["cnpj_emitente"] == "28203865000174"
    assert data["numero"] == 24
    assert data["competencia"] == "2026-01"
    assert data["cnpj_emitente_confere_fornecedor"] == "OK"
