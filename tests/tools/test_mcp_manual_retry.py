"""Regression tests for dashboard-triggered MCP reconnects."""

import pytest


@pytest.mark.no_isolate
def test_retry_mcp_server_clears_throttle_state(monkeypatch):
    from tools import mcp_tool

    server_name = "dashboard-oauth"
    monkeypatch.setattr(
        mcp_tool,
        "_load_mcp_config",
        lambda: {server_name: {"url": "https://mcp.example.test"}},
    )
    monkeypatch.setattr(mcp_tool, "register_mcp_servers", lambda _config: None)
    monkeypatch.setattr(
        mcp_tool,
        "get_mcp_status",
        lambda: [{"name": server_name, "status": "configured"}],
    )

    with mcp_tool._lock:
        mcp_tool._servers.pop(server_name, None)
    with mcp_tool._server_rate_limit_lock:
        mcp_tool._server_rate_limit_until[server_name] = 123.0

    status = mcp_tool.retry_mcp_server(server_name)

    assert status == {"name": server_name, "status": "configured"}
    assert server_name not in mcp_tool._server_rate_limit_until
