"""Unit tests for EpubTranslator."""
import io
from unittest.mock import MagicMock, patch

from ebooklib import epub
from PIL import Image

from epub2kr.translator import EpubTranslator, CJK_LANGS


class TestCJKLangsConstant:
    """Test the CJK_LANGS constant."""

    def test_cjk_langs_has_all_expected_languages(self):
        """CJK_LANGS constant includes all expected languages."""
        expected = {'ko', 'ja', 'zh', 'zh-cn', 'zh-tw'}
        assert CJK_LANGS == expected


class TestTranslateTextsWithCache:
    """Test _translate_texts_with_cache method."""

    def test_no_cache_translates_all_texts(self, mock_service):
        """When use_cache=False, translates all texts without cache checks."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False)

            texts = ["Hello", "World", "Test"]
            translations = translator._translate_texts_with_cache(texts)

            # Should translate all texts
            mock_service.translate.assert_called_once_with(texts, "auto", "en")
            assert translations == ["[translated]Hello", "[translated]World", "[translated]Test"]

    def test_cache_hit_skips_translation(self, mock_service, tmp_cache):
        """When all texts are cached, skips translation service call."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=True)
            translator.cache = tmp_cache

            # Pre-populate cache
            texts = ["Hello", "World"]
            tmp_cache.put_batch(
                [("Hello", "[cached]Hello"), ("World", "[cached]World")],
                "auto",
                "en",
                "MockService"
            )

            translations = translator._translate_texts_with_cache(texts)

            # Should NOT call translation service
            mock_service.translate.assert_not_called()
            assert translations == ["[cached]Hello", "[cached]World"]

    def test_partial_cache_translates_only_uncached(self, mock_service, tmp_cache):
        """When some texts are cached, translates only uncached texts."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=True)
            translator.cache = tmp_cache

            # Pre-populate cache with only first text
            tmp_cache.put("Hello", "[cached]Hello", "auto", "en", "MockService")

            texts = ["Hello", "World", "Test"]
            translations = translator._translate_texts_with_cache(texts)

            # Should translate only uncached texts
            mock_service.translate.assert_called_once_with(["World", "Test"], "auto", "en")
            assert translations == ["[cached]Hello", "[translated]World", "[translated]Test"]

    def test_translation_error_returns_originals(self, mock_service):
        """When translation fails, returns original texts."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            # Mock service that raises error
            mock_service.translate.side_effect = Exception("API error")
            mock_get_service.return_value = mock_service

            translator = EpubTranslator(service_name="google", use_cache=False)

            texts = ["Hello", "World"]
            translations = translator._translate_texts_with_cache(texts)

            # Should return original texts on error
            assert translations == ["Hello", "World"]

    def test_empty_texts_returns_empty_list(self, mock_service):
        """When given empty list, returns empty list."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google")

            translations = translator._translate_texts_with_cache([])

            assert translations == []
            mock_service.translate.assert_not_called()

    def test_uses_effective_source_lang_when_set(self, mock_service):
        """Uses detected/overridden effective source language for translation."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False, source_lang="auto")
            translator.effective_source_lang = "zh"
            translator._source_lang_locked = True

            translator._translate_texts_with_cache(["你好"])

            mock_service.translate.assert_called_once_with(["你好"], "zh", "en")

    def test_auto_source_lang_gets_locked_from_document_texts(self, mock_service):
        """Auto source language should lock during text translation."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False, source_lang="auto")

            translator._translate_texts_with_cache(["這是中文內容"])

            assert translator.effective_source_lang == "zh-tw"
            assert translator._source_lang_locked is True
            mock_service.translate.assert_called_once_with(["這是中文內容"], "zh-tw", "en")


class TestSourceLanguageDetection:
    def test_detects_simplified_chinese_as_zh_cn(self):
        assert EpubTranslator._detect_lang_from_text("这是中文内容") == "zh-cn"

    def test_detects_traditional_chinese_as_zh_tw(self):
        assert EpubTranslator._detect_lang_from_text("這是中文內容") == "zh-tw"

    def test_detects_neutral_han_as_zh(self):
        assert EpubTranslator._detect_lang_from_text("中文內容漢字") == "zh"

    def test_detects_korean_from_hangul_text(self):
        assert EpubTranslator._detect_lang_from_text("이것은 한국어 문장입니다") == "ko"

    def test_detects_japanese_when_kana_present(self):
        assert EpubTranslator._detect_lang_from_text("これは日本語のテキストです") == "ja"


class TestTranslateDocument:
    """Test _translate_document method."""

    def test_calls_extract_translate_replace(self, mock_service):
        """Calls extract, translate, replace in sequence."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False)

            # Mock document item
            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body><p>Hello</p></body></html>"

            # Mock extractor methods
            mock_tree = MagicMock()
            translator.extractor.extract_texts = MagicMock(return_value=(["Hello"], mock_tree))
            translator.extractor.replace_texts = MagicMock(return_value=b"<html><body><p>[translated]Hello</p></body></html>")

            translator._translate_document(mock_item, 1, 1)

            # Verify sequence
            translator.extractor.extract_texts.assert_called_once_with(b"<html><body><p>Hello</p></body></html>")
            mock_service.translate.assert_called_once_with(["Hello"], "auto", "en")
            translator.extractor.replace_texts.assert_called_once_with(mock_tree, ["[translated]Hello"])
            mock_item.set_content.assert_called_once()

    def test_skips_documents_with_no_text(self, mock_service):
        """Skips documents that have no translatable text."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False)

            # Mock document item with no text
            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body></body></html>"

            # Mock extractor to return empty texts
            mock_tree = MagicMock()
            translator.extractor.extract_texts = MagicMock(return_value=([], mock_tree))

            translator._translate_document(mock_item, 1, 1)

            # Should NOT call translate or set_content
            mock_service.translate.assert_not_called()
            mock_item.set_content.assert_not_called()

    def test_handles_whitespace_only_text(self, mock_service):
        """Handles documents with whitespace-only text."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False)

            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body><p>  </p></body></html>"

            mock_tree = MagicMock()
            translator.extractor.extract_texts = MagicMock(return_value=(["  "], mock_tree))
            translator.extractor.replace_texts = MagicMock(return_value=b"<html><body><p>[translated]  </p></body></html>")

            translator._translate_document(mock_item, 1, 1)

            # Should still translate (service decides how to handle whitespace)
            mock_service.translate.assert_called_once()
            mock_item.set_content.assert_called_once()


