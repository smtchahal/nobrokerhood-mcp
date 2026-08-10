"""Regression guard for silent dependency breakage.

This package moved from mcp<2 (``mcp.server.fastmcp.FastMCP``) to mcp>=2.0
(``mcp.server.mcpserver.MCPServer``) after mcp 2.0.0 removed the former
without warning. A successful ``pip install`` doesn't catch that kind of
break -- only actually importing the module does, and this is the fastest,
most minimal way to do that. Keep it even though ``test_server.py`` already
exercises the same import path via ``build_server()``; a dedicated,
self-documenting test survives refactors that might otherwise drop that
coverage incidentally.
"""


def test_server_module_imports():
    import nobrokerhood.server  # noqa: F401
