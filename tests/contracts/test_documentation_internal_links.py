import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

def iter_markdown_files():
    """Yields all relevant markdown files in the repository."""
    yield ROOT / "README.md"
    if (ROOT / "docs").exists():
        yield from (ROOT / "docs").rglob("*.md")
    if (ROOT / "examples").exists():
        yield from (ROOT / "examples").rglob("*.md")

def test_internal_markdown_references_exist():
    """
    Smoke test to ensure that internal documentation links and references are not broken.
    Validates Markdown links [text](target) and textual references to docs/*.md.
    """
    broken = []

    # Regex for Markdown links: [text](target)
    # This captures the target part of the link.
    md_link_re = re.compile(r'\[[^\]]*\]\(([^)]+)\)')

    # Regex for textual references to docs/*.md (including those in backticks)
    # We want to catch things like `docs/terminal_access_contract.md` or docs/terminal_access_contract.md
    # We use a negative lookbehind to avoid matching if preceded by a slash, word character, or parenthesis
    # (to avoid double-matching targets of markdown links like [text](docs/file.md)).
    docs_ref_re = re.compile(r'(?<![/\w(])(docs/[\w./-]+\.md)')

    # Files to ignore (e.g. if we know they are false positives or placeholders)
    ignored_patterns = [
        r'docs/your-config-file\.md',  # Example placeholder
    ]

    for md_file in iter_markdown_files():
        if not md_file.exists():
            continue

        content = md_file.read_text(encoding="utf-8")

        # Find all potential targets
        targets = []

        # 1. Markdown links
        for match in md_link_re.finditer(content):
            target = match.group(1).strip()
            targets.append(target)

        # 2. Textual/Code references starting with docs/
        for match in docs_ref_re.finditer(content):
            target = match.group(1).strip()
            targets.append(target)

        for target in targets:
            # Skip external links
            if target.startswith(("http://", "https://", "mailto:")):
                continue

            # Skip purely internal anchors
            if target.startswith("#"):
                continue

            # Skip ignored patterns
            if any(re.match(pattern, target) for pattern in ignored_patterns):
                continue

            # Remove anchor part
            path_part = target.split("#")[0]
            if not path_part:
                continue

            # Skip images if necessary (optional but good to have)
            if path_part.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                continue

            # Resolution strategy:
            # 1. Relative to the current file.
            # 2. Relative to the repository ROOT (especially for docs/ references).

            referenced_file_relative = (md_file.parent / path_part).resolve()
            referenced_file_root = (ROOT / path_part).resolve()

            exists_relative = referenced_file_relative.exists() and referenced_file_relative.is_file()
            exists_root = referenced_file_root.exists() and referenced_file_root.is_file()

            if not exists_relative and not exists_root:
                broken.append(f"In {md_file.relative_to(ROOT)}: '{target}'")

    assert not broken, "Broken internal documentation references found:\n" + "\n".join(broken)
