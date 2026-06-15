"""Traffic law translation pipeline."""

try:
    from .parser import LawPart, LawSection, parse_rules_of_road
    from .prompting import (
        LAW_TEXT_PLACEHOLDER,
        MARKDOWN_LAW_TEXT_PLACEHOLDER,
        PromptTemplateError,
    )
    from .retrieval import RetrievalError, retrieve_html
    from .translator import TranslationError
    from .validation import TranslatedSection, TranslationValidationError
except ImportError:
    from parser import LawPart, LawSection, parse_rules_of_road
    from prompting import (
        LAW_TEXT_PLACEHOLDER,
        MARKDOWN_LAW_TEXT_PLACEHOLDER,
        PromptTemplateError,
    )
    from retrieval import RetrievalError, retrieve_html
    from translator import TranslationError
    from validation import TranslatedSection, TranslationValidationError

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
