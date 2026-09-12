""" Parser nodes implementation for Red-Fastapi.

Mirrors @node-red/nodes/core/parsers/:
- JSONNode: Parses JSON strings to objects, or serializes objects to JSON strings.
- CSVNode: Parses CSV text to rows/arrays of objects, or converts arrays/objects to CSV text.
- YAMLNode: Parses YAML strings to objects or formats objects as YAML text.
- XMLNode: Parses XML strings to Python dicts or builds XML from Python dicts.
- HTMLNode: Extracts elements from HTML using CSS selectors (via regex/parser).
"""

import copy
import csv
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
import yaml
import xmltodict
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.eval import get_property, set_property


logger = logging.getLogger("red_fastapi.nodes.parsers")


class JSONNode(Node):
    """ JSON parser node.
    - If input is str/bytes: parses into dict/list.
    - If input is dict/list: serializes into JSON string.
    - Respects 'action' configuration ('str', 'obj', or '' for toggle).
    - Respects 'pretty' formatting.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property_expr: str = config.get("property", "payload")
        self.action: str = config.get("action", "")
        self.pretty: bool = config.get("pretty", False)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        val = get_property(msg, self.property_expr)
        if val is None:
            await self.send(msg)
            return

        indent = 4 if self.pretty else None

        try:
            if self.action == "str":
                # Force convert to string
                if isinstance(val, (dict, list, int, float, bool)):
                    res = json.dumps(val, indent=indent, default=str)
                else:
                    res = str(val)
                set_property(msg, self.property_expr, res)
            elif self.action == "obj":
                # Force convert to object
                if isinstance(val, bytes):
                    val = val.decode("utf-8")
                if isinstance(val, str):
                    res = json.loads(val)
                    set_property(msg, self.property_expr, res)
            else:
                # Toggle: if string/bytes -> parse to object; if object/list -> stringify
                if isinstance(val, bytes):
                    val = val.decode("utf-8")
                if isinstance(val, str):
                    res = json.loads(val)
                    set_property(msg, self.property_expr, res)
                elif isinstance(val, (dict, list)):
                    res = json.dumps(val, indent=indent, default=str)
                    set_property(msg, self.property_expr, res)

            await self.send(msg)
        except Exception as err:
            await self.error(f"JSON error: {err}", msg)


class CSVNode(Node):
    """ CSV parser node.
    - Converts CSV text strings to dicts or lists.
    - Converts dicts/lists to CSV formatted strings.
    - Supports custom delimiters (comma, tab, semicolon, colon, space, etc.).
    - Supports headers in first row or user-specified columns.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property_expr: str = config.get("property", "payload")
        self.columns: List[str] = [c.strip() for c in config.get("temp", "").split(",") if c.strip()]
        self.separator: str = config.get("sep", ",")
        if not self.separator:
            self.separator = config.get("select-sep", ",") or ","
        self.hdrin: bool = config.get("hdrin", False)
        self.multi: str = config.get("multi", "one")  # "one" row per msg, or "mult" all rows in array
        self.skip: int = int(config.get("skip", 0) or 0)
        self.strings: bool = config.get("strings", True)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        val = get_property(msg, self.property_expr)
        if val is None:
            await self.send(msg)
            return

        try:
            # Check if input is a string -> parse CSV to object/array
            if isinstance(val, (str, bytes)):
                if isinstance(val, bytes):
                    val = val.decode("utf-8")

                lines = val.splitlines()
                if self.skip > 0 and len(lines) > self.skip:
                    lines = lines[self.skip:]

                reader = csv.reader(lines, delimiter=self.separator)
                rows = list(reader)
                if not rows:
                    return

                headers = self.columns
                start_idx = 0
                if self.hdrin and not headers:
                    headers = [h.strip() for h in rows[0]]
                    start_idx = 1
                elif self.hdrin and headers:
                    start_idx = 1

                records: List[Any] = []
                for row in rows[start_idx:]:
                    if not row:
                        continue
                    if headers:
                        record: Dict[str, Any] = {}
                        for i, col_name in enumerate(headers):
                            raw_cell = row[i] if i < len(row) else ""
                            record[col_name] = self._convert_val(raw_cell)
                        records.append(record)
                    else:
                        converted_row = [self._convert_val(cell) for cell in row]
                        records.append(converted_row)

                if self.multi == "mult":
                    # Output single message containing array of rows
                    out_msg = copy.deepcopy(msg)
                    set_property(out_msg, self.property_expr, records)
                    await self.send(out_msg)
                else:
                    # Output one message per row
                    total = len(records)
                    for idx, r in enumerate(records):
                        row_msg = copy.deepcopy(msg)
                        set_property(row_msg, self.property_expr, r)
                        row_msg["parts"] = {
                            "id": msg.get("_msgid", "csv"),
                            "index": idx,
                            "count": total,
                            "type": "array"
                        }
                        await self.send(row_msg)

            # Input is list or dict -> format to CSV text
            elif isinstance(val, (list, dict)):
                output = io.StringIO()
                writer = csv.writer(output, delimiter=self.separator, lineterminator="\n")

                if isinstance(val, dict):
                    # Write dict keys as header if columns not specified, then values
                    cols = self.columns or list(val.keys())
                    writer.writerow(cols)
                    writer.writerow([val.get(k, "") for k in cols])
                elif isinstance(val, list):
                    if val and isinstance(val[0], dict):
                        cols = self.columns or list(val[0].keys())
                        writer.writerow(cols)
                        for item in val:
                            writer.writerow([item.get(k, "") for k in cols])
                    elif val and isinstance(val[0], list):
                        for row in val:
                            writer.writerow(row)
                    else:
                        writer.writerow(val)

                csv_text = output.getvalue()
                out_msg = copy.deepcopy(msg)
                set_property(out_msg, self.property_expr, csv_text)
                await self.send(out_msg)

        except Exception as err:
            await self.error(f"CSV error: {err}", msg)

    def _convert_val(self, s: str) -> Any:
        if self.strings:
            return s
        try:
            if "." in s:
                return float(s)
            return int(s)
        except (ValueError, TypeError):
            return s


