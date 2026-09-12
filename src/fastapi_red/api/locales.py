""" Locales API router: GET /locales/{namespace}

Mirrors @node-red/editor-api/lib/editor/locales.js:
- get (loads language catalog for editor, infotips, jsonata, etc.)
"""

import json
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi_red.config import settings


router = APIRouter()


@router.get("/locales/{namespace:path}")
async def get_locales(namespace: str, lng: str = Query(default="en-US")):
    """ Returns the i18n translation catalog for the requested namespace,
    matching get in @node-red/editor-api/lib/editor/locales.js.
    """
    # Normalize namespace (e.g. editor.json -> editor)
    ns = namespace.removesuffix(".json").strip("/")

    # Try exact language first, fallback to en-US
    candidates = [lng]
    if "-" in lng:
        candidates.append(lng.split("-")[0])
    if "en-US" not in candidates:
        candidates.append("en-US")

    for lang in candidates:
        lang_dir = settings.locales_dir / lang
        if not lang_dir.is_dir():
            # Match case-insensitively (e.g., pt-br vs pt-BR)
            for sub in settings.locales_dir.iterdir():
                if sub.is_dir() and sub.name.lower() == lang.lower():
                    lang_dir = sub
                    break

        file_path = lang_dir / f"{ns}.json"
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
            except Exception:
                pass

    return {}
