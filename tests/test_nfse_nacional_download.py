from src.services.nfse_nacional_download import _extract_form_error


def test_extracts_official_nonexistent_invoice_message():
    html = """
    <div class="validation-summary-errors">
      Nota Fiscal de Serviço inexistente.
    </div>
    """

    assert _extract_form_error(html) == "Nota Fiscal de Serviço inexistente"


def test_extract_form_error_returns_none_without_known_message():
    assert _extract_form_error("<html><body>Consulta Pública</body></html>") is None
