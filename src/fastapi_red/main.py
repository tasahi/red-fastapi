""" FastAPI-Red Main Application Entrypoint.

Initialises the FastAPI server, mounts editor and admin routers,
and loads the core node library and flow runtime.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi_red.config import settings
from fastapi_red.api.settings import router as settings_router
from fastapi_red.api.locales import router as locales_router
from fastapi_red.api.nodes import router as nodes_router
from fastapi_red.api.flows import router as flows_router
from fastapi_red.api.core import router as core_router
from fastapi_red.api.comms import router as comms_router
from fastapi_red.api.node_actions import router as node_actions_router
from fastapi_red.api.http_in import router as http_in_router
from fastapi_red.runtime import nodes as runtime_nodes
from fastapi_red.runtime import flows as runtime_flows
from fastapi_red.runtime import comms as runtime_comms


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ Application startup and shutdown lifecycle management,
    matching runtime.init() and runtime.start() in Node-RED.
    """
    # Startup: Load core node types into registry, initialize flows and comms
    runtime_nodes.init()
    runtime_flows.init()
    runtime_comms.init()
    # Start flow engine execution
    await runtime_flows.start_flows()
    yield
    # Shutdown logic
    await runtime_flows.stop_flows()


app = FastAPI(
    title="fastapi-red",
    description="Python FastAPI backend hosting the Node-RED visual editor",
    version=settings.version,
    lifespan=lifespan
)

# 1. Mount API Routers
app.include_router(settings_router)
app.include_router(locales_router)
app.include_router(nodes_router)
app.include_router(flows_router)
app.include_router(core_router)
app.include_router(comms_router)
app.include_router(node_actions_router)
app.include_router(http_in_router)



# 2. Editor Home / Entrypoint
@app.get("/", response_class=FileResponse)
async def get_editor_root():
    """ Serves the main Node-RED editor HTML.
    """
    index_file = settings.static_dir / "index.html"
    return FileResponse(index_file)


# 3. Mount Static Assets
# Stock editor resources: /red/*, /vendor/*, /locales/*, /types/*
if settings.static_dir.exists():
    app.mount("/", StaticFiles(directory=str(settings.static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_red.main:app", host=settings.host, port=settings.port, reload=True)
