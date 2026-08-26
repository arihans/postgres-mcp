from pathlib import Path

from mcp.server.fastmcp import FastMCP

from postgres_mcp.context.context_resources import register_context_resources


def _resources_by_uri(mcp: FastMCP) -> dict:
    resources = mcp._resource_manager.list_resources()
    return {str(r.uri): r for r in resources}


def test_registers_directory_of_markdown_files(tmp_path: Path):
    (tmp_path / "orders.md").write_text(
        "---\ndescription: Order table schema\nname: Orders\n---\n# Orders\nColumns: id, total\n"
    )
    (tmp_path / "users.md").write_text("---\ndescription: User table schema\n---\n# Users\n")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 2
    resources = _resources_by_uri(mcp)
    assert "context:///orders.md" in resources
    assert "context:///users.md" in resources

    orders = resources["context:///orders.md"]
    assert orders.name == "Orders"
    assert orders.description == "Order table schema"
    assert orders.mime_type == "text/markdown"
    assert orders.text == "# Orders\nColumns: id, total\n"


def test_non_markdown_files_are_skipped(tmp_path: Path):
    (tmp_path / "orders.md").write_text("---\ndescription: Orders\n---\nbody")
    (tmp_path / "notes.txt").write_text("some text")
    (tmp_path / "schema.json").write_text("{}")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 1
    assert list(_resources_by_uri(mcp).keys()) == ["context:///orders.md"]


def test_hidden_files_and_directories_are_skipped(tmp_path: Path):
    (tmp_path / ".hidden.md").write_text("---\ndescription: hidden\n---\nbody")
    hidden_dir = tmp_path / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "nested.md").write_text("---\ndescription: nested\n---\nbody")
    (tmp_path / "visible.md").write_text("---\ndescription: visible\n---\nbody")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 1
    assert list(_resources_by_uri(mcp).keys()) == ["context:///visible.md"]


def test_nested_directories_use_relative_path_in_uri(tmp_path: Path):
    nested = tmp_path / "docs"
    nested.mkdir()
    (nested / "orders.md").write_text("---\ndescription: Orders\n---\nbody")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 1
    assert "context:///docs/orders.md" in _resources_by_uri(mcp)


def test_missing_description_falls_back_to_filename(tmp_path: Path):
    (tmp_path / "orders.md").write_text("# Orders\nNo frontmatter here.\n")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 1
    resource = _resources_by_uri(mcp)["context:///orders.md"]
    assert resource.description == "orders"
    assert resource.name == "orders"
    assert resource.text == "# Orders\nNo frontmatter here.\n"


def test_malformed_frontmatter_is_treated_as_body(tmp_path: Path):
    raw = "---\ndescription: Orders\nno closing delimiter\n"
    (tmp_path / "orders.md").write_text(raw)

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path))

    assert count == 1
    resource = _resources_by_uri(mcp)["context:///orders.md"]
    assert resource.text == raw
    assert resource.description == "orders"


def test_single_markdown_file_as_context_path(tmp_path: Path):
    file_path = tmp_path / "orders.md"
    file_path.write_text("---\ndescription: Orders\n---\nbody")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(file_path))

    assert count == 1
    assert "context:///orders.md" in _resources_by_uri(mcp)


def test_single_non_markdown_file_is_skipped(tmp_path: Path):
    file_path = tmp_path / "orders.txt"
    file_path.write_text("body")

    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(file_path))

    assert count == 0
    assert _resources_by_uri(mcp) == {}


def test_missing_path_warns_and_returns_zero(tmp_path: Path):
    mcp = FastMCP("test")
    count = register_context_resources(mcp, str(tmp_path / "does-not-exist"))

    assert count == 0
    assert _resources_by_uri(mcp) == {}
