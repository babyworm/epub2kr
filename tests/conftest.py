"""Shared fixtures for epub2kr tests."""
import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageDraw, ImageFont

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


@pytest.fixture
def image_with_text():
    """Create a synthetic PNG image with text drawn on it."""
    img = Image.new('RGB', (400, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.text((50, 80), "Hello World", fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def image_without_text():
    """Create a solid color image with no text."""
    img = Image.new('RGB', (200, 200), color=(128, 128, 200))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def tiny_image():
    """Create an image smaller than the minimum dimension threshold."""
    img = Image.new('RGB', (50, 50), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
