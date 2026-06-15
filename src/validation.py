"""Validation for translated section JSON returned by the LLM."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import re
from typing import Any

try:
    from .parser import LawSection
except ImportError:
    from parser import LawSection


class TranslationValidationError(ValueError):
    """Raised when a translation response is not valid section JSON."""


@dataclass(frozen=True)
class TranslatedSection:
    """One validated translated law section."""

    section_number: str
    section_title: str
    source_text: str
    translated_text: Any
    notes: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_number": self.section_number,
            "section_title": self.section_title,
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


def parse_translated_section(raw_response: str, source: LawSection) -> TranslatedSection:
    """Parse and validate one LLM JSON response."""

    payload = _loads_json_object(raw_response)

    if _looks_like_checklist(payload):
        checklist = _normalize_checklist(payload)
        return TranslatedSection(
            section_number=source.section_number,
            section_title=source.section_title,
            source_text=source.source_text,
            translated_text=checklist,
            notes=(),
            warnings=(),
        )

    _require_string(payload, "section_number")
    _require_string(payload, "section_title")
    _require_string(payload, "source_text")
    _require_translation_value(payload, "translated_text")
    notes = _optional_string_list(payload, "notes")
    warnings = _optional_string_list(payload, "warnings")

    if payload["section_number"] != source.section_number:
        raise TranslationValidationError(
            "Response section_number "
            f"{payload['section_number']!r} does not match source {source.section_number!r}."
        )
    if payload["source_text"] != source.source_text:
        raise TranslationValidationError("Response source_text does not match the parsed source text.")

    return TranslatedSection(
        section_number=payload["section_number"],
        section_title=payload["section_title"],
        source_text=payload["source_text"],
        translated_text=payload["translated_text"],
        notes=tuple(notes),
        warnings=tuple(warnings),
    )


def _loads_json_object(raw_response: str) -> dict[str, Any]:
    text = _strip_code_fence(raw_response.strip())
    payload = _load_json_candidate(text)
    if payload is None:
        extracted = _extract_json_object(text)
        if extracted is not None:
            payload = _load_json_candidate(extracted)
    if payload is None:
        try:
            json.loads(text, strict=False)
        except json.JSONDecodeError as exc:
            raise TranslationValidationError(f"Response is not valid JSON: {exc}") from exc
        raise TranslationValidationError("Response is not valid JSON.")
    if not isinstance(payload, dict):
        raise TranslationValidationError("Response JSON must be an object.")
    return payload


def _load_json_candidate(text: str) -> Any | None:
    for candidate in _candidate_json_texts(text):
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass

        try:
            return ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            pass

    return None


def _candidate_json_texts(text: str) -> tuple[str, ...]:
    cleaned = _remove_json_comments(text)
    without_trailing_commas = _remove_trailing_commas(cleaned)
    with_quoted_keys = _quote_bare_object_keys(without_trailing_commas)
    with_missing_commas = _insert_missing_commas(without_trailing_commas)

    candidates: list[str] = []
    for candidate in (text, cleaned, without_trailing_commas, with_quoted_keys, with_missing_commas):
        if candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def _strip_code_fence(text: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _remove_json_comments(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""

        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue

        if character == "/" and next_character == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if character == "/" and next_character == "*":
            index += 2
            while index + 1 < len(text) and text[index : index + 2] != "*/":
                index += 1
            index += 2
            continue

        output.append(character)
        index += 1

    return "".join(output)


def _remove_trailing_commas(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(text):
        character = text[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue

        if character == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "]}":
                index += 1
                continue

        output.append(character)
        index += 1

    return "".join(output)


def _quote_bare_object_keys(text: str) -> str:
    return re.sub(r'(?m)([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)


_VALUE_STARTERS = set('"{\'[-0123456789tfn')


def _insert_missing_commas(text: str) -> str:
    """Insert commas between adjacent JSON values separated only by whitespace.

    Handles the common LLM error of omitting commas between objects in arrays
    or between properties in objects, e.g. ``}\n{`` → ``},\n{``.
    """

    output: list[str] = []
    in_string = False
    escaped = False
    i = 0

    while i < len(text):
        ch = text[i]

        if in_string:
            output.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            output.append(ch)
            i += 1
            continue

        if ch in "}]":
            output.append(ch)
            i += 1
            # Capture any whitespace that follows.
            ws_start = len(output)
            while i < len(text) and text[i] in " \t\r\n":
                output.append(text[i])
                i += 1
            # If the next character starts a new value, a comma is missing.
            if i < len(text) and text[i] in _VALUE_STARTERS:
                output.insert(ws_start, ",")
            continue

        output.append(ch)
        i += 1

    return "".join(output)


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced JSON object from a response with extra text."""

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _require_string(payload: dict[str, Any], key: str) -> None:
    if key not in payload:
        raise TranslationValidationError(f"Response is missing {key!r}.")
    if not isinstance(payload[key], str) or not payload[key].strip():
        raise TranslationValidationError(f"Response field {key!r} must be a non-empty string.")


def _require_translation_value(payload: dict[str, Any], key: str) -> None:
    if key not in payload:
        raise TranslationValidationError(f"Response is missing {key!r}.")
    value = payload[key]
    if value is None or value == "":
        raise TranslationValidationError(f"Response field {key!r} must be non-empty.")
    if not isinstance(value, str | dict | list):
        raise TranslationValidationError(f"Response field {key!r} must be a string, object, or list.")


def _optional_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TranslationValidationError(f"Response field {key!r} must be a list of strings.")
    return value


def _looks_like_checklist(payload: dict[str, Any]) -> bool:
    return "law_id" in payload and "questions" in payload


def _validate_checklist(payload: dict[str, Any]) -> None:
    _require_string(payload, "law_id")
    questions = payload["questions"]
    if not isinstance(questions, list) or not questions:
        raise TranslationValidationError("Response field 'questions' must be a non-empty list.")

    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            raise TranslationValidationError(f"Question {index} must be an object.")
        _require_string(question, "id")
        _require_string(question, "type")
        _require_string(question, "text")
        if question["type"] not in {"CONDITION", "ACTION"}:
            raise TranslationValidationError(
                f"Question {index} type must be 'CONDITION' or 'ACTION'."
            )
        if question.get("allowed_responses") != ["True", "False", "Uncertain"]:
            raise TranslationValidationError(
                f"Question {index} allowed_responses must be "
                "['True', 'False', 'Uncertain']."
            )


def _normalize_checklist(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_checklist(payload)
    return {
        **payload,
        "questions": sorted(
            payload["questions"],
            key=lambda question: 0 if question["type"] == "CONDITION" else 1,
        ),
    }
