"""Registers markdown files as MCP resources so they can be served as LLM context."""

import logging
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import TextResource
from pydantic import AnyUrl

logger = logging.getLogger(__name__)

MARKDOWN_SUFFIXES = (".md", ".markdown")
FRONTMATTER_DELIM = "---"


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """Split a leading YAML frontmatter block off a markdown file's contents.

    Returns (metadata, body). metadata is {} when there is no frontmatter block
    (missing opening delimiter, or no matching closing delimiter).
    """
    if not raw.startswith(FRONTMATTER_DELIM):
        return {}, raw

    lines = raw.splitlines(keepends=True)
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\n") == FRONTMATTER_DELIM:
            frontmatter_text = "".join(lines[1:i])
            body = "".join(lines[i + 1 :]).lstrip("\n")
            try:
                metadata = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError as e:
                logger.warning(f"Invalid frontmatter, ignoring: {e}")
                return {}, raw
            if not isinstance(metadata, dict):
                logger.warning("Frontmatter did not parse to a mapping, ignoring")
                return {}, raw
            return metadata, body

    return {}, raw


def _is_hidden(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def register_context_resources(mcp: FastMCP, context_path: str) -> int:
    """Register every markdown file under context_path as an MCP resource.

    Accepts either a single markdown file or a directory (recursed). Each file's
    optional YAML frontmatter supplies the resource's name/description; the
    frontmatter block itself is stripped from the served content. Returns the
    number of resources registered.
    """
    root = Path(context_path).expanduser().resolve()

    if not root.exists():
        logger.warning(f"Context path does not exist, skipping: {root}")
        return 0

    if root.is_file():
        if root.suffix.lower() not in MARKDOWN_SUFFIXES:
            logger.warning(f"Context path is not a markdown file, skipping: {root}")
            return 0
        files = [root]
    else:
        files = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in MARKDOWN_SUFFIXES and not _is_hidden(p, root)
        )

    count = 0
    for file_path in files:
        rel = file_path.name if root.is_file() else file_path.relative_to(root).as_posix()

        try:
            raw = file_path.read_text()
        except OSError as e:
            logger.warning(f"Skipping unreadable context file {rel}: {e}")
            continue

        metadata, body = _split_frontmatter(raw)

        raw_description = metadata.get("description")
        if not raw_description:
            logger.warning(f"Context file {rel} has no 'description' in its frontmatter; falling back to filename")
            description = file_path.stem
        else:
            description = str(raw_description)

        raw_name = metadata.get("name")
        name = str(raw_name) if raw_name else file_path.stem

        mcp.add_resource(
            TextResource(
                uri=AnyUrl(f"context:///{rel}"),
                name=name,
                description=description,
                mime_type="text/markdown",
                text=body,
            )
        )
        count += 1

    logger.info(f"Registered {count} context resource(s) from {root}")
    return count
