""" fastapi-red: Configuration settings.
"""

from pathlib import Path
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DIST_DIR = BASE_DIR / "dist"
STATIC_DIR = DIST_DIR if DIST_DIR.exists() and (DIST_DIR / "index.html").exists() else BASE_DIR / "static"
LOCALES_DIR = STATIC_DIR / "locales"
NODES_DIR = BASE_DIR / "nodes"
NODES_DIST_DIR = DIST_DIR / "nodes"
ICONS_DIR = STATIC_DIR / "icons"
USER_DIR = BASE_DIR / "storage"
FLOWS_FILE = USER_DIR / "flows.json"
CREDENTIALS_FILE = USER_DIR / "flows_cred.json"


class Settings(BaseSettings):
    """ Application settings and directory paths for fastapi-red.
    """

    app_name: str = "fastapi-red"
    version: str = "4.0.8"
    host: str = "127.0.0.1"
    port: int = 8000
    http_node_root: str = "/"
    disable_editor: bool = False

    # Path settings
    base_dir: Path = BASE_DIR
    dist_dir: Path = DIST_DIR
    static_dir: Path = STATIC_DIR
    locales_dir: Path = LOCALES_DIR
    nodes_dir: Path = NODES_DIR
    nodes_dist_dir: Path = NODES_DIST_DIR
    icons_dir: Path = ICONS_DIR
    user_dir: Path = USER_DIR
    flows_file: Path = FLOWS_FILE
    credentials_file: Path = CREDENTIALS_FILE


settings = Settings()
