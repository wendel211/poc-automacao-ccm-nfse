"""
Geração de artefatos baixáveis a partir dos dados extraídos.

Como os portais municipais não permitem baixar o cadastro nem o PDF da nota sem
autenticação, este módulo materializa os dados que o pipeline conseguiu obter de
fontes públicas em arquivos reais no disco:

  - Comprovante de Cadastro (PDF): a partir do cadastro federal da empresa
    (Receita), entregue como documento legível — o equivalente público ao
    "cadastro municipal" que o portal não libera.
  - Dados da Nota (JSON): os campos decodificados e validados da chave fiscal
    (município, emitente, número, série, competência, DV), como artefato
    estruturado da nota.

Ambos carregam um aviso de procedência para não serem confundidos com o
documento oficial emitido pela prefeitura.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

if TYPE_CHECKING:
    from src.services.cnpj_lookup import CompanyData
    from src.utils.fiscal_keys import ChaveFiscal

_AZUL = HexColor("#1F4E79")
_CINZA = HexColor("#595959")


def build_company_registration_pdf(company: "CompanyData", dest_dir: Path) -> Path:
    """Gera comprovante_cadastro_<cnpj>.pdf com os dados cadastrais da empresa."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"comprovante_cadastro_{company.cnpj}.pdf"

    c = canvas.Canvas(str(out), pagesize=A4)
    w, h = A4
    y = h - 2.5 * cm

    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "Comprovante de Cadastro da Empresa")
    y -= 0.7 * cm
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, y, f"Dados públicos da Receita Federal via {company.fonte or 'API pública'}")
    y -= 0.4 * cm
    c.line(2 * cm, y, w - 2 * cm, y)
    y -= 1.0 * cm

    campos = [
        ("CNPJ", company.cnpj),
        ("Razão Social", company.razao_social),
        ("Nome Fantasia", company.nome_fantasia),
        ("Situação Cadastral", company.situacao_cadastral),
        ("Natureza Jurídica", company.natureza_juridica),
        ("Atividade Principal", company.atividade_principal),
        ("Município / UF", _join(company.municipio, company.uf)),
        ("Data de Abertura", company.data_abertura),
    ]
    for rotulo, valor in campos:
        if not valor:
            continue
        c.setFillColor(_AZUL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(2 * cm, y, f"{rotulo}:")
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica", 10)
        for linha in _wrap(str(valor), 78):
            c.drawString(6 * cm, y, linha)
            y -= 0.55 * cm
        y -= 0.1 * cm

    y -= 0.5 * cm
    c.setFillColor(_CINZA)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        2 * cm, 2 * cm,
        "Documento gerado pela automação a partir de dados públicos. Não substitui "
        "a Inscrição Municipal (CCM) emitida pela prefeitura.",
    )
    c.save()
    logger.info("Comprovante de cadastro gerado: {}", out.name)
    return out


def build_note_data_file(chave: "ChaveFiscal", dest_dir: Path, cnpj_confere: str | None) -> Path:
    """Salva dados_nota_<n>.json com os campos decodificados e validados da chave."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    nome = f"dados_nota_{(str(chave.numero) if chave.numero is not None else chave.digitos[:12]) or 'na'}.json"
    out = dest_dir / nome

    payload = {
        "tipo_documento": chave.tipo.value,
        "descricao": chave.descricao,
        "chave_acesso": chave.digitos,
        "municipio_ou_uf": chave.municipio or chave.uf,
        "cnpj_emitente": chave.cnpj_emitente,
        "cnpj_emitente_confere_fornecedor": cnpj_confere,
        "modelo": chave.modelo,
        "serie": chave.serie,
        "numero": chave.numero,
        "competencia": chave.competencia,
        "digito_verificador_valido": chave.dv_valido,
        "_obs": "Dados extraídos e validados da chave fiscal. Não substitui o DANFSe oficial.",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Dados da nota salvos: {}", out.name)
    return out


def _join(a: str | None, b: str | None) -> str | None:
    if a and b:
        return f"{a} / {b}"
    return a or b


def _wrap(text: str, width: int) -> list[str]:
    palavras = text.split()
    linhas, atual = [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > width:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    return linhas or [text]
