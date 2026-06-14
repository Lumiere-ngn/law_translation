"""Parse Ontario Highway Traffic Act HTML into Part X law sections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import json
import re
from typing import Iterable


PART_TITLE = "Rules of the Road"
START_ANCHOR = "BK229"

_SPACE_RE = re.compile(r"\s+")
_PART_X_RE = re.compile(r"\bPART\s+X\b", re.IGNORECASE)
_LATER_PART_RE = re.compile(r"\bPART\s+X(?:\.1|\.2|\.3|I|V|X|L|C)\b", re.IGNORECASE)
_NUMBERED_BLOCK_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:\.|\s)?\s*(?P<body>.*)$")


@dataclass(frozen=True)
class TextBlock:
    """Text from one visible block-level HTML element."""

    tag: str
    text: str
    anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class LawSection:
    """One parsed law section."""

    section_number: str
    section_title: str
    source_text: str


@dataclass(frozen=True)
class LawPart:
    """Parsed law part with its sections."""

    part: str
    title: str
    sections: tuple[LawSection, ...]

    def to_json(self) -> str:
        """Serialize the parsed part to stable, readable JSON."""

        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class ParseError(ValueError):
    """Raised when expected statute structure cannot be parsed."""


class _VisibleBlockParser(HTMLParser):
    """Collect heading/list/paragraph text without depending on third-party HTML parsers."""

    _BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"}
    _SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[TextBlock] = []
        self._stack: list[dict[str, object]] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        anchor = attr_map.get("id") or attr_map.get("name")

        if tag in self._BLOCK_TAGS:
            self._stack.append({"tag": tag, "pieces": [], "anchors": []})
        if anchor and self._stack:
            anchors = self._stack[-1]["anchors"]
            assert isinstance(anchors, list)
            anchors.append(anchor)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth or tag not in self._BLOCK_TAGS:
            return

        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                block_data = self._stack.pop(index)
                text = _normalize_text(" ".join(block_data["pieces"]))
                if text:
                    self.blocks.append(
                        TextBlock(
                            tag=str(block_data["tag"]),
                            text=text,
                            anchors=tuple(str(anchor) for anchor in block_data["anchors"]),
                        )
                    )
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._stack:
            return
        pieces = self._stack[-1]["pieces"]
        assert isinstance(pieces, list)
        pieces.append(data)


def parse_rules_of_road(html: str) -> LawPart:
    """Parse Part X, Rules of the Road, into section records."""

    blocks = _parse_text_blocks(html)
    start_index = _find_part_x_start(blocks)
    stop_index = _find_part_x_stop(blocks, start_index)
    part_blocks = blocks[start_index + 1 : stop_index]
    sections = tuple(_split_sections(part_blocks))

    if not sections:
        raise ParseError("Found Part X heading but could not parse any law sections.")

    return LawPart(part="Part X", title=PART_TITLE, sections=sections)


def _parse_text_blocks(html: str) -> list[TextBlock]:
    parser = _VisibleBlockParser()
    parser.feed(html)
    parser.close()
    return parser.blocks


def _find_part_x_start(blocks: list[TextBlock]) -> int:
    for index, block in enumerate(blocks):
        anchors = {anchor.upper() for anchor in block.anchors}
        if START_ANCHOR in anchors and _looks_like_part_x_heading(block.text):
            return index

    for index, block in enumerate(blocks):
        text = block.text
        combined = _combine_with_next(blocks, index)

        if _looks_like_part_x_heading(text) or _looks_like_part_x_heading(combined):
            return index
        if text.upper() == "PART X" and PART_TITLE.upper() in _combine_with_next(blocks, index).upper():
            return index

    raise ParseError("Could not find Part X, Rules of the Road, in the HTML.")


def _find_part_x_stop(blocks: list[TextBlock], start_index: int) -> int:
    for index in range(start_index + 1, len(blocks)):
        text = blocks[index].text
        combined = _combine_with_next(blocks, index) if text.upper().startswith("PART ") else text
        if _looks_like_later_part_heading(text) or _looks_like_later_part_heading(combined):
            return index
    return len(blocks)


def _split_sections(blocks: Iterable[TextBlock]) -> Iterable[LawSection]:
    block_list = list(blocks)
    current_number: str | None = None
    current_title: str | None = None
    current_lines: list[str] = []
    pending_title: str | None = None

    for index, block in enumerate(block_list):
        text = block.text
        section_match = _NUMBERED_BLOCK_RE.match(text)
        if section_match and _is_plausible_section_number(section_match.group("number")):
            if current_number is not None and current_title is not None:
                yield _build_section(current_number, current_title, current_lines)

            current_number = section_match.group("number")
            body = _normalize_text(section_match.group("body"))
            current_title = pending_title or _title_from_numbered_body(body)
            current_lines = [line for line in (pending_title, text) if line]
            pending_title = None
            continue

        if current_number is not None:
            if _is_possible_section_title(text) and _next_block_starts_section(block_list, index):
                pending_title = text
                continue
            current_lines.append(text)
            continue

        if _is_possible_section_title(text):
            pending_title = text

    if current_number is not None and current_title is not None:
        yield _build_section(current_number, current_title, current_lines)


def _build_section(number: str, title: str, lines: list[str]) -> LawSection:
    return LawSection(
        section_number=number,
        section_title=title,
        source_text="\n".join(line for line in lines if line).strip(),
    )


def _looks_like_part_x_heading(text: str) -> bool:
    normalized = text.upper()
    return bool(_PART_X_RE.search(text)) and PART_TITLE.upper() in normalized and "PART X." not in normalized


def _looks_like_later_part_heading(text: str) -> bool:
    normalized = text.upper()
    if PART_TITLE.upper() in normalized:
        return False
    return bool(_LATER_PART_RE.search(text))


def _is_plausible_section_number(value: str) -> bool:
    parts = value.split(".")
    if not all(part.isdigit() for part in parts):
        return False
    number = int(parts[0])
    return 1 <= number <= 999


def _normalize_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _normalize_title(text: str) -> str:
    return text.strip(" .")


def _title_from_numbered_body(text: str) -> str:
    if not text:
        return "Untitled section"
    sentence = re.split(r"(?<=[.;:])\s+", text, maxsplit=1)[0]
    return _normalize_title(sentence)


def _is_possible_section_title(text: str) -> bool:
    normalized = text.upper()
    if not text or len(text) > 180:
        return False
    if text.endswith("."):
        return False
    if normalized.startswith("PART ") or "COVERS THE FOLLOWING ITEMS" in normalized:
        return False
    if _NUMBERED_BLOCK_RE.match(text):
        return False
    return any(character.isalpha() for character in text)


def _next_block_starts_section(blocks: list[TextBlock], index: int) -> bool:
    if index + 1 >= len(blocks):
        return False
    match = _NUMBERED_BLOCK_RE.match(blocks[index + 1].text)
    return bool(match and _is_plausible_section_number(match.group("number")))


def _combine_with_next(blocks: list[TextBlock], index: int) -> str:
    current = blocks[index].text
    next_text = blocks[index + 1].text if index + 1 < len(blocks) else ""
    return _normalize_text(f"{current} {next_text}")
