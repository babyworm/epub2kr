"""Unit tests for EpubParser."""
import pytest
from pathlib import Path
from ebooklib import epub

from epub2kr.epub_parser import EpubParser


class TestEpubParserLoad:
    """Tests for EpubParser.load()."""

    def test_load_valid_epub(self, minimal_epub):
        """Test loading a valid EPUB file."""
        book = EpubParser.load(str(minimal_epub))

        assert isinstance(book, epub.EpubBook)
        assert book.get_metadata("DC", "title")[0][0] == "Test Book"
        assert book.get_metadata("DC", "language")[0][0] == "en"

    def test_load_nonexistent_file_raises_error(self, tmp_path):
        """Test loading a non-existent file raises FileNotFoundError."""
        nonexistent_path = tmp_path / "nonexistent.epub"

        with pytest.raises(FileNotFoundError) as exc_info:
            EpubParser.load(str(nonexistent_path))

        assert "EPUB file not found" in str(exc_info.value)
        assert str(nonexistent_path) in str(exc_info.value)


class TestEpubParserSave:
    """Tests for EpubParser.save()."""

    def test_save_and_reload_roundtrip(self, minimal_epub, tmp_path):
        """Test saving an EPUB and reloading it preserves content."""
        # Load original
        original_book = EpubParser.load(str(minimal_epub))
        original_title = original_book.get_metadata("DC", "title")[0][0]

        # Save to new location
        output_path = tmp_path / "output.epub"
        EpubParser.save(original_book, str(output_path))

        # Reload and verify
        reloaded_book = EpubParser.load(str(output_path))
        reloaded_title = reloaded_book.get_metadata("DC", "title")[0][0]

        assert output_path.exists()
        assert reloaded_title == original_title


class TestEpubParserGetContentDocuments:
    """Tests for EpubParser.get_content_documents()."""

    def test_get_content_documents_returns_correct_count(self, minimal_epub):
        """Test get_content_documents returns correct number of documents."""
        book = EpubParser.load(str(minimal_epub))
        content_docs = EpubParser.get_content_documents(book)

        # minimal_epub has 2 chapters + nav (3 total HTML documents)
        assert len(content_docs) == 3
        assert all(isinstance(doc, epub.EpubHtml) for doc in content_docs)

    def test_get_content_documents_preserves_spine_order(self, minimal_epub):
        """Test content documents are returned in spine order."""
        book = EpubParser.load(str(minimal_epub))
        content_docs = EpubParser.get_content_documents(book)

        # Check filenames match expected order (nav, ch1, ch2)
        assert content_docs[0].file_name == "nav.xhtml"
        assert content_docs[1].file_name == "ch1.xhtml"
        assert content_docs[2].file_name == "ch2.xhtml"


class TestEpubParserUpdateMetadataLanguage:
    """Tests for EpubParser.update_metadata_language()."""

    def test_update_metadata_language_changes_language(self, minimal_epub):
        """Test updating metadata language changes the language field."""
        book = EpubParser.load(str(minimal_epub))

        # Verify original language
        assert book.get_metadata("DC", "language")[0][0] == "en"

        # Update to Korean
        EpubParser.update_metadata_language(book, "ko")

        # Verify new language
        assert book.get_metadata("DC", "language")[0][0] == "ko"

    def test_update_metadata_language_multiple_updates(self, minimal_epub):
        """Test multiple language updates work correctly."""
        book = EpubParser.load(str(minimal_epub))

        EpubParser.update_metadata_language(book, "ja")
        assert book.get_metadata("DC", "language")[0][0] == "ja"

        EpubParser.update_metadata_language(book, "zh")
        assert book.get_metadata("DC", "language")[0][0] == "zh"


