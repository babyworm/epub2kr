"""Shared fixtures for epub2kr tests."""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from epub2kr.cache import TranslationCache
from epub2kr.services.base import BaseTranslationService


# --- Sample XHTML content ---

SIMPLE_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body>
<h1>Hello World</h1>
<p>This is a test paragraph.</p>
<p>Another paragraph here.</p>
</body>
</html>"""

XHTML_WITH_CODE = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body>
<p>Translate this text.</p>
<pre>do_not_translate()</pre>
<code>also_skip</code>
<p>Translate this too.</p>
</body>
</html>"""

XHTML_WITH_NESTED = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body>
<div>
  <p>Outer text <strong>bold text</strong> tail text</p>
</div>
</body>
</html>"""

EMPTY_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Empty</title></head>
<body></body>
</html>"""

CJK_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>CJK</title></head>
<body>
<h1>\xe4\xb8\xad\xe6\x96\x87\xe6\xa0\x87\xe9\xa2\x98</h1>
<p>\xe8\xbf\x99\xe6\x98\xaf\xe4\xb8\x80\xe4\xb8\xaa\xe6\xb5\x8b\xe8\xaf\x95\xe3\x80\x82</p>
</body>
</html>"""


# --- Fixtures ---

@pytest.fixture
def tmp_cache(tmp_path):
    """Create a TranslationCache in a temporary directory."""
    cache = TranslationCache(cache_dir=str(tmp_path / "cache"))
    yield cache


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".epub2kr"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def mock_service():
    """Create a mock translation service."""
    service = MagicMock(spec=BaseTranslationService)
    service.name.return_value = "mock"
    service.__class__.__name__ = "MockService"

    def mock_translate(texts, source_lang, target_lang):
        return [f"[translated]{t}" for t in texts]

    service.translate.side_effect = mock_translate
    return service


@pytest.fixture
def minimal_epub(tmp_path):
    """Create a minimal valid EPUB file for testing."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book-001")
    book.set_title("Test Book")
    book.set_language("en")
    book.add_author("Test Author")

    # Create chapters with explicit UIDs
    ch1 = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="en", uid="ch1")
    ch1.set_content(SIMPLE_XHTML)
    book.add_item(ch1)

    ch2 = epub.EpubHtml(title="Chapter 2", file_name="ch2.xhtml", lang="en", uid="ch2")
    ch2.set_content(XHTML_WITH_CODE)
    book.add_item(ch2)

    # Add navigation with proper uid parameter
    book.toc = [
        epub.Link("ch1.xhtml", "Chapter 1", uid="ch1_link"),
        epub.Link("ch2.xhtml", "Chapter 2", uid="ch2_link"),
    ]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Spine uses item IDs (strings), nav is added automatically
    book.spine = ["nav", "ch1", "ch2"]

    epub_path = tmp_path / "test.epub"
    epub.write_epub(str(epub_path), book)
    return epub_path
