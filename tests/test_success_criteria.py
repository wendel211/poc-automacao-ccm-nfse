from pathlib import Path

from src.models import StatusExecucao
from src.pipeline import _CADASTRO_EXTS, _NOTA_EXTS, _classify_status, _has_file


def test_success_requires_ccm_cadastro_municipal_and_invoice_download():
    status = _classify_status(
        ccm_value="123456",
        cadastro_municipal_ok=True,
        nota_download_ok=True,
    )

    assert status == StatusExecucao.SUCESSO


def test_generated_public_data_is_not_success_criteria():
    status = _classify_status(
        ccm_value=None,
        cadastro_municipal_ok=False,
        nota_download_ok=False,
    )

    assert status == StatusExecucao.ERRO


def test_partial_when_only_one_required_artifact_is_available():
    status = _classify_status(
        ccm_value="123456",
        cadastro_municipal_ok=False,
        nota_download_ok=False,
    )

    assert status == StatusExecucao.PARCIAL


def test_invoice_success_only_accepts_pdf_or_xml(tmp_path: Path):
    screenshot = tmp_path / "nfse.png"
    screenshot.write_bytes(b"png")
    xml = tmp_path / "nfse.xml"
    xml.write_text("<xml />", encoding="utf-8")

    assert _has_file(str(screenshot), _NOTA_EXTS) is False
    assert _has_file(str(xml), _NOTA_EXTS) is True


def test_company_registration_accepts_pdf_xml_or_page_print(tmp_path: Path):
    page_print = tmp_path / "cadastro.png"
    page_print.write_bytes(b"png")
    xml = tmp_path / "cadastro.xml"
    xml.write_text("<cadastro />", encoding="utf-8")
    txt = tmp_path / "cadastro.txt"
    txt.write_text("nao e print nem documento oficial", encoding="utf-8")

    assert _has_file(str(page_print), _CADASTRO_EXTS) is True
    assert _has_file(str(xml), _CADASTRO_EXTS) is True
    assert _has_file(str(txt), _CADASTRO_EXTS) is False
