""" Core routers for plugins, diagnostics, and theme.

Mirrors corresponding modules in @node-red/editor-api:
- lib/admin/plugins.js
- lib/admin/diagnostics.js
- lib/editor/theme.js
"""

from fastapi import APIRouter, Header, Request, Response


router = APIRouter()


@router.get("/plugins")
async def get_plugins(request: Request, accept: str = Header(default="")):
    """ Returns the list of installed plugins (JSON) or plugin HTML configs (text/html),
    matching getAll and getConfigs in @node-red/editor-api/lib/admin/plugins.js.
    """
    accept_header = accept or request.headers.get("accept", "")
    if "text/html" in accept_header and "application/json" not in accept_header:
        # Return empty HTML for plugin configurations
        return Response(content="", media_type="text/html")
    # Return empty list of installed plugins
    return []


@router.get("/plugins/messages")
async def get_plugins_messages():
    """ Returns plugin i18n catalogs.
    """
    return {}


@router.get("/diagnostics")
async def get_diagnostics():
    """ Returns diagnostic report of the runtime environment.
    """
    return {"runtime": "python-fastapi", "version": "4.0.8"}


@router.get("/theme")
async def get_theme():
    """ Returns theme context object for editor initialization,
    matching theme.app() get('/') in @node-red/editor-api/lib/editor/theme.js.
    """
    return {
        "page": {
            "title": "Node-RED (FastAPI)",
            "favicon": "favicon.ico",
            "tabicon": {
                "icon": "red/images/node-red-icon-black.svg",
                "colour": "#8f0000"
            }
        },
        "header": {
            "title": "Node-RED (FastAPI)",
            "image": "red/images/node-red-icon.svg"
        },
        "themes": []
    }


@router.get("/theme/{theme_path:path}")
async def get_theme_resource(theme_path: str):
    """ Returns custom theme assets (CSS, JS, images) or empty response.
    """
    return Response(content="", media_type="text/css")