class TestBilingualMode:
    """Test bilingual mode functionality."""

    def test_creates_combined_original_and_translated(self, mock_service):
        """Bilingual mode creates original+translated pairs."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False, bilingual=True)

            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body><p>Hello</p></body></html>"

            mock_tree = MagicMock()
            translator.extractor.extract_texts = MagicMock(return_value=(["Hello"], mock_tree))
            translator.extractor.replace_texts = MagicMock(return_value=b"<html><body><p>Hello\n\n[translated]Hello</p></body></html>")

            translator._translate_document(mock_item, 1, 1)

            # Check that replace_texts was called with bilingual text
            call_args = translator.extractor.replace_texts.call_args
            assert call_args[0][1] == ["Hello\n\n[translated]Hello"]

    def test_bilingual_skips_whitespace_only_originals(self, mock_service):
        """Bilingual mode skips combining for whitespace-only originals."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", use_cache=False, bilingual=True)

            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body><p>  </p></body></html>"

            mock_tree = MagicMock()
            translator.extractor.extract_texts = MagicMock(return_value=(["  "], mock_tree))
            translator.extractor.replace_texts = MagicMock(return_value=b"<html><body><p>[translated]  </p></body></html>")

            translator._translate_document(mock_item, 1, 1)

            # Whitespace-only original should NOT be combined
            call_args = translator.extractor.replace_texts.call_args
            assert call_args[0][1] == ["[translated]  "]


