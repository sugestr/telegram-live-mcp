"""MCP stdio transport. Discovery works before sign-in; calls fail clearly."""
import json
import os
import sys

from .mcp_telegram import Reader, SERVER_INSTRUCTIONS, TOOLS


def respond(message_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": message_id}
    payload["error" if error is not None else "result"] = error if error is not None else result
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main():
    os.umask(0o077)
    reader = None
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request must be an object")
        except (ValueError, TypeError):
            respond(None, error={"code": -32700, "message": "Invalid JSON request"})
            continue
        mid, method = req.get("id"), req.get("method")
        if method == "initialize":
            respond(mid, {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "telegram-live", "version": "0.1.0"},
                "instructions": SERVER_INSTRUCTIONS,
            })
        elif method == "tools/list":
            tools = [dict(t, annotations={"readOnlyHint": True, "destructiveHint": False,
                                         "openWorldHint": True}) for t in TOOLS]
            respond(mid, {"tools": tools})
        elif method == "ping":
            respond(mid, {})
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            if name not in {t["name"] for t in TOOLS}:
                respond(mid, error={"code": -32601, "message": "Unknown tool"})
                continue
            try:
                if reader is None:
                    reader = Reader()
                args = params.get("arguments") or {}
                if not isinstance(args, dict):
                    raise ValueError("arguments must be an object")
                result = getattr(reader, name)(**args)
                respond(mid, {"content": [{"type": "text", "text": result}]})
            except Exception as exc:
                respond(mid, {"content": [{"type": "text", "text": "Ошибка запроса: %s" % exc}],
                              "isError": True})
        elif mid is not None:
            respond(mid, error={"code": -32601, "message": "Unsupported method"})
