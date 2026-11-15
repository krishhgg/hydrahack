from hydrahack.data import Api
from hydrahack.mcp import handle, tool_schema

TEXT = (
    "category_name:Food, tool_name:Cocktail DB, api_name:Recipe, api_description:Get a recipe, "
    'required_params: [{"name": "id", "type": "STRING", "description": "cocktail id"}], '
    'optional_params: [{"name": "limit", "type": "NUMBER", "description": ""}], '
    'return_schema: {"id": "str"}'
)
API = Api(7, "Food", "Cocktail DB", "Recipe", "Get a recipe", TEXT)


def fake_find(task, k):
    return {"tools": [tool_schema(API)], "k": k}


def fake_report(task, used, offered):
    return {"task": task, "used": used, "offered": offered}


def call(method, params=None, msg_id=1):
    return handle(
        {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        fake_find,
        fake_report,
    )


def test_tool_schema_parses_params():
    s = tool_schema(API)
    assert s["inputSchema"]["required"] == ["id"]
    assert s["inputSchema"]["properties"]["limit"]["type"] == "number"


def test_initialize_and_list():
    init = call("initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert "tools" in init["capabilities"]
    names = [t["name"] for t in call("tools/list")["result"]["tools"]]
    assert names == ["find_tools", "report_run"]


def test_find_tools_and_report_run():
    res = call("tools/call", {"name": "find_tools", "arguments": {"task": "a cocktail", "k": 50}})
    assert res["result"]["structuredContent"]["k"] == 20
    res = call("tools/call", {"name": "report_run", "arguments": {"task": "x y z", "used": [7]}})
    assert res["result"]["structuredContent"]["used"] == [7]


def test_errors_and_notifications():
    assert call("tools/call", {"name": "find_tools", "arguments": {}})["error"]["code"] == -32602
    assert call("nope")["error"]["code"] == -32601
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert handle(note, fake_find, fake_report) is None


def test_endpoint_caps_body_and_batch():
    from fastapi.testclient import TestClient

    from hydrahack.api import MCP_MAX_BATCH, MCP_MAX_BYTES, app

    client = TestClient(app)
    big = client.post("/mcp", content=b" " * (MCP_MAX_BYTES + 1))
    assert big.status_code == 413
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    batch = client.post("/mcp", json=[ping] * (MCP_MAX_BATCH + 1))
    assert batch.status_code == 400
    assert batch.json()["error"]["code"] == -32600
    assert (
        client.post("/mcp", json=[ping, ping]).json()
        == [{"jsonrpc": "2.0", "id": 1, "result": {}}] * 2
    )
