from __future__ import annotations

import unittest

from mcp import Client

from review_mcp.config import Settings
from review_mcp.server import build_mcp_server, build_service

# Build from explicit CSV settings so tests never depend on .env contents.
_TEST_SETTINGS = Settings(
    data_backend="csv",
    csv_data_glob="data/preprocessed_reviews_*.csv",
    database_url=None,
    review_table="preprocessed_reviews",
    max_analysis_rows=5000,
    mcp_auth_token=None,
    mcp_host="127.0.0.1",
    mcp_port=8000,
    allowed_hosts=("localhost:*",),
    allowed_origins=(),
)
mcp = build_mcp_server(build_service(_TEST_SETTINGS))


class McpContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_discoverable_and_callable(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            self.assertEqual(
                names,
                {
                    "list_review_sources",
                    "get_latest_reviews",
                    "search_reviews",
                    "aggregate_review_stats",
                    "get_top_review_keywords",
                },
            )
            search_tool = next(
                tool for tool in tools.tools if tool.name == "search_reviews"
            )
            limit_schema = search_tool.input_schema["properties"]["limit"]
            self.assertEqual(limit_schema["minimum"], 1)
            self.assertEqual(limit_schema["maximum"], 100)
            self.assertIsNotNone(search_tool.output_schema)
            result = await client.call_tool(
                "get_latest_reviews", {"site": "kakao", "limit": 2}
            )
            self.assertFalse(result.is_error)
            self.assertIsNotNone(result.structured_content)


if __name__ == "__main__":
    unittest.main()
