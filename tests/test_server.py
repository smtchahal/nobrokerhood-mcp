import pytest
from mcp.server.fastmcp import FastMCP

from nobrokerhood.server import _TOOLS, build_server


@pytest.mark.asyncio
async def test_build_server_registers_all_tools():
    mcp = build_server()
    assert isinstance(mcp, FastMCP)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {fn.__name__ for fn in _TOOLS}
