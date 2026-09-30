"""Clasificación de archivos locales compartida por los visores."""

from pathlib import Path


TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".css", ".csv", ".go", ".h", ".hpp", ".ini", ".java",
    ".js", ".json", ".jsx", ".md", ".py", ".rs", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".xml", ".yaml", ".yml",
}


def is_text_file(path):
    """Devuelve si la extensión corresponde a un archivo editable de texto."""
    return Path(path).suffix.lower() in TEXT_EXTENSIONS
