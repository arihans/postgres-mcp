"""Loads server-level instructions text, sent to every client at MCP `initialize`."""

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


def apply_server_instructions(mcp: FastMCP, instructions_path: str) -> bool:
    """Load instructions_path and set it as the server's MCP `instructions` field.

    Unlike context resources, this text is sent to every client automatically as
    part of the `initialize` handshake rather than requiring an explicit fetch, so
    it's the right place for behavior/policy that must apply on every turn (e.g.
    scope restrictions), not just reference material a model may look up on demand.

    Returns True if instructions were applied, False otherwise (missing path, path
    is a directory, or the file couldn't be read).
    """
    path = Path(instructions_path).expanduser().resolve()

    if not path.exists():
        logger.warning(f"Instructions path does not exist, skipping: {path}")
        return False

    if path.is_dir():
        logger.warning(f"Instructions path must be a single file, skipping directory: {path}")
        return False

    try:
        text = path.read_text()
    except OSError as e:
        logger.warning(f"Could not read instructions file {path}: {e}")
        return False

    # FastMCP.instructions is a read-only property; the underlying lowlevel
    # Server object holds the mutable attribute that feeds `initialize`.
    mcp._mcp_server.instructions = text  # type: ignore
    logger.info(f"Loaded server instructions from {path} ({len(text)} chars)")
    return True
