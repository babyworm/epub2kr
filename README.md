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

# Disable image OCR translation
epub2kr book.epub --no-translate-images -lo ko

# Disable cache
epub2kr book.epub --no-cache -lo ko

# Explicit source language (default: auto)
epub2kr book.epub -li zh -lo en
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

This project is licensed under AGPL-3.0-or-later.
See `LICENSE` and `NOTICE`.

Author: Hyun-Gyu (Ethan) Kim
This project is licensed under AGPL-3.0-or-later. See LICENSE and NOTICE.
