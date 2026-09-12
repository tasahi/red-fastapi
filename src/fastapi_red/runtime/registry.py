""" Node Registry for Node-RED in Python.

Mirrors the structure and behavior of @node-red/registry/lib/registry.js:
- Loads node module sets and templates
- Provides getNodeList, getAllNodeConfigs, getNodeIcons, getNodeConfig
"""

from pathlib import Path
from typing import Dict, List, Optional
from fastapi_red.config import settings


# In-memory registry data structures matching @node-red/registry
module_configs: Dict[str, dict] = {}
node_list: List[str] = []
node_type_to_id: Dict[str, str] = {}
node_config_cache: Dict[str, str] = {}
icon_paths: Dict[str, List[Path]] = {}


def filter_node_info(n: dict) -> dict:
    """ Filters node information to the standard subset sent to editor clients,
    matching filterNodeInfo() in @node-red/registry/lib/registry.js.
    """
    r = {
        "id": n.get("id", f"{n.get('module', '')}/{n.get('name', '')}"),
        "name": n.get("name"),
        "types": n.get("types", []),
        "enabled": n.get("enabled", True),
        "local": n.get("local", False),
        "user": n.get("user", False),
        "module": n.get("module", "node-red"),
    }
    if "err" in n:
        r["err"] = n["err"]
    return r


def register_node_set(module_name: str, set_name: str, types: List[str], html_path: Path, enabled: bool = True):
    """ Registers a node set into the module registry,
    matching addModule() and registerType() in @node-red/registry.
    """
    if module_name not in module_configs:
        module_configs[module_name] = {
            "name": module_name,
            "version": settings.version,
            "local": False,
            "user": False,
            "nodes": {},
            "icons": []
        }

    set_id = f"{module_name}/{set_name}"

    # Prefer pre-compiled modular chunk from dist/nodes if available
    effective_html = html_path
    if settings.nodes_dist_dir.exists():
        try:
            rel = html_path.relative_to(settings.nodes_dir)
            dist_candidate = settings.nodes_dist_dir / rel
            if dist_candidate.is_file():
                effective_html = dist_candidate
        except ValueError:
            pass

    node_entry = {
        "id": set_id,
        "name": set_name,
        "types": types,
        "enabled": enabled,
        "module": module_name,
        "html_path": effective_html
    }

    module_configs[module_name]["nodes"][set_name] = node_entry
    if set_id not in node_list:
        node_list.append(set_id)

    for t in types:
        node_type_to_id[t] = set_id

    # Clear config cache on registry change
    node_config_cache.clear()


def get_node_list(filter_fn=None) -> List[dict]:
    """ Returns the list of available node sets and their types,
    matching getNodeList() in @node-red/registry/lib/registry.js.
    """
    results: List[dict] = []
    for module_name, mod_info in module_configs.items():
        nodes = mod_info.get("nodes", {})
        for node_name, node_entry in nodes.items():
            info = filter_node_info(node_entry)
            info["version"] = mod_info.get("version", settings.version)
            if not filter_fn or filter_fn(node_entry):
                results.append(info)
    return results


def get_all_node_configs(lang: str = "en-US") -> str:
    """ Concatenates all registered node HTML templates into a single string
    separated by <!-- --- [red-module:id] --- --> markers, matching
    getAllNodeConfigs() in @node-red/registry/lib/registry.js.
    """
    if lang in node_config_cache:
        return node_config_cache[lang]

    parts: List[str] = []
    for set_id in node_list:
        module_name, set_name = set_id.split("/", 1)
        mod = module_configs.get(module_name)
        if not mod:
            continue
        config = mod.get("nodes", {}).get(set_name)
        if config and config.get("enabled", True) and "html_path" in config:
            html_file: Path = config["html_path"]
            if html_file.is_file():
                try:
                    content = html_file.read_text(encoding="utf-8")
                    parts.append(f"\n<!-- --- [red-module:{set_id}] --- -->\n")
                    parts.append(content)
                except Exception:
                    pass

    rendered = "".join(parts)
    node_config_cache[lang] = rendered
    return rendered


def get_node_config(set_id: str, lang: str = "en-US") -> Optional[str]:
    """ Gets the HTML config template for a single node set,
    matching getNodeConfig() in @node-red/registry/lib/registry.js.
    """
    if "/" not in set_id:
        return None
    module_name, set_name = set_id.split("/", 1)
    mod = module_configs.get(module_name)
    if not mod:
        return None
    config = mod.get("nodes", {}).get(set_name)
    if config and "html_path" in config:
        html_file: Path = config["html_path"]
        if html_file.is_file():
            return html_file.read_text(encoding="utf-8")
    return None


def get_node_icons() -> Dict[str, List[str]]:
    """ Returns the dictionary of available icons grouped by module,
    matching getNodeIcons() in @node-red/registry/lib/registry.js.
    """
    icons: List[str] = []
    if settings.icons_dir.is_dir():
        for f in settings.icons_dir.iterdir():
            if f.is_file() and f.suffix.lower() in [".svg", ".png"]:
                icons.append(f.name)
    return {"node-red": sorted(icons)}


def get_node_icon_path(module_name: str, icon_name: str) -> Optional[Path]:
    """ Resolves the filesystem path for a specific icon,
    matching getNodeIconPath() in @node-red/registry/lib/registry.js.
    """
    icon_file = settings.icons_dir / icon_name
    if icon_file.is_file():
        return icon_file
    default_icon = settings.icons_dir / "arrow-in.svg"
    return default_icon if default_icon.is_file() else None


