# Traffic Law Translation Pipeline

Python CLI pipeline for retrieving Ontario Highway Traffic Act Part X, "Rules of the Road", parsing it into law sections, sending selected sections to a local Ollama model, and writing validated JSON output.

The pipeline currently works for part X of the laws found here:

```text
https://www.ontario.ca/laws/statute/90h08#BK229
```

## Requirements

- Python 3.11+
- Ollama and a compatible LLM
- A GPU

Example model check:

```bash
ollama list
```

## Project Structure

```text
.
├── config.toml
├── pyproject.toml
├── README.md
└── src/
    ├── __init__.py
    ├── cli.py
    ├── ollama.py
    ├── parser.py
    ├── prompting.py
    ├── prompts/
    │   └── prompt.md
    ├── retrieval.py
    ├── translator.py
    └── validation.py
```

Key files:

- `config.toml`: main runtime configuration.
- `src/cli.py`: command-line entrypoint.
- `src/retrieval.py`: retrieves Ontario law HTML/API content.
- `src/parser.py`: extracts Part X and splits it into sections.
- `src/prompting.py`: inserts each law section into the prompt template.
- `src/ollama.py`: calls `ollama run <model>`.
- `src/translator.py`: sends prompts, retries invalid JSON, and writes debug responses.
- `src/validation.py`: validates and normalizes model JSON.
- `src/prompts/prompt.md`: prompt template used for translation.

Generated files are written under `out/` by default.

## Configuration

The default run uses `config.toml`:

```toml
url = "https://www.ontario.ca/laws/statute/90h08#BK229"
parsed_cache_path = "out/rules_of_road.parsed.json"
section_numbers = [161, 162, 163]
model = "qwen3.5:9b"
prompt_file = "src/prompts/prompt.md"
max_retries = 3
ollama_request_timeout = 300
debug_dir = "out/debug"
output = "out/translation_res.json"
```

To translate all parsed Part X sections, omit `section_numbers` or set:

```toml
section_numbers = []
```

To translate specific sections, set:

```toml
section_numbers = [148]
```

or:

```toml
section_numbers = [161, 162, 163]
```

If retrieval from Ontario is unavailable, use a saved HTML file:

```toml
input_html = "path/to/saved_page.html"
```

## How To Run

From the repo root:

```bash
PYTHONPATH=src python -m cli --config config.toml
```

If the package is installed, use the console script:

```bash
law-translation --config config.toml
```

CLI flags override config values. For example, to run the configured pipeline for one section:

```bash
PYTHONPATH=src python -m cli --config config.toml --section-number 148
```

To change the model for a run:

```bash
PYTHONPATH=src python -m cli --config config.toml --model qwen3.5:27b
```

## Output

The final JSON is written to the configured `output` path, defaulting to:

```text
out/translation_res.json
```

The output shape is:

```json
{
  "source_url": "...",
  "part": "Part X",
  "title": "Rules of the Road",
  "retrieved_at": "...",
  "model": "...",
  "prompt_file": "...",
  "sections": []
}
```

Each section includes the original parsed law text and the model-generated checklist under `translated_text`.

## Notes

- If `parsed_cache_path` exists, retrieval and parsing are skipped.
- Invalid model responses are written to `debug_dir` when configured.
- Checklist questions are normalized so all `CONDITION` questions appear before all `ACTION` questions.
- The output is generated translation data and does not certify legal accuracy.
