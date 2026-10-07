"""Run the independently deployable data MCP service."""

import argparse

import uvicorn

from zhizhi_data_mcp.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Zhizhi data MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    arguments = parser.parse_args()
    uvicorn.run(create_app(), host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