class YAMLNode(Node):
    """ YAML parser node.
    - If input is str/bytes: parses YAML into Python dict/list.
    - If input is dict/list: formats into YAML text string.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property_expr: str = config.get("property", "payload")

    async def on_input(self, msg: Dict[str, Any]) -> None:
        val = get_property(msg, self.property_expr)
        if val is None:
            await self.send(msg)
            return

        try:
            if isinstance(val, bytes):
                val = val.decode("utf-8")

            if isinstance(val, str):
                parsed = yaml.safe_load(val)
                set_property(msg, self.property_expr, parsed)
            elif isinstance(val, (dict, list)):
                formatted = yaml.dump(val, sort_keys=False)
                set_property(msg, self.property_expr, formatted)

            await self.send(msg)
        except Exception as err:
            await self.error(f"YAML error: {err}", msg)


class XMLNode(Node):
    """ XML parser node.
    - If input is XML string: parses into Python dictionary using xmltodict.
    - If input is dictionary: converts back to XML string.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property_expr: str = config.get("property", "payload")
        self.attr_prefix: str = config.get("attr", "$") or "@"
        self.cdata_key: str = config.get("chr", "_") or "#text"

    async def on_input(self, msg: Dict[str, Any]) -> None:
        val = get_property(msg, self.property_expr)
        if val is None:
            await self.send(msg)
            return

        try:
            if isinstance(val, bytes):
                val = val.decode("utf-8")

            if isinstance(val, str):
                parsed = xmltodict.parse(
                    val,
                    attr_prefix=self.attr_prefix,
                    cdata_key=self.cdata_key,
                )
                set_property(msg, self.property_expr, dict(parsed))
            elif isinstance(val, dict):
                xml_str = xmltodict.unparse(
                    val,
                    attr_prefix=self.attr_prefix,
                    cdata_key=self.cdata_key,
                    pretty=True,
                )
                set_property(msg, self.property_expr, xml_str)

            await self.send(msg)
        except Exception as err:
            await self.error(f"XML error: {err}", msg)


class HTMLNode(Node):
    """ HTML parser node: Extracts elements matching tag/CSS selector.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property_expr: str = config.get("property", "payload")
        self.tag: str = config.get("tag", "")
        self.ret: str = config.get("ret", "html")  # "html" or "text"
        self.as_array: bool = config.get("as", "single") == "multi"

    async def on_input(self, msg: Dict[str, Any]) -> None:
        val = get_property(msg, self.property_expr)
        if val is None or not isinstance(val, (str, bytes)):
            await self.send(msg)
            return

        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="ignore")

        try:
            # Simple, fast regex-based HTML extractor for common tags
            matches: List[str] = []
            if self.tag:
                tag_name = re.escape(self.tag.split()[0].replace(".", "").replace("#", ""))
                pattern = rf"<{tag_name}[^>]*>(.*?)</{tag_name}>"
                found = re.findall(pattern, val, flags=re.DOTALL | re.IGNORECASE)
                for f in found:
                    if self.ret == "text":
                        # Strip nested tags
                        cleaned = re.sub(r"<[^>]+>", "", f).strip()
                        matches.append(cleaned)
                    else:
                        matches.append(f.strip())

            if self.as_array:
                set_property(msg, self.property_expr, matches)
                await self.send(msg)
            else:
                for idx, m in enumerate(matches):
                    row_msg = copy.deepcopy(msg)
                    set_property(row_msg, self.property_expr, m)
                    row_msg["parts"] = {"id": msg.get("_msgid", "html"), "index": idx, "count": len(matches)}
                    await self.send(row_msg)
        except Exception as err:
            await self.error(f"HTML error: {err}", msg)