class TestAddCJKStylesheet:
    """Test _add_cjk_stylesheet method."""

    def test_adds_css_item_for_cjk_targets(self, mock_service):
        """Adds CSS stylesheet item for CJK target languages."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", target_lang="ko")

            # Create mock book and content docs
            mock_book = MagicMock()
            mock_doc1 = MagicMock()
            mock_doc2 = MagicMock()
            content_docs = [mock_doc1, mock_doc2]

            translator._add_cjk_stylesheet(mock_book, content_docs)

            # Should add CSS item to book
            mock_book.add_item.assert_called_once()
            css_item = mock_book.add_item.call_args[0][0]
            assert css_item.file_name == 'style/cjk.css'
            assert css_item.media_type == 'text/css'

            # Should link CSS to all content docs
            mock_doc1.add_link.assert_called_once_with(href='style/cjk.css', rel='stylesheet', type='text/css')
            mock_doc2.add_link.assert_called_once_with(href='style/cjk.css', rel='stylesheet', type='text/css')

    def test_uses_custom_font_family(self, mock_service):
        """Uses custom font_family if provided."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(
                service_name="google",
                target_lang="ko",
                font_family="'Custom Font', sans-serif"
            )

            mock_book = MagicMock()
            content_docs = [MagicMock()]

            translator._add_cjk_stylesheet(mock_book, content_docs)

            css_item = mock_book.add_item.call_args[0][0]
            css_content = css_item.content.decode('utf-8')
            assert "'Custom Font', sans-serif" in css_content

    def test_uses_custom_font_size_and_line_height(self, mock_service):
        """Uses custom font_size and line_height if provided."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(
                service_name="google",
                target_lang="ko",
                font_size="16px",
                line_height="2.0"
            )

            mock_book = MagicMock()
            content_docs = [MagicMock()]

            translator._add_cjk_stylesheet(mock_book, content_docs)

            css_item = mock_book.add_item.call_args[0][0]
            css_content = css_item.content.decode('utf-8')
            assert "font-size: 16px" in css_content
            assert "line-height: 2.0" in css_content


class TestTranslateEpub:
    """Test translate_epub method."""

    def test_generates_correct_default_output_path(self, mock_service, minimal_epub):
        """Generates output path with target language suffix when not provided."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", target_lang="ko")

            # Mock parser methods to avoid actual EPUB operations
            translator.parser.load = MagicMock(return_value=MagicMock())
            translator.parser.get_content_documents = MagicMock(return_value=[])
            translator.parser.update_metadata_language = MagicMock()
            translator.parser.update_toc_labels = MagicMock()
            translator.parser.save = MagicMock()

            input_path = str(minimal_epub)
            output_path = translator.translate_epub(input_path)

            # Should generate path with .ko.epub suffix
            expected = str(minimal_epub.parent / "test.ko.epub")
            assert output_path == expected
            translator.parser.save.assert_called_once_with(translator.parser.load.return_value, expected)

    def test_uses_provided_output_path(self, mock_service, minimal_epub, tmp_path):
        """Uses provided output path when specified."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", target_lang="ko")

            translator.parser.load = MagicMock(return_value=MagicMock())
            translator.parser.get_content_documents = MagicMock(return_value=[])
            translator.parser.update_metadata_language = MagicMock()
            translator.parser.update_toc_labels = MagicMock()
            translator.parser.save = MagicMock()

            custom_output = str(tmp_path / "custom_output.epub")
            output_path = translator.translate_epub(str(minimal_epub), custom_output)

            assert output_path == custom_output
            translator.parser.save.assert_called_once_with(translator.parser.load.return_value, custom_output)

    def test_adds_cjk_stylesheet_for_cjk_languages(self, mock_service, minimal_epub):
        """Adds CJK stylesheet when target language is CJK."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service

            for lang in ['ko', 'ja', 'zh', 'zh-cn', 'zh-tw']:
                translator = EpubTranslator(service_name="google", target_lang=lang)

                mock_book = MagicMock()
                translator.parser.load = MagicMock(return_value=mock_book)
                translator.parser.get_content_documents = MagicMock(return_value=[])
                translator.parser.update_metadata_language = MagicMock()
                translator.parser.update_toc_labels = MagicMock()
                translator.parser.save = MagicMock()
                translator._add_cjk_stylesheet = MagicMock()

                translator.translate_epub(str(minimal_epub))

                # Should call _add_cjk_stylesheet for CJK languages
                translator._add_cjk_stylesheet.assert_called_once()

    def test_skips_cjk_stylesheet_for_non_cjk_languages(self, mock_service, minimal_epub):
        """Skips CJK stylesheet for non-CJK target languages."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", target_lang="en")

            mock_book = MagicMock()
            translator.parser.load = MagicMock(return_value=mock_book)
            translator.parser.get_content_documents = MagicMock(return_value=[])
            translator.parser.update_metadata_language = MagicMock()
            translator.parser.update_toc_labels = MagicMock()
            translator.parser.save = MagicMock()
            translator._add_cjk_stylesheet = MagicMock()

            translator.translate_epub(str(minimal_epub))

            # Should NOT call _add_cjk_stylesheet for non-CJK languages
            translator._add_cjk_stylesheet.assert_not_called()


class TestInitialization:
    """Test EpubTranslator initialization."""

    def test_initializes_with_defaults(self, mock_service):
        """Initializes with default parameters."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator()

            assert translator.source_lang == "auto"
            assert translator.target_lang == "en"
            assert translator.threads == 4
            assert translator.image_threads == 4
            assert translator.cache is not None  # Cache enabled by default
            assert translator.ocr_cache is not None
            assert translator.bilingual is False
            assert translator.font_size == "0.95em"
            assert translator.line_height == "1.8"
            assert translator.font_family is None

    def test_image_threads_can_be_overridden(self, mock_service):
        """Uses image_threads when explicitly provided."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(threads=2, image_threads=6)

            assert translator.threads == 2
            assert translator.image_threads == 6

    def test_initializes_without_cache(self, mock_service):
        """Initializes with cache disabled when use_cache=False."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(use_cache=False)

            assert translator.cache is None
            assert translator.ocr_cache is None

    def test_passes_service_kwargs(self, mock_service):
        """Passes service kwargs to get_service."""
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service

            EpubTranslator(
                service_name="deepl",
                api_key="test-key",
                custom_param="value"
            )

            mock_get_service.assert_called_once_with(
                "deepl",
                api_key="test-key",
                custom_param="value"
            )


