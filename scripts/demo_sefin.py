"""
Demonstração do caminho oficial de busca na NFS-e Federal (API SEFIN Nacional).

Roda em sequência, pronto para gravar um GIF ou apresentar:

  1. Prova ao vivo de que o portal federal EXIGE certificado ICP-Brasil (mTLS).
  2. Comportamento do cliente SEFIN sem certificado (mensagem clara, sem quebrar).
  3. Comportamento com certificado, se NFSE_CERT_PEM/NFSE_KEY_PEM estiverem setados.

Uso:
    python -m scripts.demo_sefin
    python scripts/demo_sefin.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# stdout em UTF-8 para terminais Windows cp1252 (mesmo padrão do pipeline)
_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
console = Console(file=_stdout, highlight=False)

# Chave NFS-e Nacional real da amostra (Belo Horizonte, nota 24, comp. 2026-01)
_CHAVE = "31062002228203865000174000000000002426013942565090"

_ENDPOINTS = [
    ("ADN Nacional", f"https://adn.nfse.gov.br/contribuinteisn/nfse/{_CHAVE}"),
    ("SEFIN Nacional", f"https://sefin.nfse.gov.br/sefinnacional/nfse/{_CHAVE}"),
]


def passo_1_prova_mtls() -> None:
    console.rule("[bold cyan]1. O portal federal exige certificado ICP-Brasil (mTLS)[/bold cyan]")
    table = Table(show_lines=False, expand=False)
    table.add_column("Endpoint oficial", style="bold")
    table.add_column("HTTP", justify="center")
    table.add_column("Significado")

    for nome, url in _ENDPOINTS:
        try:
            resp = httpx.get(url, timeout=12)
            status = resp.status_code
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]{type(exc).__name__}[/red] ao acessar {nome}")
            continue
        if status == 496:
            signif, cor = "SSL certificate required (mTLS obrigatório)", "yellow"
        elif status == 403:
            signif, cor = "Sem credencial de cliente", "yellow"
        else:
            signif, cor = "—", "white"
        table.add_row(nome, f"[{cor}]{status}[/{cor}]", signif)

    console.print(table)
    console.print(
        "  [dim]Conclusão: o download programático da NFS-e Federal só é possível "
        "com certificado digital (e-CNPJ A1).[/dim]\n"
    )


def passo_2_sem_certificado() -> None:
    console.rule("[bold cyan]2. Cliente SEFIN sem certificado (degrada com elegância)[/bold cyan]")
    from src.services.sefin_nacional import cert_disponivel, fetch_nfse

    console.print(f"  Certificado configurado? [bold]{cert_disponivel()}[/bold]")
    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    result = fetch_nfse(_CHAVE, out)
    console.print(f"  success: [bold]{result.success}[/bold]")
    console.print(Panel(result.error or "—", title="mensagem", border_style="yellow", expand=False))
    console.print()


def passo_3_com_certificado() -> None:
    console.rule("[bold cyan]3. Cliente SEFIN com certificado (download real do XML)[/bold cyan]")
    from src.services.sefin_nacional import cert_disponivel, fetch_nfse

    if not cert_disponivel():
        console.print(
            "  [dim]NFSE_CERT_PEM / NFSE_KEY_PEM não configurados — pulando.[/dim]\n"
            "  [dim]Para baixar o XML real, configure um e-CNPJ A1 (ICP-Brasil):[/dim]"
        )
        console.print(
            "    [green]openssl pkcs12 -in ecnpj.pfx -clcerts -nokeys -out cert.pem[/green]\n"
            "    [green]openssl pkcs12 -in ecnpj.pfx -nocerts -nodes  -out key.pem[/green]\n"
            "    [green]export NFSE_CERT_PEM=cert.pem NFSE_KEY_PEM=key.pem[/green]\n"
        )
        return

    console.print("  Certificado detectado — baixando XML real via SEFIN...")
    result = fetch_nfse(_CHAVE, Path("output"))
    if result.success:
        console.print(f"  [green]XML salvo em:[/green] {result.file_path}")
    else:
        console.print(f"  [red]Falha:[/red] {result.error}")
    console.print()


def main() -> None:
    console.print(
        Panel(
            "[bold]NFS-e Federal — caminho oficial de busca (API SEFIN Nacional + mTLS)[/bold]\n"
            f"Chave de demonstração: {_CHAVE}",
            border_style="cyan",
        )
    )
    passo_1_prova_mtls()
    passo_2_sem_certificado()
    passo_3_com_certificado()
    console.rule("[bold green]Fim da demonstração[/bold green]")


if __name__ == "__main__":
    main()
