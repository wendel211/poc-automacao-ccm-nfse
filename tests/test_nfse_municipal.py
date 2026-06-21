from src.services.nfse_municipal import _validar_nota_exibida


def test_validates_real_nfse_text():
    text = """
    NFS-e - NOTA FISCAL DE SERVIÇOS ELETRÔNICA
    CPF/CNPJ: 90.347.840/0051-87
    Código de Verificação:
    b46a80ef
    """

    assert _validar_nota_exibida(text, "90347840005187", "b46a80ef") is None


def test_rejects_error_page_as_invoice():
    text = "Ocorreu um erro inesperado na aplicação. Tente realizar a operação novamente."

    assert _validar_nota_exibida(text, "09262608001645", "qualquer") == (
        "Portal municipal nao exibiu uma NFS-e valida"
    )
