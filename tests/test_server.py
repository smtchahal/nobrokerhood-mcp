import pytest
from mcp.server.mcpserver import MCPServer

from nobrokerhood.server import _TOOLS, build_server


@pytest.mark.asyncio
async def test_build_server_registers_all_tools():
    mcp = build_server()
    assert isinstance(mcp, MCPServer)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {fn.__name__ for fn in _TOOLS}
