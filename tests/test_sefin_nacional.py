"""Testes do cliente SEFIN Nacional (mTLS) — caminho oficial de fetch da NFS-e."""
import httpx
import respx

from src.services import sefin_nacional
from src.services.sefin_nacional import cert_disponivel, fetch_nfse

_CHAVE = "31062002228203865000174000000000002426013942565090"


def test_sem_certificado_retorna_mensagem_clara(tmp_path, monkeypatch):
    monkeypatch.delenv("NFSE_CERT_PEM", raising=False)
    monkeypatch.delenv("NFSE_KEY_PEM", raising=False)
    assert cert_disponivel() is False
    r = fetch_nfse(_CHAVE, tmp_path)
    assert r.success is False
    assert r.cert_configured is False
    assert "ICP-Brasil" in r.error


def test_certificado_inexistente_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.setenv("NFSE_CERT_PEM", str(tmp_path / "nao_existe.pem"))
    monkeypatch.setenv("NFSE_KEY_PEM", str(tmp_path / "nao_existe_key.pem"))
    assert cert_disponivel() is False  # arquivos não existem


@respx.mock
def test_com_certificado_baixa_xml(tmp_path, monkeypatch):
    # Cria arquivos PEM fake só para passar na checagem de existência
    cert = tmp_path / "cert.pem"; cert.write_text("--cert--")
    key = tmp_path / "key.pem"; key.write_text("--key--")
    monkeypatch.setenv("NFSE_CERT_PEM", str(cert))
    monkeypatch.setenv("NFSE_KEY_PEM", str(key))

    # Evita que o httpx tente carregar o PEM falso como certificado real
    monkeypatch.setattr(sefin_nacional.httpx, "Client", _FakeClientFactory(
        httpx.Response(200, content=b"<NFSe><Numero>24</Numero></NFSe>")
    ))

    r = fetch_nfse(_CHAVE, tmp_path)
    assert r.success is True
    assert r.cert_configured is True
    assert r.file_path.endswith(".xml")


class _FakeClientFactory:
    """Substitui httpx.Client por um cliente fake que ignora o cert e devolve a resposta dada."""
    def __init__(self, response: httpx.Response):
        self._response = response

    def __call__(self, *args, **kwargs):
        return _FakeClient(self._response)


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *args, **kwargs):
        return self._response
