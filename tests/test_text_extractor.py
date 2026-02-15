"""Unit tests for TextExtractor class."""
import pytest
from lxml import etree

from epub2kr.text_extractor import TextExtractor
from tests.conftest import (
    SIMPLE_XHTML,
    XHTML_WITH_CODE,
    XHTML_WITH_NESTED,
    EMPTY_XHTML,
    CJK_XHTML,
)


class TestTextExtractor:
    """Test suite for TextExtractor class."""

    def test_extract_texts_simple(self):
        """Test basic text extraction from simple XHTML."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(SIMPLE_XHTML)

        # Includes title "Test" + 3 body texts
        assert len(texts) == 4
        assert texts[0] == "Test"
        assert texts[1] == "Hello World"
        assert texts[2] == "This is a test paragraph."
        assert texts[3] == "Another paragraph here."
        assert tree is not None
        assert isinstance(tree, etree._Element)

    def test_extract_texts_skips_code_blocks(self):
        """Test that code/pre/script/style blocks are skipped."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(XHTML_WITH_CODE)

        # Should extract title "Test" + two <p> elements, not <pre> or <code>
        assert len(texts) == 3
        assert texts[0] == "Test"
        assert texts[1] == "Translate this text."
        assert texts[2] == "Translate this too."

    def test_extract_texts_handles_nested_elements(self):
        """Test extraction from nested elements with tail text."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(XHTML_WITH_NESTED)

        # Should extract: title "Test" + "Outer text", "bold text", "tail text"
        assert len(texts) == 4
        assert texts[0] == "Test"
        assert texts[1] == "Outer text"
        assert texts[2] == "bold text"
        assert texts[3] == "tail text"

    def test_extract_texts_empty_content(self):
        """Test extraction from empty XHTML returns only title."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(EMPTY_XHTML)

        # Only extracts title "Empty", body is empty
        assert len(texts) == 1
        assert texts[0] == "Empty"
        assert tree is not None

    def test_extract_texts_cjk_characters(self):
        """Test extraction of CJK (Chinese/Japanese/Korean) text."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(CJK_XHTML)

        # Includes title "CJK" + "中文标题" + "这是一个测试。"
        assert len(texts) == 3
        assert texts[0] == "CJK"
        assert texts[1] == "中文标题"
        assert texts[2] == "这是一个测试。"

    def test_replace_texts_correct_count(self):
        """Test replace_texts with correct number of translations."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(SIMPLE_XHTML)

        # Translate all four extracted texts (title + 3 body texts)
        translations = ["테스트", "번역된 제목", "번역된 단락 1", "번역된 단락 2"]
        result = extractor.replace_texts(tree, translations)

        assert b"\xeb\xb2\x88\xec\x97\xad\xeb\x90\x9c" in result  # Korean bytes for "번역된"
        assert isinstance(result, bytes)

    def test_replace_texts_raises_too_few_translations(self):
        """Test replace_texts raises ValueError with too few translations."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(SIMPLE_XHTML)

        # Provide only 2 translations when 4 are needed
        translations = ["Translation 1", "Translation 2"]

        with pytest.raises(ValueError, match="Not enough translations provided"):
            extractor.replace_texts(tree, translations)

    def test_replace_texts_raises_too_many_translations(self):
        """Test replace_texts raises ValueError with too many translations."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(SIMPLE_XHTML)

        # Provide 5 translations when only 4 are needed
        translations = ["T1", "T2", "T3", "T4", "T5"]

        with pytest.raises(ValueError, match="Too many translations provided"):
            extractor.replace_texts(tree, translations)

    def test_round_trip_preserves_structure(self):
        """Test extract then replace preserves document structure."""
        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(SIMPLE_XHTML)

        # Replace with same texts (identity translation)
        result = extractor.replace_texts(tree, texts)

        # Parse both original and result to compare structure
        original_tree = etree.fromstring(SIMPLE_XHTML, extractor.parser)
        result_tree = etree.fromstring(result, extractor.parser)

        # Check that structure is preserved (same number of elements)
        original_elements = list(original_tree.iter())
        result_elements = list(result_tree.iter())

        # Should have same number of elements
        assert len(original_elements) == len(result_elements)

        # Check that text content is preserved
        result_texts, _ = extractor.extract_texts(result)
        assert result_texts == texts

    def test_extract_with_metadata_returns_tag_info(self):
        """Test extract_with_metadata returns correct tag information."""
        extractor = TextExtractor()
        segments, tree = extractor.extract_with_metadata(SIMPLE_XHTML)

        assert len(segments) == 4

        # First segment: title
        assert segments[0]['text'] == "Test"
        assert segments[0]['tag'] == "title"
        assert segments[0]['attrs'] == {}

        # Second segment: h1
        assert segments[1]['text'] == "Hello World"
        assert segments[1]['tag'] == "h1"
        assert segments[1]['attrs'] == {}

        # Third segment: first p
        assert segments[2]['text'] == "This is a test paragraph."
        assert segments[2]['tag'] == "p"
        assert segments[2]['attrs'] == {}

        # Fourth segment: second p
        assert segments[3]['text'] == "Another paragraph here."
        assert segments[3]['tag'] == "p"
        assert segments[3]['attrs'] == {}

    def test_extract_with_metadata_nested_elements(self):
        """Test extract_with_metadata handles tail text correctly."""
        extractor = TextExtractor()
        segments, tree = extractor.extract_with_metadata(XHTML_WITH_NESTED)

        assert len(segments) == 4

        # First: title
        assert segments[0]['text'] == "Test"
        assert segments[0]['tag'] == "title"

        # Second: "Outer text" (element text of <p>)
        assert segments[1]['text'] == "Outer text"
        assert segments[1]['tag'] == "p"

        # Third: "bold text" (element text of <strong>)
        assert segments[2]['text'] == "bold text"
        assert segments[2]['tag'] == "strong"

        # Fourth: "tail text" (tail of <strong>, parent is <p>)
        assert segments[3]['text'] == "tail text"
        assert segments[3]['tag'] == "p_tail"  # Parent tag + _tail
        assert segments[3]['attrs'] == {}

    def test_whitespace_only_nodes_skipped(self):
        """Test that whitespace-only text nodes are skipped."""
        xhtml = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<p>   </p>
