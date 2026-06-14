"""Traffic law translation pipeline."""

from law_translation.parser import LawPart, LawSection, parse_rules_of_road
from law_translation.prompting import (
    LAW_TEXT_PLACEHOLDER,
    MARKDOWN_LAW_TEXT_PLACEHOLDER,
    PromptTemplateError,
)
from law_translation.retrieval import RetrievalError, retrieve_html
from law_translation.translator import TranslationError
from law_translation.validation import TranslatedSection, TranslationValidationError

__all__ = [
    "LAW_TEXT_PLACEHOLDER",
    "MARKDOWN_LAW_TEXT_PLACEHOLDER",
    "LawPart",
    "LawSection",
    "PromptTemplateError",
    "RetrievalError",
    "TranslatedSection",
    "TranslationError",
    "TranslationValidationError",
    "parse_rules_of_road",
    "retrieve_html",
]