class TestImagePrescanCache:
    def test_prefetch_uses_persistent_ocr_cache(self, mock_service, tmp_path):
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", source_lang="zh-cn", use_cache=True)

            # isolate OCR cache per test
            from epub2kr.ocr_cache import OCRPrescanCache
            translator.ocr_cache = OCRPrescanCache(cache_dir=str(tmp_path / "ocr_cache"))

            img = Image.new("RGB", (200, 200), color=(255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_item = epub.EpubImage(
                uid="img1",
                file_name="images/p1.png",
                media_type="image/png",
                content=buf.getvalue(),
            )
            book = MagicMock()
            book.get_items.return_value = [img_item]

            ocr_region = [
                (
                    [[10, 10], [100, 10], [100, 40], [10, 40]],
                    "中文",
                    0.95,
                )
            ]

            with patch("epub2kr.image_translator.ImageTranslator._get_reader") as mock_get_reader:
                mock_reader = MagicMock()
                mock_reader.readtext.return_value = ocr_region
                mock_get_reader.return_value = mock_reader

                # First run: OCR executed and cached
                out1 = translator._prefetch_image_regions(book, "zh-cn")
                assert "images/p1.png" in out1
                assert mock_reader.readtext.call_count == 1

                # Second run: should hit OCR cache and skip OCR call
                out2 = translator._prefetch_image_regions(book, "zh-cn")
                assert "images/p1.png" in out2
                assert mock_reader.readtext.call_count == 1

    def test_prefetch_reuses_cached_image_translations(self, mock_service, tmp_path):
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", source_lang="zh-cn", target_lang="ko", use_cache=True)
            translator.cache = None

            from epub2kr.ocr_cache import OCRPrescanCache
            translator.ocr_cache = OCRPrescanCache(cache_dir=str(tmp_path / "ocr_cache"))

            def make_book():
                img = Image.new("RGB", (200, 200), color=(255, 255, 255))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_item = epub.EpubImage(
                    uid="img1",
                    file_name="images/p1.png",
                    media_type="image/png",
                    content=buf.getvalue(),
                )
                book = MagicMock()
                book.get_items.return_value = [img_item]
                return book

            ocr_region = [
                (
                    [[10, 10], [100, 10], [100, 40], [10, 40]],
                    "中文",
                    0.95,
                )
            ]

            with patch("epub2kr.image_translator.ImageTranslator._get_reader") as mock_get_reader:
                mock_reader = MagicMock()
                mock_reader.readtext.return_value = ocr_region
                mock_get_reader.return_value = mock_reader

                # First pass populates translation cache
                book1 = make_book()
                pref1 = translator._prefetch_image_regions(book1, "zh-cn")
                translator._translate_images(book1, pref1, show_progress=False)
                assert mock_service.translate.call_count >= 1

                # Second pass should reuse cached translations (no service call)
                mock_service.translate.reset_mock()
                book2 = make_book()
                pref2 = translator._prefetch_image_regions(book2, "zh-cn")
                translator._translate_images(book2, pref2, show_progress=False)
                mock_service.translate.assert_not_called()

    def test_translate_images_skips_resume_done_files(self, mock_service):
        with patch('epub2kr.translator.get_service') as mock_get_service:
            mock_get_service.return_value = mock_service
            translator = EpubTranslator(service_name="google", source_lang="en", target_lang="ko", use_cache=False)

            img = Image.new("RGB", (200, 200), color=(255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_item = epub.EpubImage(
                uid="img1",
                file_name="images/p1.png",
                media_type="image/png",
                content=buf.getvalue(),
            )
            book = MagicMock()
            book.get_items.return_value = [img_item]

            with patch("epub2kr.image_translator.ImageTranslator.process_image") as mock_process:
                processed, skipped, errors, total = translator._translate_images(
                    book,
                    prefetched_regions={},
                    show_progress=False,
                    resume_done_files={"images/p1.png"},
                )
                assert (processed, skipped, errors, total) == (0, 1, 0, 1)
                mock_process.assert_not_called()
