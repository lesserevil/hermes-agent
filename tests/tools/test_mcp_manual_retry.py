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
    with mcp_tool._lock:
        mcp_tool._server_connect_failures[server_name] = 2
        mcp_tool._server_connect_retry_after[server_name] = 456.0

    status = mcp_tool.retry_mcp_server(server_name)

    assert status == {"name": server_name, "status": "configured"}
    assert server_name not in mcp_tool._server_rate_limit_until
    assert server_name not in mcp_tool._server_connect_failures
    assert server_name not in mcp_tool._server_connect_retry_after


@pytest.mark.no_isolate
def test_retry_mcp_server_forces_dormant_lazy_connector_eager(monkeypatch):
    from tools import mcp_tool

    server_name = "dashboard-oauth-lazy"
    config = {"url": "https://mcp.example.test", "auth": "oauth"}
    monkeypatch.setattr(mcp_tool, "_load_mcp_config", lambda: {server_name: config})
    observed = []
    monkeypatch.setattr(
        mcp_tool, "register_mcp_servers", lambda servers: observed.append(servers)
    )
    monkeypatch.setattr(
        mcp_tool,
        "get_mcp_status",
        lambda: [{"name": server_name, "status": "configured"}],
    )
    monkeypatch.setattr("tools.registry.registry.deregister", lambda name: observed.append(name))

    with mcp_tool._lock:
        mcp_tool._servers.pop(server_name, None)
        mcp_tool._server_connecting.add(server_name)
        mcp_tool._lazy_server_configs[server_name] = dict(config)
        mcp_tool._lazy_server_fingerprints[server_name] = "fingerprint"
        mcp_tool._lazy_server_tool_names[server_name] = ["mcp__dashboard_oauth_lazy__ping"]

    status = mcp_tool.retry_mcp_server(server_name)

    assert status == {"name": server_name, "status": "configured"}
    assert observed == ["mcp__dashboard_oauth_lazy__ping", {server_name: config}]
    assert server_name not in mcp_tool._server_connecting
    assert server_name not in mcp_tool._lazy_server_configs
    assert server_name not in mcp_tool._lazy_server_fingerprints
    assert server_name not in mcp_tool._lazy_server_tool_names


@pytest.mark.no_isolate
def test_status_reports_active_oauth_handoff(monkeypatch, tmp_path):
    from tools import mcp_tool
    from tools.mcp_oauth_manager import get_manager, _ProviderEntry

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(mcp_tool, "_load_mcp_config", lambda: {
        "outlook": {"url": "https://example.test/mcp", "auth": "oauth"}
    })
    manager = get_manager()
    key = manager._key("outlook")
    manager._entries[key] = _ProviderEntry(
        server_url="https://example.test/mcp",
        oauth_config={},
        authorization_url="https://login.example.test/oauth?state=abc",
    )
    try:
        status = mcp_tool.get_mcp_status()[0]
        assert status["status"] == "needs_auth"
        assert status["authorization_url"].startswith(
            "https://login.example.test/"
        )
    finally:
        manager._entries.pop(key, None)
