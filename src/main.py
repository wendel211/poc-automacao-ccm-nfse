"""CLI de entrada — poc-automacao-ccm-nfse."""
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="POC de automação CCM + Download NFS-e por município")


@app.command()
def run(
    input_file: Path = typer.Argument(..., help="Planilha de entrada (.xlsx)"),
    output_dir: Path = typer.Option(Path("output"), "--output-dir", "-o", help="Pasta de saída"),
    log_level: str = typer.Option("INFO", "--log-level", "-l"),
) -> None:
    """Processa a planilha: consulta CCM, baixa cadastros e notas fiscais."""
    logger.remove()
    logger.add(
        lambda msg: typer.echo(msg, err=False),
        level=log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )
    logger.add(
        output_dir / "logs" / "execution.jsonl",
        level="DEBUG",
        serialize=True,
        rotation="50 MB",
    )

    if not input_file.exists():
        typer.echo(f"Arquivo não encontrado: {input_file}", err=True)
        raise typer.Exit(1)

    from src.pipeline import run as pipeline_run
    result_path = pipeline_run(input_file, output_dir)
    typer.echo(f"\nPlanilha de resultados: {result_path}")


if __name__ == "__main__":
    app()
