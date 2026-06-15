"""Command line interface for the law translation pipeline."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import tomllib
from typing import Any

try:
    from .ollama import OllamaError, OllamaRunner
    from .parser import LawPart, LawSection, ParseError, parse_rules_of_road
    from .prompting import PromptTemplateError, load_prompt_template
    from .retrieval import DEFAULT_URL, RetrievalError, load_html, retrieve_html
    from .translator import TranslationError, translate_sections
except ImportError:
    from ollama import OllamaError, OllamaRunner
    from parser import LawPart, LawSection, ParseError, parse_rules_of_road
    from prompting import PromptTemplateError, load_prompt_template
    from retrieval import DEFAULT_URL, RetrievalError, load_html, retrieve_html
    from translator import TranslationError, translate_sections


class ConfigError(ValueError):
    """Raised when CLI configuration cannot be loaded or validated."""


_CONFIG_PATH_FIELDS = {
    "input_html",
    "raw_cache_path",
    "parsed_cache_path",
    "prompt_file",
    "debug_dir",
    "output",
}
_CONFIG_STRING_FIELDS = {"url", "model"}
_CONFIG_INT_FIELDS = {"max_retries"}
_CONFIG_FLOAT_FIELDS = {"ollama_request_timeout"}
_CONFIG_FIELDS = (
    _CONFIG_PATH_FIELDS
    | _CONFIG_STRING_FIELDS
    | _CONFIG_INT_FIELDS
    | _CONFIG_FLOAT_FIELDS
    | {"section_numbers"}
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    parsed_args = parser.parse_args(argv)

    try:
        args = _resolve_args(parsed_args)
        prompt_template = load_prompt_template(args.prompt_file)
        law_part = _get_law_part(args)
        sections_to_translate = _filter_sections(law_part.sections, args.section_numbers)
        with OllamaRunner(
            args.model,
            request_timeout=args.ollama_request_timeout,
        ) as ollama:
            translated_sections = translate_sections(
                sections_to_translate,
                prompt_template=prompt_template,
                generator=ollama,
                max_retries=args.max_retries,
                debug_dir=args.debug_dir,
            )
    except (
        OSError,
        ConfigError,
        OllamaError,
        ParseError,
        PromptTemplateError,
        RetrievalError,
        TranslationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = {
        "source_url": args.url,
        "part": law_part.part,
        "title": law_part.title,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "prompt_file": str(args.prompt_file),
        "sections": [section.to_dict() for section in translated_sections],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Translated {len(translated_sections)} Part X sections into {args.output}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="law-translation",
        description="Retrieve, parse, and translate Ontario Highway Traffic Act Part X.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "TOML config file containing the same parameters as the CLI flags. "
            "CLI flags override config values."
        ),
    )
    parser.add_argument(
        "--url",
        help="Ontario law URL to retrieve. Defaults to the Highway Traffic Act Part X anchor.",
    )
    parser.add_argument(
        "--input-html",
        type=Path,
        help="Read a saved HTML file instead of retrieving the Ontario law page.",
    )
    parser.add_argument(
        "--raw-cache-path",
        type=Path,
        help="Optional path to write the retrieved raw HTML.",
    )
    parser.add_argument(
        "--parsed-cache-path",
        type=Path,
        help=(
            "Optional parsed Part X JSON cache. If it exists, retrieval/parsing is skipped; "
            "otherwise the parsed sections are written there."
        ),
    )
    parser.add_argument(
        "--section-number",
        action="append",
        dest="section_numbers",
        help=(
            "Specific law section number to translate, such as 134 or 191.0.1. "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--model",
        help="Ollama model name to run with `ollama run <model>`.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Markdown prompt template containing [INSERT_TARGET_STATUTE_HERE].",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        help="Retries per section when the LLM returns invalid JSON. Defaults to 1.",
    )
    parser.add_argument(
        "--ollama-request-timeout",
        type=float,
        help="Seconds to wait for one Ollama generation request. Defaults to 300.",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="Optional directory for raw invalid LLM responses.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write translated Part X JSON.",
    )
    return parser


def _resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    values = vars(args).copy()
    config_path = values.get("config")

    if config_path is not None:
        config_values = _load_config(config_path)
        for key, value in config_values.items():
            if values.get(key) is None:
                values[key] = value

    if values.get("url") is None:
        values["url"] = DEFAULT_URL
    if values.get("max_retries") is None:
        values["max_retries"] = 1
    if values.get("ollama_request_timeout") is None:
        values["ollama_request_timeout"] = 300.0

    missing = [
        key
        for key in ("model", "prompt_file", "output")
        if values.get(key) is None
    ]
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            f"{', '.join(missing)}. Pass them as flags or set them in --config."
        )

    return argparse.Namespace(**values)


def _load_config(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file {path} is not valid TOML: {exc}") from exc

    unknown = sorted(set(payload) - _CONFIG_FIELDS)
    if unknown:
        raise ConfigError(f"Config file {path} contains unknown key(s): {', '.join(unknown)}.")

    return {
        key: _coerce_config_value(key, value, path)
        for key, value in payload.items()
    }


def _coerce_config_value(key: str, value: Any, config_path: Path) -> Any:
    if key in _CONFIG_PATH_FIELDS:
        if not isinstance(value, str) or not value:
            raise ConfigError(f"Config key {key!r} must be a non-empty string path.")
        path = Path(value)
        return path if path.is_absolute() else config_path.parent / path

    if key in _CONFIG_STRING_FIELDS:
        if not isinstance(value, str) or not value:
            raise ConfigError(f"Config key {key!r} must be a non-empty string.")
        return value

    if key in _CONFIG_INT_FIELDS:
        if not isinstance(value, int):
            raise ConfigError(f"Config key {key!r} must be an integer.")
        return value

    if key in _CONFIG_FLOAT_FIELDS:
        if not isinstance(value, int | float):
            raise ConfigError(f"Config key {key!r} must be a number.")
        return float(value)

    if key == "section_numbers":
        return _coerce_section_numbers(value)

    raise ConfigError(f"Unsupported config key {key!r}.")


def _coerce_section_numbers(value: Any) -> list[str]:
    if isinstance(value, str | int):
        return [str(value)]
    if not isinstance(value, list):
        raise ConfigError("Config key 'section_numbers' must be a string, integer, or list.")
    if not all(isinstance(item, str | int) and str(item) for item in value):
        raise ConfigError("Config key 'section_numbers' must contain only strings or integers.")
    return [str(item) for item in value]


def _get_html(args: argparse.Namespace) -> str:
    if args.input_html is not None:
        return load_html(args.input_html)
    return retrieve_html(args.url, cache_path=args.raw_cache_path)


def _get_law_part(args: argparse.Namespace) -> LawPart:
    if args.parsed_cache_path is not None and args.parsed_cache_path.exists():
        return _load_parsed_law_part(args.parsed_cache_path)

    html = _get_html(args)
    law_part = parse_rules_of_road(html)

    if args.parsed_cache_path is not None:
        _write_parsed_law_part(args.parsed_cache_path, args.url, law_part)

    return law_part


def _load_parsed_law_part(path: Path) -> LawPart:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ParseError(f"Parsed cache {path} is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ParseError(f"Parsed cache {path} must contain a JSON object.")

    part = _require_string(payload, "part", path)
    title = _require_string(payload, "title", path)
    sections_payload = payload.get("sections")
    if not isinstance(sections_payload, list):
        raise ParseError(f"Parsed cache {path} must contain a sections list.")

    sections: list[LawSection] = []
    for index, section_payload in enumerate(sections_payload):
        if not isinstance(section_payload, dict):
            raise ParseError(f"Parsed cache {path} section {index} must be an object.")
        sections.append(
            LawSection(
                section_number=_require_string(section_payload, "section_number", path),
                section_title=_require_string(section_payload, "section_title", path),
                source_text=_require_string(section_payload, "source_text", path),
            )
        )

    if not sections:
        raise ParseError(f"Parsed cache {path} does not contain any sections.")

    return LawPart(part=part, title=title, sections=tuple(sections))


def _write_parsed_law_part(path: Path, source_url: str, law_part: LawPart) -> None:
    payload = {
        "source_url": source_url,
        "part": law_part.part,
        "title": law_part.title,
        "sections": [
            {
                "section_number": section.section_number,
                "section_title": section.section_title,
                "source_text": section.source_text,
            }
            for section in law_part.sections
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _filter_sections(
    sections: tuple[LawSection, ...],
    requested_numbers: list[str] | None,
) -> tuple[LawSection, ...]:
    if not requested_numbers:
        return sections

    available = {section.section_number: section for section in sections}
    missing = [number for number in requested_numbers if number not in available]
    if missing:
        available_numbers = ", ".join(section.section_number for section in sections)
        raise ParseError(
            "Requested section number(s) not found: "
            f"{', '.join(missing)}. Available section numbers: {available_numbers}"
        )

    return tuple(available[number] for number in requested_numbers)


def _require_string(payload: dict[str, Any], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ParseError(f"Parsed cache {path} field {key!r} must be a non-empty string.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