def load_core_nodes():
    """ Discovers and registers built-in core nodes.
    """
    nodes_root = settings.nodes_dir / "core"

    # 1. Common: inject, debug, comment, catch, status, complete
    common_dir = nodes_root / "common"
    inject_html = common_dir / "20-inject.html"
    if inject_html.is_file():
        register_node_set("node-red", "inject", ["inject"], inject_html)

    debug_html = common_dir / "21-debug.html"
    if debug_html.is_file():
        register_node_set("node-red", "debug", ["debug"], debug_html)

    comment_html = common_dir / "90-comment.html"
    if comment_html.is_file():
        register_node_set("node-red", "comment", ["comment"], comment_html)

    catch_html = common_dir / "25-catch.html"
    if catch_html.is_file():
        register_node_set("node-red", "catch", ["catch"], catch_html)

    status_html = common_dir / "25-status.html"
    if status_html.is_file():
        register_node_set("node-red", "status", ["status"], status_html)

    complete_html = common_dir / "24-complete.html"
    if complete_html.is_file():
        register_node_set("node-red", "complete", ["complete"], complete_html)

    link_html = common_dir / "60-link.html"
    if link_html.is_file():
        register_node_set("node-red", "link", ["link in", "link out", "link call"], link_html)


    # 2. Function: function, switch, change, range, delay, trigger
    function_dir = nodes_root / "function"
    function_html = function_dir / "10-function.html"
    if function_html.is_file():
        register_node_set("node-red", "function", ["function"], function_html)

    switch_html = function_dir / "10-switch.html"
    if switch_html.is_file():
        register_node_set("node-red", "switch", ["switch"], switch_html)

    change_html = function_dir / "15-change.html"
    if change_html.is_file():
        register_node_set("node-red", "change", ["change"], change_html)

    range_html = function_dir / "16-range.html"
    if range_html.is_file():
        register_node_set("node-red", "range", ["range"], range_html)

    delay_html = function_dir / "89-delay.html"
    if delay_html.is_file():
        register_node_set("node-red", "delay", ["delay"], delay_html)

    trigger_html = function_dir / "89-trigger.html"
    if trigger_html.is_file():
        register_node_set("node-red", "trigger", ["trigger"], trigger_html)

    # 3. Sequence: split, join, sort, batch
    sequence_dir = nodes_root / "sequence"
    split_html = sequence_dir / "17-split.html"
    if split_html.is_file():
        register_node_set("node-red", "split", ["split", "join"], split_html)

    sort_html = sequence_dir / "18-sort.html"
    if sort_html.is_file():
        register_node_set("node-red", "sort", ["sort"], sort_html)

    batch_html = sequence_dir / "19-batch.html"
    if batch_html.is_file():
        register_node_set("node-red", "batch", ["batch"], batch_html)

    # 4. Network: http in, http response, http request
    network_dir = nodes_root / "network"
    httpin_html = network_dir / "21-httpin.html"
    if httpin_html.is_file():
        register_node_set("node-red", "rbe", ["http in", "http response"], httpin_html)

    httprequest_html = network_dir / "21-httprequest.html"
    if httprequest_html.is_file():
        register_node_set("node-red", "httprequest", ["http request"], httprequest_html)

    mqtt_html = network_dir / "10-mqtt.html"
    if mqtt_html.is_file():
        register_node_set("node-red", "mqtt", ["mqtt in", "mqtt out", "mqtt-broker"], mqtt_html)

    websocket_html = network_dir / "22-websocket.html"
    if websocket_html.is_file():
        register_node_set("node-red", "websocket", ["websocket in", "websocket out", "websocket-listener", "websocket-client"], websocket_html)

    tcpin_html = network_dir / "31-tcpin.html"
    if tcpin_html.is_file():
        register_node_set("node-red", "tcpin", ["tcp in", "tcp out", "tcp request"], tcpin_html)

    udp_html = network_dir / "32-udp.html"
    if udp_html.is_file():
        register_node_set("node-red", "udp", ["udp in", "udp out"], udp_html)

    # 5. Storage: file, file in, watch
    storage_dir = nodes_root / "storage"
    file_html = storage_dir / "10-file.html"
    if file_html.is_file():
        register_node_set("node-red", "file", ["file", "file in"], file_html)

    # 6. Parsers: json, csv, xml, yaml, html
    parsers_dir = nodes_root / "parsers"
    json_html = parsers_dir / "70-JSON.html"
    if json_html.is_file():
        register_node_set("node-red", "json", ["json"], json_html)

    csv_html = parsers_dir / "70-CSV.html"
    if csv_html.is_file():
        register_node_set("node-red", "csv", ["csv"], csv_html)

    xml_html = parsers_dir / "70-XML.html"
    if xml_html.is_file():
        register_node_set("node-red", "xml", ["xml"], xml_html)

    yaml_html = parsers_dir / "70-YAML.html"
    if yaml_html.is_file():
        register_node_set("node-red", "yaml", ["yaml"], yaml_html)

    html_html = parsers_dir / "70-HTML.html"
    if html_html.is_file():
        register_node_set("node-red", "html", ["html"], html_html)
