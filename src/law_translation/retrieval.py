"""HTML retrieval for Ontario law pages."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urldefrag
from urllib.request import Request, urlopen


DEFAULT_URL = "https://www.ontario.ca/laws/statute/90h08#BK229"
ELAWS_API_BASE = "https://www.ontario.ca/laws/api/v2/legislation"


class RetrievalError(RuntimeError):
    """Raised when source HTML cannot be retrieved."""


def retrieve_html(
    url: str = DEFAULT_URL,
    *,
    timeout: float = 30.0,
    cache_path: Path | None = None,
) -> str:
    """Retrieve an Ontario law page as HTML.

    URL fragments are useful to humans in browsers but are not sent to HTTP
    servers, so this fetches the defragmented URL.
    """

    fetch_url, _fragment = urldefrag(url)
    fetch_url = _api_url_for_elaws_document(fetch_url) or fetch_url
    request = Request(
        fetch_url,
        headers={
            "Accept": "application/json,text/html,application/xhtml+xml",
            "User-Agent": "law-translation/0.1 (+local research pipeline)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(content_type, errors="replace")
    except HTTPError as exc:
        raise RetrievalError(
            f"Ontario law page returned HTTP {exc.code} for {fetch_url}. "
            "Use --input-html with a saved copy if automated retrieval is blocked."
        ) from exc
    except URLError as exc:
        raise RetrievalError(f"Could not retrieve {fetch_url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RetrievalError(f"Timed out retrieving {fetch_url}") from exc

    html = _extract_html_content(body)

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")

    return html


def load_html(path: Path) -> str:
    """Load source HTML from disk."""

    return path.read_text(encoding="utf-8")


def _api_url_for_elaws_document(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "laws":
        return None

    if parts[1] == "api":
        return None

    if parts[1] not in {"statute", "regulation"}:
        return None

    document_type = "statute" if parts[1] == "statute" else "regulation"
    code = parts[2]
    version = f"/{parts[3]}" if len(parts) > 3 else ""
    return f"{ELAWS_API_BASE}/en/doc-search/{document_type}/{code}{version}"


def _extract_html_content(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body

    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RetrievalError("Ontario e-Laws API response did not contain HTML content.")
    return content
