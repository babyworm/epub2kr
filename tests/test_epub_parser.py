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
