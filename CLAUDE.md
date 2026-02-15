# epub2kr - Project Guidelines

## Project Overview

EPUB translation CLI tool that preserves layout. Supports Google Translate (free), DeepL, OpenAI, Ollama backends.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- **Python 3.12**, venv at `.venv/`
- System Python is externally-managed; always use `.venv/bin/python`
- Entry point: `epub2kr` CLI via `src/epub2kr/cli.py:main`

## Architecture

Pipeline: `EpubParser.load()` → `TextExtractor.extract_texts()` → `Cache.get_batch()` → `Service.translate()` → `TextExtractor.replace_texts()` → `EpubParser.save()`

### Key Files

| File | Role |
|------|------|
| `src/epub2kr/cli.py` | Click CLI interface |
| `src/epub2kr/translator.py` | Translation pipeline orchestrator |
| `src/epub2kr/epub_parser.py` | EPUB read/write (ebooklib) |
| `src/epub2kr/text_extractor.py` | XHTML text extraction (lxml HTMLParser) |
| `src/epub2kr/cache.py` | SQLite translation cache |
| `src/epub2kr/config.py` | Config load/save (`~/.epub2kr/config.json`) |
| `src/epub2kr/services/` | Translation backends (google, deepl, openai, ollama) |

## Coding Conventions

### Language

- **All user-facing messages (CLI output, errors, logs) must be in English**
- Code comments and docstrings in English
- README.md is in Korean (user documentation)

### Style

- Follow existing patterns in the codebase
- Use type hints for function signatures
- Use `rich.console.Console` for CLI output (colored, formatted)
- Error messages: `console.print(f"[bold red]Error:[/bold red] {message}")`

### Language Code Validation

- All language codes are validated via `validate_lang_code()` in `translator.py`
- Common country code mistakes (kr, jp, cn) are caught with helpful suggestions
- `LANG_NAMES` dict is the single source of truth for supported languages
- `LANG_CORRECTIONS` dict maps country codes to correct language codes
- `auto` is a special value for source language (auto-detect)

### ebooklib Workarounds

- ebooklib loses TOC Link UIDs on read → `EpubParser._fix_toc_uids()` patches them before save
- `update_metadata_language()` must clear existing language metadata before setting new (ebooklib appends, doesn't replace)
- Empty `<body></body>` causes lxml ParserError in ebooklib's write → ensure minimal content

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_translator.py -v

# Run with coverage
pytest tests/ --cov=epub2kr --cov-report=term-missing
```

### Test Structure

| File | Coverage |
|------|----------|
| `tests/conftest.py` | Shared fixtures (XHTML samples, mock service, minimal EPUB) |
| `tests/test_text_extractor.py` | 16 tests - extraction, replacement, round-trip |
| `tests/test_cache.py` | 24 tests - CRUD, batch, stats, thread safety |
| `tests/test_config.py` | 10 tests - load/save, defaults, error handling |
| `tests/test_services.py` | 33 tests - factory, all 4 backends |
| `tests/test_epub_parser.py` | 12 tests - load/save, metadata, TOC |
| `tests/test_translator.py` | 21 tests - pipeline, cache, bilingual, CJK |
| `tests/test_integration.py` | 20 tests - CLI (11) + E2E pipeline (9) |

### Test Guidelines

- Use `unittest.mock` (patch, MagicMock) for external dependencies
- Never make real API calls in tests
- Use `tmp_path` fixture for temporary files
- Use `monkeypatch` for environment variables
- Test EPUB: `inputs/test_book.epub` (Chinese H.265/HEVC book, 96 chapters)

## Git Workflow

- Branch: `main`
- Commit messages: imperative mood, concise summary line
- Always run `pytest tests/` before committing
- Push to: `github.com:babyworm/epub2kr.git`

## Dependencies

- `ebooklib` - EPUB read/write (AGPL-3.0 license → project is AGPL-3.0-or-later)
- `lxml` - XHTML parsing
- `click` - CLI framework
- `rich` - Terminal formatting
- `requests` - HTTP (Google Translate)
- `openai` - OpenAI API
- `deepl` - DeepL API
- `langdetect` - Language detection
- Dev: `pytest`, `pytest-cov`, `ruff`

## Build

```bash
# pyproject.toml build backend
build-backend = "setuptools.build_meta"  # NOT setuptools.backends._legacy
```