class TestEpubParserTranslateMetadata:
    """Tests for EpubParser.translate_metadata()."""

    def _make_book_with_metadata(self, title="Test Book", description=None, subject=None, creator=None):
        """Helper to create a book with various metadata fields."""
        book = epub.EpubBook()
        book.set_identifier("meta-test-001")
        book.set_title(title)
        book.set_language("zh")
        if description:
            book.add_metadata('DC', 'description', description)
        if subject:
            book.add_metadata('DC', 'subject', subject)
        if creator:
            book.add_author(creator)
        return book

    def test_translates_title(self):
        """Test title metadata is translated."""
        book = self._make_book_with_metadata(title="中文标题")

        def mock_translator(text):
            return f"[EN]{text}"

        result = EpubParser.translate_metadata(book, mock_translator)

        assert 'title' in result
        assert result['title'] == [("中文标题", "[EN]中文标题")]
        assert book.get_metadata('DC', 'title')[0][0] == "[EN]中文标题"

    def test_translates_description(self):
        """Test description metadata is translated."""
        book = self._make_book_with_metadata(description="这是一本关于测试的书")

        def mock_translator(text):
            return f"[EN]{text}"

        result = EpubParser.translate_metadata(book, mock_translator)

        assert 'description' in result
        assert book.get_metadata('DC', 'description')[0][0] == "[EN]这是一本关于测试的书"

    def test_translates_subject(self):
        """Test subject metadata is translated."""
        book = self._make_book_with_metadata(subject="计算机科学")

        def mock_translator(text):
            return f"[EN]{text}"

        result = EpubParser.translate_metadata(book, mock_translator)

        assert 'subject' in result
        assert book.get_metadata('DC', 'subject')[0][0] == "[EN]计算机科学"

    def test_translates_all_default_fields(self):
        """Test all three default fields are translated together."""
        book = self._make_book_with_metadata(
            title="中文标题", description="描述", subject="主题"
        )

        def mock_translator(text):
            return f"[KO]{text}"

        result = EpubParser.translate_metadata(book, mock_translator)

        assert len(result) == 3
        assert book.get_metadata('DC', 'title')[0][0] == "[KO]中文标题"
        assert book.get_metadata('DC', 'description')[0][0] == "[KO]描述"
        assert book.get_metadata('DC', 'subject')[0][0] == "[KO]主题"

    def test_skips_missing_fields(self):
        """Test that missing metadata fields are silently skipped."""
        book = self._make_book_with_metadata(title="Test")

        def mock_translator(text):
            return f"[EN]{text}"

        result = EpubParser.translate_metadata(book, mock_translator)

        # Only title exists, description and subject are missing
        assert 'title' in result
        assert 'description' not in result
        assert 'subject' not in result

    def test_does_not_translate_unlisted_fields(self):
        """Test that creator/publisher are NOT translated by default."""
        book = self._make_book_with_metadata(title="Test", creator="张三")

        def mock_translator(text):
            return f"[EN]{text}"

        EpubParser.translate_metadata(book, mock_translator)

        # Creator should remain untouched
        creators = book.get_metadata('DC', 'creator')
        assert any("张三" in c[0] for c in creators)

    def test_custom_fields_parameter(self):
        """Test custom fields list only translates specified fields."""
        book = self._make_book_with_metadata(title="原始标题", description="原始描述")

        def mock_translator(text):
            return f"[EN]{text}"

        result = EpubParser.translate_metadata(book, mock_translator, fields=['description'])

        # Only description translated, title untouched
        assert 'description' in result
        assert 'title' not in result
        assert book.get_metadata('DC', 'title')[0][0] == "原始标题"
        assert book.get_metadata('DC', 'description')[0][0] == "[EN]原始描述"

    def test_preserves_metadata_attributes(self):
        """Test that metadata attributes are preserved after translation."""
        book = epub.EpubBook()
        book.set_identifier("attr-test")
        book.set_title("Test Title")
        book.set_language("en")

        # Get original attributes
        orig_attrs = book.get_metadata('DC', 'title')[0][1]

        def mock_translator(text):
            return f"[KO]{text}"

        EpubParser.translate_metadata(book, mock_translator)

        # Attributes should be preserved
        new_attrs = book.get_metadata('DC', 'title')[0][1]
        assert new_attrs == orig_attrs

    def test_roundtrip_save_reload(self, tmp_path):
        """Test translated metadata survives save/reload cycle."""
        book = self._make_book_with_metadata(title="原始标题", description="书籍描述")

        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", uid="ch1")
        ch1.set_content(b"<html><body><p>Content</p></body></html>")
        book.add_item(ch1)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", "ch1"]
        book.toc = [epub.Link("ch1.xhtml", "Ch1", uid="ch1_link")]

        def mock_translator(text):
            return f"[KO]{text}"

        EpubParser.translate_metadata(book, mock_translator)

        # Save and reload
        path = tmp_path / "meta_test.epub"
        EpubParser.save(book, str(path))
        reloaded = EpubParser.load(str(path))

        assert reloaded.get_metadata('DC', 'title')[0][0] == "[KO]原始标题"
        assert reloaded.get_metadata('DC', 'description')[0][0] == "[KO]书籍描述"


