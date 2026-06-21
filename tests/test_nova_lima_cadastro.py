from src.services import nova_lima_cadastro
from src.services.nova_lima_cadastro import NovaLimaCadastroResult, baixar_cadastro_nova_lima


def test_nova_lima_does_not_fabricate_when_print_capture_fails(tmp_path, monkeypatch):
    """Inscricao confirmada, mas se o print da pagina nao for capturado, NAO inventa arquivo."""
    monkeypatch.setattr(
        nova_lima_cadastro,
        "consultar_inscricao_nova_lima",
        lambda cnpj: NovaLimaCadastroResult(success=True, inscricao="29657884", razao="SALT TECNOLOGIA LTDA."),
    )
    monkeypatch.setattr(nova_lima_cadastro, "_capturar_print_enfs", lambda *a, **k: False)

    result = baixar_cadastro_nova_lima("56422955000191", tmp_path)

    assert result.success is False
    assert result.inscricao == "29657884"
    assert result.file_path is None
    assert "nao foi possivel capturar" in result.error


def test_nova_lima_returns_print_when_captured(tmp_path, monkeypatch):
    """Quando o print oficial da Consulta de Prestadores e capturado, retorna sucesso com o arquivo."""
    monkeypatch.setattr(
        nova_lima_cadastro,
        "consultar_inscricao_nova_lima",
        lambda cnpj: NovaLimaCadastroResult(success=True, inscricao="29657884", razao="SALT TECNOLOGIA LTDA."),
    )

    def _fake_capture(cnpj, inscricao, termo, out):
        out.write_bytes(b"\x89PNG\r\n" + b"0" * 2000)  # simula print salvo
        return True

    monkeypatch.setattr(nova_lima_cadastro, "_capturar_print_enfs", _fake_capture)

    result = baixar_cadastro_nova_lima("56422955000191", tmp_path)

    assert result.success is True
    assert result.inscricao == "29657884"
    assert result.file_path is not None
    assert result.file_path.endswith("cadastro_municipal_nova_lima_enfs_56422955000191.png")


def test_nova_lima_propagates_lookup_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        nova_lima_cadastro,
        "consultar_inscricao_nova_lima",
        lambda cnpj: NovaLimaCadastroResult(success=False, error="Inscricao municipal nao encontrada no e-NFS Nova Lima"),
    )

    result = baixar_cadastro_nova_lima("00000000000000", tmp_path)

    assert result.success is False
    assert result.file_path is None
