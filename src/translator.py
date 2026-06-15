"""Translate parsed law sections through an LLM client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from .parser import LawSection
    from .prompting import render_prompt
    from .validation import (
        TranslatedSection,
        TranslationValidationError,
        parse_translated_section,
    )
except ImportError:
    from parser import LawSection
    from prompting import render_prompt
    from validation import (
        TranslatedSection,
        TranslationValidationError,
        parse_translated_section,
    )


class TranslationError(RuntimeError):
    """Raised when a section cannot be translated into valid JSON."""


class TextGenerator:
    """Protocol-like base for objects that can generate text from a prompt."""

    def generate(self, prompt: str) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class TranslationResult:
    """Result of translating one section."""

    section: TranslatedSection
    attempts: int


def translate_sections(
    sections: tuple[LawSection, ...],
    *,
    prompt_template: str,
    generator: TextGenerator,
    max_retries: int = 1,
    debug_dir: Path | None = None,
) -> tuple[TranslatedSection, ...]:
    """Translate every section and return validated translated sections."""

    translated: list[TranslatedSection] = []
    for section in sections:
        translated.append(
            translate_section(
                section,
                prompt_template=prompt_template,
                generator=generator,
                max_retries=max_retries,
                debug_dir=debug_dir,
            ).section
        )
    return tuple(translated)


def translate_section(
    section: LawSection,
    *,
    prompt_template: str,
    generator: TextGenerator,
    max_retries: int = 1,
    debug_dir: Path | None = None,
) -> TranslationResult:
    """Translate one section, retrying malformed JSON responses."""

    rendered_prompt = render_prompt(prompt_template, section)
    prompt = rendered_prompt
    last_error: TranslationValidationError | None = None

    for attempt in range(1, max_retries + 2):
        raw_response = generator.generate(prompt)
        try:
            parsed = parse_translated_section(raw_response, section)
            return TranslationResult(section=parsed, attempts=attempt)
        except TranslationValidationError as exc:
            last_error = exc
            _write_debug_response(debug_dir, section.section_number, attempt, raw_response)
            prompt = _repair_prompt(rendered_prompt, raw_response, exc)

    raise TranslationError(
        f"Section {section.section_number} did not produce valid JSON after "
        f"{max_retries + 1} attempt(s): {last_error}"
    )


def _repair_prompt(original_prompt: str, invalid_response: str, error: Exception) -> str:
    return (
        "The previous response was invalid for this reason:\n"
        f"{error}\n\n"
        "Return only the JSON object requested by the original prompt. "
        "Use double quotes, include every required comma, and escape all newlines and tabs "
        "inside string values. "
        "Do not include markdown fences or commentary.\n\n"
        "Original prompt:\n"
        f"{original_prompt}\n\n"
        "Invalid response:\n"
        f"{invalid_response}"
    )


def _write_debug_response(
    debug_dir: Path | None,
    section_number: str,
    attempt: int,
    raw_response: str,
) -> None:
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_number = section_number.replace(".", "_")
    path = debug_dir / f"section_{safe_number}_attempt_{attempt}.txt"
    path.write_text(raw_response, encoding="utf-8")
