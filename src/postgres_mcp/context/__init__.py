"""Context resources exposed to MCP clients (e.g. table schema docs)."""

from .context_resources import register_context_resources
from .instructions import apply_server_instructions

__all__ = [
    "apply_server_instructions",
    "register_context_resources",
]