<p>Real text</p>
<p>\n\t\n</p>
</body>
</html>"""

        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(xhtml)

        # Should only extract "Real text", skip whitespace-only nodes
        assert len(texts) == 1
        assert texts[0] == "Real text"

    def test_replace_texts_preserves_whitespace(self):
        """Test that replace_texts preserves leading/trailing whitespace."""
        xhtml = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<p>  Hello  </p>
<p>\n\tWorld\n</p>
</body>
</html>"""

        extractor = TextExtractor()
        texts, tree = extractor.extract_texts(xhtml)

        # Replace with different text
        translations = ["Bonjour", "Monde"]
        result = extractor.replace_texts(tree, translations)

        # Parse result and check whitespace preservation
        result_tree = etree.fromstring(result, extractor.parser)
        paragraphs = result_tree.xpath('//p')

        # First paragraph should preserve "  " on both sides
        assert paragraphs[0].text == "  Bonjour  "

        # Second paragraph should preserve "\n\t" and "\n"
        assert paragraphs[1].text == "\n\tMonde\n"

    def test_no_translate_tags_constant(self):
        """Test NO_TRANSLATE_TAGS constant has expected values."""
        assert TextExtractor.NO_TRANSLATE_TAGS == {'code', 'pre', 'script', 'style'}

    def test_extract_with_metadata_skips_code_blocks(self):
        """Test extract_with_metadata also skips NO_TRANSLATE_TAGS."""
        extractor = TextExtractor()
        segments, tree = extractor.extract_with_metadata(XHTML_WITH_CODE)

        # Should extract title + two <p> elements
        assert len(segments) == 3
        assert segments[0]['text'] == "Test"
        assert segments[1]['text'] == "Translate this text."
        assert segments[2]['text'] == "Translate this too."

    def test_extract_with_metadata_includes_attributes(self):
        """Test extract_with_metadata captures element attributes."""
        xhtml = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<p class="intro" id="first">Attributed text</p>
</body>
</html>"""

        extractor = TextExtractor()
        segments, tree = extractor.extract_with_metadata(xhtml)

        assert len(segments) == 1
        assert segments[0]['text'] == "Attributed text"
        assert segments[0]['tag'] == "p"
        assert segments[0]['attrs']['class'] == "intro"
        assert segments[0]['attrs']['id'] == "first"