class TestEpubParserUpdateTocLabels:
    """Tests for EpubParser.update_toc_labels()."""

    def test_update_toc_labels_translates_link_titles(self, minimal_epub):
        """Test TOC Link titles are translated."""
        book = EpubParser.load(str(minimal_epub))

        # Define translator function
        def mock_translator(text):
            return f"[KO]{text}"

        # Update TOC
        EpubParser.update_toc_labels(book, mock_translator)

        # Verify translations
        assert book.toc[0].title == "[KO]Chapter 1"
        assert book.toc[1].title == "[KO]Chapter 2"

    def test_update_toc_labels_translates_section_titles(self, tmp_path):
        """Test TOC Section titles are translated."""
        # Create EPUB with Section in TOC
        book = epub.EpubBook()
        book.set_identifier("test-sections")
        book.set_title("Test Sections")
        book.set_language("en")

        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml")
        ch1.set_content(b"<html><body>Test</body></html>")
        book.add_item(ch1)

        # Create TOC with Section
        section = epub.Section("Part One")
        book.toc = [section]
        book.spine = [("ch1", "yes")]

        # Translate
        def mock_translator(text):
            return f"[KO]{text}"

        EpubParser.update_toc_labels(book, mock_translator)

        # Verify
        assert book.toc[0].title == "[KO]Part One"

    def test_update_toc_labels_handles_nested_tuple_items(self, tmp_path):
        """Test TOC handles nested tuple items (Section, children)."""
        book = epub.EpubBook()
        book.set_identifier("test-nested")
        book.set_title("Test Nested")
        book.set_language("en")

        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml")
        ch1.set_content(b"<html><body>Test</body></html>")
        book.add_item(ch1)

        # Create nested TOC structure
        section = epub.Section("Part One")
        link = epub.Link("ch1.xhtml", "Chapter 1", "ch1")
        book.toc = [(section, [link])]
        book.spine = [("ch1", "yes")]

        # Translate
        def mock_translator(text):
            return f"[KO]{text}"

        EpubParser.update_toc_labels(book, mock_translator)

        # Verify parent section
        assert book.toc[0][0].title == "[KO]Part One"
        # Verify child link
        assert book.toc[0][1][0].title == "[KO]Chapter 1"

    def test_update_toc_labels_skips_empty_titles(self, tmp_path):
        """Test TOC update skips items with empty titles."""
        book = epub.EpubBook()
        book.set_identifier("test-empty")
        book.set_title("Test Empty")
        book.set_language("en")

        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml")
        ch1.set_content(b"<html><body>Test</body></html>")
        book.add_item(ch1)

        # Create TOC with empty title
        link_with_title = epub.Link("ch1.xhtml", "Chapter 1", "ch1")
        link_empty = epub.Link("ch1.xhtml", "", "ch1_empty")
        book.toc = [link_with_title, link_empty]
        book.spine = [("ch1", "yes")]

        # Translate (should not fail on empty)
        def mock_translator(text):
            if not text:
                raise ValueError("Should not translate empty text")
            return f"[KO]{text}"

        EpubParser.update_toc_labels(book, mock_translator)

        # Verify only non-empty was translated
        assert book.toc[0].title == "[KO]Chapter 1"
        assert book.toc[1].title == ""

    def test_update_toc_labels_deeply_nested_structure(self, tmp_path):
        """Test TOC handles deeply nested structures."""
        book = epub.EpubBook()
        book.set_identifier("test-deep")
        book.set_title("Test Deep Nesting")
        book.set_language("en")

        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml")
        ch1.set_content(b"<html><body>Test</body></html>")
        book.add_item(ch1)

        # Create deeply nested structure
        part = epub.Section("Part One")
        chapter = epub.Section("Chapter 1")
        section = epub.Link("ch1.xhtml", "Section 1.1", "s1")

        book.toc = [(part, [(chapter, [section])])]
        book.spine = [("ch1", "yes")]

        # Translate
        def mock_translator(text):
            return f"[KO]{text}"

        EpubParser.update_toc_labels(book, mock_translator)

        # Verify all levels translated
        assert book.toc[0][0].title == "[KO]Part One"
        assert book.toc[0][1][0][0].title == "[KO]Chapter 1"
        assert book.toc[0][1][0][1][0].title == "[KO]Section 1.1"
