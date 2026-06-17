import re
import unicodedata
from pathlib import Path


def slug(text: str) -> str:
    """Converte texto para slug seguro em nome de pasta."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w]+", "_", ascii_str).strip("_").upper()


def ensure_dirs(base: Path, municipio: str, cnpj_raw: str) -> tuple[Path, Path]:
    """
    Cria e retorna:
      - pasta do cadastro:  base/<MUNICIPIO>/<CNPJ>/
      - pasta das notas:    base/<MUNICIPIO>/<CNPJ>/notas/
    """
    from src.utils.cnpj import normalize
    cnpj = normalize(cnpj_raw)
    company_dir = base / slug(municipio) / cnpj
    notes_dir = company_dir / "notas"
    company_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    return company_dir, notes_dir
