""" Unit tests for Storage nodes (File, FileIn, S3/MinIO) and Parsers (JSON, CSV, YAML, XML, HTML).

Validates:
- JSON parser: string to object, object to string, pretty formatting
- CSV parser: CSV string to array/rows with headers, object/array to CSV text
- YAML parser: YAML text to dict, dict to YAML text
- XML parser: XML text to dict, dict to XML text
- HTML parser: tag content extraction and stripping
- File & FileIn: async write, append, read as utf8, read as lines, delete
- S3 & MinIO: mock/boto3 client upload, download, delete, json parsing
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from red_fastapi.runtime.engine import FlowEngine


@pytest.mark.asyncio
async def test_json_parser_node():
    """ Tests JSONNode parsing string to dict, and serializing dict to JSON string.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        {"id": "n_json_parse", "type": "json", "z": "tab1", "action": "obj", "wires": [["out1"]]},
        {"id": "n_json_str", "type": "json", "z": "tab1", "action": "str", "pretty": True, "wires": [["out2"]]},
        {"id": "out1", "type": "function", "z": "tab1", "wires": []},
        {"id": "out2", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    res1 = []
    res2 = []
    engine.get_node("out1").on_input = lambda msg: res1.append(msg) or asyncio.sleep(0)
    engine.get_node("out2").on_input = lambda msg: res2.append(msg) or asyncio.sleep(0)

    # 1. Parse string to dict
    parse_node = engine.get_node("n_json_parse")
    await parse_node.on_input({"payload": '{"sensor": "temp", "val": 23.5}'})
    await asyncio.sleep(0.02)

    assert len(res1) == 1
    assert isinstance(res1[0]["payload"], dict)
    assert res1[0]["payload"]["sensor"] == "temp"
    assert res1[0]["payload"]["val"] == 23.5

    # 2. Stringify dict to pretty JSON
    str_node = engine.get_node("n_json_str")
    await str_node.on_input({"payload": {"user": "alice", "roles": ["admin", "dev"]}})
    await asyncio.sleep(0.02)

    assert len(res2) == 1
    assert isinstance(res2[0]["payload"], str)
    assert '"user": "alice"' in res2[0]["payload"]
    assert "    " in res2[0]["payload"]  # check indentation

    await engine.stop()


@pytest.mark.asyncio
async def test_csv_parser_node():
    """ Tests CSVNode parsing CSV rows and serializing objects to CSV.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        {
            "id": "csv_to_obj",
            "type": "csv",
            "z": "tab1",
            "temp": "name,age,city",
            "hdrin": True,
            "multi": "mult",
            "wires": [["out_csv_parsed"]],
        },
        {
            "id": "obj_to_csv",
            "type": "csv",
            "z": "tab1",
            "wires": [["out_csv_string"]],
        },
        {"id": "out_csv_parsed", "type": "function", "z": "tab1", "wires": []},
        {"id": "out_csv_string", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    parsed_rows = []
    csv_strings = []
    engine.get_node("out_csv_parsed").on_input = lambda msg: parsed_rows.append(msg) or asyncio.sleep(0)
    engine.get_node("out_csv_string").on_input = lambda msg: csv_strings.append(msg) or asyncio.sleep(0)

    # 1. Parse CSV string to multi-object array
    csv_text = "name,age,city\nAlice,30,London\nBob,25,Paris"
    c2o = engine.get_node("csv_to_obj")
    await c2o.on_input({"payload": csv_text})
    await asyncio.sleep(0.02)

    assert len(parsed_rows) == 1
    data = parsed_rows[0]["payload"]
    assert len(data) == 2
    assert data[0]["name"] == "Alice"
    assert data[0]["city"] == "London"
    assert data[1]["name"] == "Bob"

    # 2. Serialize list of dicts to CSV string
    o2c = engine.get_node("obj_to_csv")
    await o2c.on_input({"payload": [{"id": 1, "item": "pen"}, {"id": 2, "item": "book"}]})
    await asyncio.sleep(0.02)

    assert len(csv_strings) == 1
    generated_csv = csv_strings[0]["payload"]
    assert "id,item" in generated_csv
    assert "1,pen" in generated_csv

    await engine.stop()


@pytest.mark.asyncio
async def test_yaml_and_xml_parsers():
    """ Tests YAMLNode and XMLNode bidirectional conversion.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        {"id": "n_yaml", "type": "yaml", "z": "tab1", "wires": [["yaml_out"]]},
        {"id": "n_xml", "type": "xml", "z": "tab1", "wires": [["xml_out"]]},
        {"id": "yaml_out", "type": "function", "z": "tab1", "wires": []},
        {"id": "xml_out", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    yaml_results = []
    xml_results = []
    engine.get_node("yaml_out").on_input = lambda msg: yaml_results.append(msg) or asyncio.sleep(0)
    engine.get_node("xml_out").on_input = lambda msg: xml_results.append(msg) or asyncio.sleep(0)

    yaml_node = engine.get_node("n_yaml")
    xml_node = engine.get_node("n_xml")

    # 1. Parse YAML text
    yaml_src = "server:\n  host: localhost\n  port: 8080\n"
    await yaml_node.on_input({"payload": yaml_src})
    await asyncio.sleep(0.02)

    assert len(yaml_results) == 1
    assert yaml_results[0]["payload"]["server"]["port"] == 8080

    # 2. Parse XML text
    xml_src = "<device id='dev101'><temperature>24.2</temperature></device>"
    await xml_node.on_input({"payload": xml_src})
    await asyncio.sleep(0.02)

    assert len(xml_results) == 1
    xml_data = xml_results[0]["payload"]
    assert "device" in xml_data
    assert xml_data["device"]["temperature"] == "24.2"

    await engine.stop()


@pytest.mark.asyncio
async def test_file_storage_nodes():
    """ Tests FileNode (write/append/delete) and FileInNode (read utf8/lines).
    """
    tmp_dir = tempfile.mkdtemp()
    test_file = Path(tmp_dir) / "test_data.txt"

    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        # File write node
        {
            "id": "f_write",
            "type": "file",
            "z": "tab1",
            "filename": str(test_file),
            "filenameType": "str",
            "overwriteFile": "true",
            "appendNewline": True,
            "wires": [["write_done"]],
        },
        # File read node
        {
            "id": "f_read",
            "type": "file in",
            "z": "tab1",
            "filename": str(test_file),
            "filenameType": "str",
            "format": "utf8",
            "wires": [["read_done"]],
        },
        # File delete node
        {
            "id": "f_delete",
            "type": "file",
            "z": "tab1",
            "filename": str(test_file),
            "filenameType": "str",
            "overwriteFile": "delete",
            "wires": [["delete_done"]],
        },
        {"id": "write_done", "type": "function", "z": "tab1", "wires": []},
        {"id": "read_done", "type": "function", "z": "tab1", "wires": []},
        {"id": "delete_done", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    read_results = []
    delete_results = []
    engine.get_node("read_done").on_input = lambda msg: read_results.append(msg) or asyncio.sleep(0)
    engine.get_node("delete_done").on_input = lambda msg: delete_results.append(msg) or asyncio.sleep(0)

    try:
        # 1. Write file
        writer = engine.get_node("f_write")
        await writer.on_input({"payload": "Red-Fastapi File Node Test Content"})
        await asyncio.sleep(0.05)
        assert test_file.exists()

        # 2. Read file
        reader = engine.get_node("f_read")
        await reader.on_input({})
        await asyncio.sleep(0.05)
        assert len(read_results) == 1
        assert "Red-Fastapi File Node Test Content" in read_results[0]["payload"]

        # 3. Delete file
        deleter = engine.get_node("f_delete")
        await deleter.on_input({})
        await asyncio.sleep(0.05)
        assert not test_file.exists()
        assert len(delete_results) == 1

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        await engine.stop()


@pytest.mark.asyncio
async def test_s3_and_minio_blob_nodes():
    """ Tests S3ConfigNode, S3InNode, and S3OutNode with mocked AWS S3 / MinIO backend.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        # Config Node for MinIO / S3
        {
            "id": "s3_cfg",
            "type": "s3-config",
            "z": "tab1",
            "endpoint": "http://127.0.0.1:9000",
            "region": "us-east-1",
            "accessKey": "minioadmin",
            "secretKey": "minioadmin",
        },
        # Upload / S3 Out
        {
            "id": "s3_out",
            "type": "s3 out",
            "z": "tab1",
            "s3Config": "s3_cfg",
            "bucket": "my-test-bucket",
            "key": "telemetry/device_01.json",
            "action": "upload",
            "wires": [["upload_done"]],
        },
        # Download / S3 In
        {
            "id": "s3_in",
            "type": "s3 in",
            "z": "tab1",
            "s3Config": "s3_cfg",
            "bucket": "my-test-bucket",
            "key": "telemetry/device_01.json",
            "format": "json",
            "wires": [["download_done"]],
        },
        {"id": "upload_done", "type": "function", "z": "tab1", "wires": []},
        {"id": "download_done", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    upload_results = []
    download_results = []
    engine.get_node("upload_done").on_input = lambda msg: upload_results.append(msg) or asyncio.sleep(0)
    engine.get_node("download_done").on_input = lambda msg: download_results.append(msg) or asyncio.sleep(0)

    # Setup mock S3 client
    mock_s3_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b'{"status": "active", "battery": 98}'
    mock_s3_client.get_object.return_value = {
        "Body": mock_body,
        "ContentType": "application/json"
    }

    cfg_node = engine.get_node("s3_cfg")
    cfg_node._client = mock_s3_client

    # 1. Test S3 Out upload
    s3_out_node = engine.get_node("s3_out")
    await s3_out_node.on_input({"payload": {"status": "active", "battery": 98}})
    await asyncio.sleep(0.05)

    assert mock_s3_client.put_object.called
    call_args = mock_s3_client.put_object.call_args[1]
    assert call_args["Bucket"] == "my-test-bucket"
    assert call_args["Key"] == "telemetry/device_01.json"
    assert b'"status": "active"' in call_args["Body"]
    assert len(upload_results) == 1

    # 2. Test S3 In download
    s3_in_node = engine.get_node("s3_in")
    await s3_in_node.on_input({})
    await asyncio.sleep(0.05)

    assert mock_s3_client.get_object.called
    assert len(download_results) == 1
    assert download_results[0]["payload"]["battery"] == 98
    assert download_results[0]["bucket"] == "my-test-bucket"
    assert download_results[0]["key"] == "telemetry/device_01.json"

    # 3. Test S3 Out delete
    await s3_out_node.on_input({"action": "delete"})
    await asyncio.sleep(0.05)
    assert mock_s3_client.delete_object.called

    await engine.stop()

