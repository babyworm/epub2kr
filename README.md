# epub2kr

A CLI tool to translate EPUB files while preserving layout.

For the Korean documentation, see `README_kr.md`.

## Features

- Preserves original HTML/CSS EPUB layout during translation
- Supports 4 translation backends: Google Translate, DeepL, OpenAI, Ollama
- OCR translation for text inside images (PNG/JPEG)
- Auto source-language detection with consistent use across body/metadata/TOC/OCR
- Parallel chapter translation and parallel image OCR/translation
- Background image pre-scan with early skip of non-translatable images
- Persistent SQLite caches for text translation and OCR pre-scan results
- Images-only mode for post-processing image translation on already translated EPUBs
- Resume mode with checkpoint file (`.resume.json`) for safer continuation
- Performance summary output and optional JSON log output
- Bilingual mode (original + translated)
- Automatic TOC translation and metadata translation
- CJK typography optimization (font, line-height, spacing)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Initial Setup

```bash
epub2kr --setup
```

Configuration is saved to `~/.epub2kr/config.json`.
CLI options override saved defaults.

## Usage

### Basic

```bash
# Default target is English
epub2kr book.epub

# Translate to Korean
epub2kr book.epub -lo ko

# Specify output path
epub2kr book.epub -lo ko -o translated_book.epub
```

### Service Selection

```bash
# DeepL
epub2kr book.epub -s deepl --api-key YOUR_DEEPL_KEY -lo ja

# OpenAI
epub2kr book.epub -s openai --api-key sk-xxx --model gpt-4 -lo es

# Ollama (local)
epub2kr book.epub -s ollama --model llama2 -lo ko

# OpenAI-compatible endpoint
epub2kr book.epub -s openai --base-url http://localhost:8000/v1 --api-key dummy -lo zh
```

### Advanced

```bash
# Bilingual output
epub2kr book.epub --bilingual -lo ko

# Chapter translation threads
epub2kr book.epub -t 4 -lo ko

# Image OCR/translation threads
epub2kr book.epub -j 4 -lo ko

# Chapter 1 thread + image 3 threads
epub2kr book.epub -t 1 -j 3 -lo ko

# Images-only mode (skip chapter translation)
epub2kr book.epub --images-only -lo ko -o book.img-only.epub

# Resume mode (continue from existing output)
epub2kr book.epub --resume -lo ko -o book.ko.epub

# Disable image OCR translation
epub2kr book.epub --no-translate-images -lo ko

# Disable cache
epub2kr book.epub --no-cache -lo ko

# Explicit source language (default: auto)
epub2kr book.epub -li zh -lo en

# Final report as JSON
epub2kr book.epub -lo ko --log-json

# Cache management
epub2kr --cache-stats
epub2kr --cache-clear
epub2kr --cache-prune-days 30
```

When using `-li auto`, logs can look like:

```text
Translation: auto (detected: zh-cn) -> ko (Korean)
```

## CJK Styling Options

For `ko`, `ja`, `zh`, `zh-cn`, `zh-tw`, you can tune typography:

```bash
epub2kr book.epub -lo ko --font-size 14px --line-height 2.0
epub2kr book.epub -lo ko --font-family '"NanumGothic", "Malgun Gothic", sans-serif'
epub2kr book.epub -lo ko --heading-font '"Noto Serif KR", serif'
epub2kr book.epub -lo ko --paragraph-spacing 1em
```

You can also adjust styles without re-translating:

```bash
epub2kr-restyle book.ko.epub --font-size 1em --line-height 2.0
epub2kr-restyle book.ko.epub --inplace --line-height 1.6
epub2kr-restyle book.ko.epub --gui
```

## CLI Options

| Option | Description | Default |
|---|---|---|
| `INPUT_FILE` | Input EPUB path | - |
| `-o, --output` | Output EPUB path | `{input}.{target}.epub` |
| `-s, --service` | `google`, `deepl`, `openai`, `ollama` | `google` |
| `-li, --source-lang` | Source language | `auto` |
| `-lo, --target-lang` | Target language | `en` |
| `-t, --threads` | Chapter translation threads | `4` |
| `-j, --image-threads` | Image OCR/translation threads | same as `threads` |
| `--no-cache` | Disable caches | `false` |
| `--no-translate-images` | Disable image OCR translation | `false` |
| `--images-only` | Run only image OCR/translation | `false` |
| `--resume` | Resume from existing output | `false` |
| `--verbose` | Verbose logs | `false` |
| `--quiet` | Minimal logs | `false` |
| `--log-json` | Print final report in JSON | `false` |
| `--cache-stats` | Show cache stats and exit | `false` |
| `--cache-clear` | Clear translation/OCR caches and exit | `false` |
| `--cache-prune-days` | Prune cache entries older than N days and exit | - |
| `--bilingual` | Output original + translation | `false` |
| `--api-key` | API key for selected service | - |
| `--model` | Model for OpenAI/Ollama | - |
| `--base-url` | Custom API base URL | - |
| `--font-size` | CJK font size | `0.95em` |
| `--line-height` | CJK line height | `1.8` |
| `--font-family` | CJK body font | auto |
| `--heading-font` | CJK heading font | body font |
| `--paragraph-spacing` | CJK paragraph spacing | `0.5em` |
| `--setup` | Run setup wizard | - |

## Caching

Text translation cache:

- Location: `~/.epub2kr/cache.db`
- Key: `SHA-256(source_text) + source_lang + target_lang + service`

OCR pre-scan cache:

- Location: `~/.epub2kr/ocr_cache.db`
- Key: `SHA-256(image_bytes) + source_lang + media_type + confidence_threshold`
- Helps skip repeated OCR work on re-runs

Use `--no-cache` to disable both caches.

Additional cache commands:

- `--cache-stats`: print translation/OCR cache stats and exit
- `--cache-clear`: clear both caches and exit
- `--cache-prune-days N`: remove cache entries older than N days and exit

## Reporting and Benchmark

- At the end of each run, a performance summary is printed (`chapters/images/metadata/save/total`).
- Use `--log-json` to print a machine-readable final report.
- A lightweight benchmark smoke test exists at `tests/test_benchmark.py`.

## Project Structure

```text
src/epub2kr/
├── cli.py
├── translator.py
├── epub_parser.py
├── text_extractor.py
├── image_translator.py
├── cache.py
├── ocr_cache.py
├── restyle.py
├── gui.py
└── services/
```

## License

Author: Hyun-Gyu (Ethan) Kim

This project is licensed under AGPL-3.0-or-later.
See `LICENSE` and `NOTICE`.