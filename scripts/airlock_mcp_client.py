"""Connect to airlock-mcp over streamable HTTP, list its tools, and run check_provenance on the
two demo assets: the clean signed clip (expect PASS, trusted signer) and the Prelinger excerpt
(expect BLOCK, no manifest).

Usage:
  scripts/airlock_mcp_client.py               # the deployed URL
  scripts/airlock_mcp_client.py --local        # http://127.0.0.1:8080/mcp
  scripts/airlock_mcp_client.py --url <url>    # any other URL

The bearer is read from the macOS keychain entry "airlock-mcp-server-token" (service name,
account dylanmerigaud), never printed and never taken from an argument.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEPLOYED_URL = "https://airlock-mcp-771466810465.us-central1.run.app/mcp"
LOCAL_URL = "http://127.0.0.1:8080/mcp"
BUCKET = "airlock-agentic-cinema-assets"
PROVENANCE_CASES = [
    (f"gs://{BUCKET}/calibration/nimbus-clean-clip.mp4", "PASS"),
    (f"gs://{BUCKET}/real/CrestToothpa-18-48.mp4", "BLOCK"),
]


def bearer() -> str:
    out = subprocess.run(
        ["security", "find-generic-password", "-s", "airlock-mcp-server-token", "-a", "dylanmerigaud", "-w"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def result_payload(result) -> dict:
    if result.structuredContent is not None:
        return result.structuredContent
    text = "".join(c.text for c in result.content if hasattr(c, "text"))
    return json.loads(text)


async def run(url: str) -> None:
    headers = {"Authorization": f"Bearer {bearer()}"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"tools: {[t.name for t in tools.tools]}")
            for gcs_uri, expected in PROVENANCE_CASES:
                t0 = time.time()
                result = await session.call_tool("check_provenance", {"gcs_uri": gcs_uri})
                elapsed_ms = int((time.time() - t0) * 1000)
                payload = result_payload(result)
                status = payload.get("status")
                match = "as expected" if status == expected else f"UNEXPECTED, wanted {expected}"
                print(f"check_provenance({gcs_uri}) -> {status} in {elapsed_ms} ms ({match})")
                print(f"  reason: {(payload.get('reasons') or [''])[0]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=None, help="MCP server URL, e.g. https://.../mcp")
    ap.add_argument("--local", action="store_true", help=f"use {LOCAL_URL}")
    args = ap.parse_args()
    url = args.url or (LOCAL_URL if args.local else DEPLOYED_URL)
    print(f"connecting to {url}")
    asyncio.run(run(url))


if __name__ == "__main__":
    main()
