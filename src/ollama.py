"""Ollama CLI client."""

from __future__ import annotations

from contextlib import AbstractContextManager
import re
import subprocess


class OllamaError(RuntimeError):
    """Raised when `ollama run` cannot produce a response."""


class OllamaRunner(AbstractContextManager["OllamaRunner"]):
    """Generate text by invoking `ollama run <model>` for each prompt."""

    def __init__(
        self,
        model: str,
        *,
        request_timeout: float = 300.0,
    ) -> None:
        self.model = model
        self.request_timeout = request_timeout

    def __enter__(self) -> "OllamaRunner":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def generate(self, prompt: str) -> str:
        try:
            completed = subprocess.run(
                ["ollama", "run", self.model, "--think", "false", "--hidethinking"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.request_timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OllamaError("Could not run Ollama. Is `ollama` installed and on PATH?") from exc
        except subprocess.TimeoutExpired as exc:
            raise OllamaError(
                f"`ollama run {self.model}` timed out after {self.request_timeout}s."
            ) from exc

        if completed.returncode != 0:
            raise OllamaError(
                f"`ollama run {self.model}` failed with exit code {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )

        response = _strip_thinking_output(completed.stdout).strip()
        if not response:
            raise OllamaError(f"`ollama run {self.model}` returned an empty response.")
        return response


def _strip_thinking_output(output: str) -> str:
    """Remove residual thinking wrappers some models print despite no-think flags."""

    text = _ANSI_RE.sub("", output).strip()
    marker = "...done thinking."
    if marker in text:
        return text.split(marker, maxsplit=1)[1].strip()
    return text


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
