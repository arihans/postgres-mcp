from pathlib import Path

from mcp.server.fastmcp import FastMCP

from postgres_mcp.context.instructions import apply_server_instructions


def test_loads_instructions_from_file(tmp_path: Path):
    file_path = tmp_path / "instructions.md"
    file_path.write_text("You are a chatbot for querying CTS/OES data.\n")

    mcp = FastMCP("test")
    applied = apply_server_instructions(mcp, str(file_path))

    assert applied is True
    assert mcp.instructions == "You are a chatbot for querying CTS/OES data.\n"


def test_missing_path_warns_and_leaves_instructions_unset(tmp_path: Path):
    mcp = FastMCP("test")
    applied = apply_server_instructions(mcp, str(tmp_path / "does-not-exist.md"))

    assert applied is False
    assert mcp.instructions is None


def test_directory_path_is_rejected(tmp_path: Path):
    mcp = FastMCP("test")
    applied = apply_server_instructions(mcp, str(tmp_path))

    assert applied is False
    assert mcp.instructions is None


def test_overwrites_any_existing_instructions(tmp_path: Path):
    file_path = tmp_path / "instructions.md"
    file_path.write_text("new instructions")

    mcp = FastMCP("test", instructions="old instructions")
    applied = apply_server_instructions(mcp, str(file_path))

    assert applied is True
    assert mcp.instructions == "new instructions"
