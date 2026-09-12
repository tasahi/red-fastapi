""" Runtime settings endpoints.

Mirrors @node-red/editor-api/lib/admin/settings.js:
- GET /settings
- GET /settings/user
- POST /settings/user
"""

from fastapi import APIRouter, Request
from red_fastapi.config import settings


router = APIRouter()

# In-memory user preferences state
user_settings_state = {
    "view": {
        "view-show-grid": True,
        "view-snap-grid": True,
        "view-grid-size": 20,
        "view-node-status": True,
        "view-show-tips": True
    }
}


@router.get("/settings")
async def get_settings():
    """ Returns the runtime settings required by @node-red/editor-client,
    matching runtimeSettings in @node-red/editor-api/lib/admin/settings.js.
    """
    return {
        "httpNodeRoot": settings.http_node_root,
        "version": settings.version,
        "context": {
            "default": "memory",
            "stores": ["memory"]
        },
        "codeEditor": {
            "lib": "monaco",
            "options": {}
        },
        "markdownEditor": {
            "mermaid": {"enabled": True}
        },
        "libraries": [],
        "flowEncryptionType": "disabled",
        "flowFilePretty": True,
        "externalModules": {
            "palette": {
                "allowInstall": False,
                "allowUpload": False,
                "allowList": ["*"],
                "denyList": []
            },
            "modules": {
                "allowInstall": False,
                "allowList": ["*"],
                "denyList": []
            }
        },
        "editorTheme": {
            "page": {
                "title": "Node-RED (FastAPI)",
                "favicon": "favicon.ico"
            },
            "header": {
                "title": "Node-RED (FastAPI)",
                "image": "red/images/node-red-icon.svg"
            },
            "palette": {
                "editable": True
            },
            "projects": {
                "enabled": False
            },
            "tours": True
        }
    }


@router.get("/settings/user")
async def get_user_settings():
    """ Returns the user settings / preferences,
    matching info.userSettings in @node-red/editor-api/lib/editor/settings.js.
    """
    return user_settings_state


@router.post("/settings/user")
async def update_user_settings(request: Request):
    """ Updates the user settings when the editor changes a setting
    (e.g., grid size, sidebar position, display toggles),
    matching info.updateUserSettings in @node-red/editor-api/lib/editor/settings.js.
    """
    try:
        data = await request.json()
        if isinstance(data, dict):
            user_settings_state.update(data)
    except Exception:
        pass
    return {"status": "ok"}
