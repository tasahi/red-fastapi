""" Nodes API router.

Mirrors @node-red/editor-api/lib/admin/nodes.js:
- GET /nodes (application/json -> getNodeList; text/html -> getNodeConfigs)
- GET /nodes/messages (i18n node catalog)
- GET /nodes/{module}/{set}
- GET /icons
- GET /icons/{module}/{icon}
"""

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from red_fastapi.runtime import nodes as runtime_nodes


router = APIRouter()


@router.get("/nodes")
async def get_all_nodes(request: Request, accept: str = Header(default="")):
    """ Returns the node list or node HTML configurations depending on Accept header,
    matching getAll in @node-red/editor-api/lib/admin/nodes.js.
    """
    accept_header = accept or request.headers.get("accept", "")

    if "application/json" in accept_header:
        # Returns JSON list of installed node sets
        node_list = runtime_nodes.get_node_list()
        return node_list

    # Returns the concatenated HTML templates for all enabled nodes
    lang = request.headers.get("accept-language", "en-US")
    if "," in lang:
        lang = lang.split(",")[0].strip()
    html_configs = runtime_nodes.get_node_configs(lang=lang)
    return Response(content=html_configs, media_type="text/html")


@router.get("/nodes/messages")
async def get_module_catalogs(lng: str = Query(default="en-US")):
    """ Returns i18n catalogs for all node sets,
    matching getModuleCatalogs in @node-red/editor-api/lib/admin/nodes.js.
    """
    return runtime_nodes.get_module_catalogs(lang=lng)


@router.get("/nodes/{module_name}/{set_name}/messages")
async def get_module_catalog(module_name: str, set_name: str, lng: str = Query(default="en-US")):
    """ Returns i18n catalog for a specific node set,
    matching getModuleCatalog in @node-red/editor-api/lib/admin/nodes.js.
    """
    return runtime_nodes.get_module_catalog(module=module_name, lang=lng)


@router.get("/nodes/{module_name}/{set_name}")
async def get_node_set(module_name: str, set_name: str, accept: str = Header(default="")):
    """ Returns single node set info or HTML configuration,
    matching getSet in @node-red/editor-api/lib/admin/nodes.js.
    """
    set_id = f"{module_name}/{set_name}"
    if "application/json" in accept:
        all_nodes = runtime_nodes.get_node_list()
        for n in all_nodes:
            if n.get("id") == set_id:
                return n
        return Response(status_code=404)

    config = runtime_nodes.get_node_config(set_id)
    if config:
        return Response(content=config, media_type="text/html")
    return Response(status_code=404)


@router.get("/icons")
async def get_icons():
    """ Returns available node icon list grouped by module,
    matching getIcons in @node-red/editor-api/lib/admin/nodes.js.
    """
    return runtime_nodes.get_icon_list()


@router.get("/icons/{module_name}/{icon_name}")
@router.get("/icons/{scope}/{module_name}/{icon_name}")
async def get_icon(module_name: str, icon_name: str, scope: str = ""):
    """ Serves a specific node icon file,
    matching ui.icon in @node-red/editor-api/lib/editor/ui.js.
    """
    icon_path = runtime_nodes.get_node_icon_path(module_name, icon_name)
    if icon_path and icon_path.is_file():
        media_type = "image/svg+xml" if icon_path.suffix == ".svg" else "image/png"
        return FileResponse(icon_path, media_type=media_type)
    return Response(status_code=404)

