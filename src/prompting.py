"""Markdown prompt template loading and rendering."""

from __future__ import annotations

from pathlib import Path

try:
    from .parser import LawSection
except ImportError:
    from parser import LawSection


LAW_TEXT_PLACEHOLDER = "{{LAW_TEXT}}"
MARKDOWN_LAW_TEXT_PLACEHOLDER = "[INSERT_TARGET_STATUTE_HERE]"
LAW_TEXT_PLACEHOLDERS = (MARKDOWN_LAW_TEXT_PLACEHOLDER, LAW_TEXT_PLACEHOLDER)


class PromptTemplateError(ValueError):
    """Raised when a prompt template is missing required placeholders."""


def load_prompt_template(path: Path) -> str:
    """Load and validate a prompt template file."""

    template = path.read_text(encoding="utf-8")
    if not any(placeholder in template for placeholder in LAW_TEXT_PLACEHOLDERS):
        raise PromptTemplateError(
            "Prompt template must contain "
            f"{MARKDOWN_LAW_TEXT_PLACEHOLDER} or {LAW_TEXT_PLACEHOLDER}."
        )
    return template


def render_prompt(template: str, section: LawSection) -> str:
    """Insert one law section's source text into the prompt template."""

    rendered = template
    for placeholder in LAW_TEXT_PLACEHOLDERS:
        rendered = rendered.replace(placeholder, section.source_text)
    return rendered
