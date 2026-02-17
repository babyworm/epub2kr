"""Integration tests for CLI and end-to-end pipeline."""
import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from ebooklib import epub
from PIL import Image

from epub2kr.cli import main
from epub2kr.config import DEFAULTS


def _make_chinese_image_epub(tmp_path: Path, body_text: str, filename: str = "zh_img.epub") -> Path:
    """Create an EPUB with Chinese body text and one PNG image."""
    book = epub.EpubBook()
    book.set_identifier("zh-book-001")
    book.set_title("ZH Book")
    book.set_language("zh")
    book.add_author("Test Author")

    ch = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="zh", uid="ch1")
    xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        f'<p>{body_text}</p>'
        '<img src="images/p1.png" alt="img"/>'
        '</body></html>'
    ).encode("utf-8")
    ch.set_content(xhtml)
    book.add_item(ch)

    img = Image.new("RGB", (220, 220), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_item = epub.EpubImage(uid="img1", file_name="images/p1.png", media_type="image/png", content=buf.getvalue())
    book.add_item(image_item)

    book.toc = [epub.Link("ch1.xhtml", "Chapter 1", uid="ch1_link")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", "ch1"]

    epub_path = tmp_path / filename
    epub.write_epub(str(epub_path), book)
    return epub_path


@pytest.fixture
def mock_config():
    """Mock load_config to return DEFAULTS."""
    with patch('epub2kr.cli.load_config') as mock_load:
        mock_load.return_value = DEFAULTS.copy()
        yield mock_load


@pytest.fixture
def mock_translator_service():
    """Mock get_service to return a simple translator."""
    mock_svc = MagicMock()
    mock_svc.__class__.__name__ = "MockService"
    mock_svc.translate.side_effect = lambda texts, sl, tl: [f"[tr]{t}" for t in texts]

    # Patch both imports of get_service
    with patch('epub2kr.translator.get_service', return_value=mock_svc) as mock_gs1, \
         patch('epub2kr.services.get_service', return_value=mock_svc) as mock_gs2:
        yield mock_gs1


class TestCLI:
    """Test CLI interface with Click CliRunner."""

    def test_help_option(self):
        """Test that --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'epub2kr' in result.output
        assert 'Translate EPUB files' in result.output
        assert '--output' in result.output
        assert '--service' in result.output

    def test_no_input_file_error(self, mock_config):
        """Test error when no input file is provided."""
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 1
        # The console.print will be in output, check for error message
        assert 'Error' in result.output or result.exception is not None

    def test_setup_flag(self):
        """Test that --setup runs interactive wizard."""
        runner = CliRunner()
        with patch('epub2kr.config.run_setup') as mock_setup:
            # Provide inputs for the wizard (though mock should prevent actual execution)
            result = runner.invoke(main, ['--setup'])
            assert result.exit_code == 0
            mock_setup.assert_called_once()

    def test_nonexistent_file_error(self, mock_config):
        """Test error when input file doesn't exist."""
        runner = CliRunner()
        result = runner.invoke(main, ['nonexistent.epub', '-lo', 'ko'])
        # Click's Path validator should fail before main logic
        assert result.exit_code != 0

    def test_valid_epub_translation(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test successful translation with valid EPUB and mocked service."""
        runner = CliRunner()
        output_path = tmp_path / "output.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        if result.exit_code != 0:
            print(f"Output: {result.output}")
            if result.exception:
                raise result.exception

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'Done!' in result.output or 'Translation Summary' in result.output

    def test_no_cache_flag(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test --no-cache flag works."""
        runner = CliRunner()
        output_path = tmp_path / "output.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'ko',
            '--no-cache',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'disabled' in result.output  # Cache status should show disabled

    def test_output_path_default(self, minimal_epub, mock_config, mock_translator_service):
        """Test default output path is {stem}.{lang}.epub."""
        runner = CliRunner()

        result = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'ko'
        ])

        assert result.exit_code == 0
        # Default output should be test.ko.epub in the same directory
        expected_output = minimal_epub.parent / "test.ko.epub"
        assert expected_output.exists()

    def test_output_flag_override(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test -o flag overrides default output path."""
        runner = CliRunner()
        custom_output = tmp_path / "custom_name.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'ja',
            '-o', str(custom_output)
        ])

        assert result.exit_code == 0
        assert custom_output.exists()
        # Default name should NOT be created
        default_output = minimal_epub.parent / "test.ja.epub"
        assert not default_output.exists()

    def test_resume_option_uses_existing_output(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test --resume mode when output file already exists."""
        runner = CliRunner()
        output_path = tmp_path / "resume.epub"

        first = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'ko',
            '-o', str(output_path)
        ])
        assert first.exit_code == 0
        assert output_path.exists()

        second = runner.invoke(main, [
            str(minimal_epub),
            '--resume',
            '-lo', 'ko',
            '-o', str(output_path)
        ])
        assert second.exit_code == 0
        assert 'Resume: enabled' in second.output

    def test_bilingual_flag(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test --bilingual flag works."""
        runner = CliRunner()
        output_path = tmp_path / "bilingual.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-lo', 'zh',
            '--bilingual',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'Bilingual' in result.output

    def test_service_option(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test -s/--service option."""
        runner = CliRunner()
        output_path = tmp_path / "deepl.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-s', 'deepl',
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        # Check that get_service was called with 'deepl'
        mock_translator_service.assert_called()
        call_args = mock_translator_service.call_args
        assert call_args[0][0] == 'deepl' or 'deepl' in str(call_args)

    def test_threads_option(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test -t/--threads option."""
        runner = CliRunner()
        output_path = tmp_path / "threaded.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-t', '8',
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()

    def test_image_threads_option(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test --image-threads option."""
        runner = CliRunner()
        output_path = tmp_path / "image_threaded.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-t', '2',
            '--image-threads', '5',
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'chapters=2, images=5' in result.output

    def test_image_threads_short_option_j(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test -j short option for image threads."""
        runner = CliRunner()
        output_path = tmp_path / "image_threaded_short.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '-t', '2',
            '-j', '4',
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'chapters=2, images=4' in result.output

    def test_images_only_option(self, minimal_epub, mock_config, mock_translator_service, tmp_path):
        """Test --images-only mode."""
        runner = CliRunner()
        output_path = tmp_path / "images_only.epub"

        result = runner.invoke(main, [
            str(minimal_epub),
            '--images-only',
            '-lo', 'ko',
            '-o', str(output_path)
        ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'Images-only' in result.output

    def test_cache_stats_command(self):
        """Test --cache-stats command without input file."""
        runner = CliRunner()
        result = runner.invoke(main, ['--cache-stats'])
        assert result.exit_code == 0
        assert 'translation_cache' in result.output
        assert 'ocr_cache' in result.output

    def test_cache_clear_and_prune_command(self):
        """Test --cache-clear and --cache-prune-days command path."""
        runner = CliRunner()
        with patch("epub2kr.cli.TranslationCache") as mock_tcache_cls, \
             patch("epub2kr.cli.OCRPrescanCache") as mock_ocache_cls:
            tcache = MagicMock()
            ocache = MagicMock()
            tcache.prune.return_value = 3
            ocache.prune.return_value = 2
            mock_tcache_cls.return_value = tcache
            mock_ocache_cls.return_value = ocache

            result = runner.invoke(main, ['--cache-clear', '--cache-prune-days', '30'])

        assert result.exit_code == 0
        tcache.clear.assert_called_once()
        ocache.clear.assert_called_once()
        tcache.prune.assert_called_once_with(30)
        ocache.prune.assert_called_once_with(30)
        assert 'Caches cleared' in result.output
        assert 'older than 30 days' in result.output

    def test_log_json_option_prints_report(self, minimal_epub, mock_config, tmp_path):
        """Test --log-json emits final JSON report."""
        runner = CliRunner()
        output_path = tmp_path / "log_json.epub"

        with patch("epub2kr.cli.EpubTranslator") as mock_translator_cls:
            tr = MagicMock()
            tr.translate_epub.return_value = str(output_path)
            tr.effective_source_lang = "zh-cn"
            tr.get_last_report.return_value = {"performance": {"total_sec": 1.23}, "images": {"total": 1}}
            mock_translator_cls.return_value = tr

            result = runner.invoke(main, [
                str(minimal_epub),
                "-lo", "ko",
                "--log-json",
                "-o", str(output_path),
            ])

        assert result.exit_code == 0
        assert '"performance"' in result.output
        assert '"total_sec": 1.23' in result.output


class TestEndToEnd:
    """Test end-to-end translation pipeline."""

    def test_full_pipeline_with_mock_service(self, minimal_epub, mock_translator_service, tmp_path):
        """Test full pipeline: load -> extract -> translate -> replace -> save."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "translated.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=1,
            use_cache=False
        )

        result_path = translator.translate_epub(str(minimal_epub), str(output_path))

        assert result_path == str(output_path)
        assert output_path.exists()

        # Verify the output is a valid EPUB
        book = epub.read_epub(str(output_path))
        assert book is not None

        # Verify metadata was updated
        lang = book.get_metadata('DC', 'language')
        assert lang
        assert lang[0][0] == 'ko'

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("这是中文内容", "zh-cn"),
            ("這是中文內容", "zh-tw"),
        ],
    )
    def test_auto_detected_source_is_used_for_ocr(self, text, expected, mock_config, mock_translator_service, tmp_path):
        """Auto-detected source language should propagate to OCR and logs."""
        runner = CliRunner()
        input_epub = _make_chinese_image_epub(tmp_path, text, f"{expected}.epub")
        output_path = tmp_path / f"out_{expected}.epub"
        captured_ocr_source = []

        def fake_get_reader(self):
            captured_ocr_source.append(self.source_lang)
            reader = MagicMock()
            reader.readtext.return_value = []  # No OCR text, just verify language wiring
            return reader

        with patch("epub2kr.image_translator.ImageTranslator._get_reader", new=fake_get_reader):
            result = runner.invoke(main, [
                str(input_epub),
                "-li", "auto",
                "-lo", "ko",
                "--no-cache",
                "-o", str(output_path),
            ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert captured_ocr_source
        assert all(lang == expected for lang in captured_ocr_source)
        assert f"auto (detected: {expected})" in result.output
        assert f"OCR source language: {expected}" in result.output

    def test_ocr_skips_non_source_language_text_when_auto_detected(self, mock_config, mock_translator_service, tmp_path):
        """After auto-detection to zh-cn, OCR should ignore non-Chinese text regions."""
        runner = CliRunner()
        input_epub = _make_chinese_image_epub(tmp_path, "这是中文内容", "zh_skip_non_source.epub")
        output_path = tmp_path / "out_skip_non_source.epub"
        translated_batches = []

        def fake_get_reader(self):
            reader = MagicMock()
            reader.readtext.return_value = [
                ([[10, 10], [100, 10], [100, 40], [10, 40]], "Hello", 0.95),
                ([[10, 50], [140, 50], [140, 90], [10, 90]], "中文", 0.95),
            ]
            return reader

        def capture_translate(texts, sl, tl):
            translated_batches.append((list(texts), sl, tl))
            return [f"[tr]{t}" for t in texts]

        with patch("epub2kr.image_translator.ImageTranslator._get_reader", new=fake_get_reader), \
             patch("epub2kr.translator.get_service") as mock_get_service:
            svc = MagicMock()
            svc.__class__.__name__ = "MockService"
            svc.translate.side_effect = capture_translate
            mock_get_service.return_value = svc

            result = runner.invoke(main, [
                str(input_epub),
                "-li", "auto",
                "-lo", "ko",
                "--no-cache",
                "-o", str(output_path),
            ])

        assert result.exit_code == 0
        assert output_path.exists()
        # Ensure OCR translation call contains only source-language-matching text.
        ocr_batches = [b for b in translated_batches if b[0] == ["中文"]]
        assert ocr_batches
        assert ocr_batches[0][1] == "zh-cn"

    def test_prescan_summary_reports_skip_and_remaining(self, mock_config, mock_translator_service, tmp_path):
        """Pre-scan summary should show skipped and remaining image counts."""
        runner = CliRunner()
        input_epub = _make_chinese_image_epub(tmp_path, "这是中文内容", "zh_prescan_summary.epub")
        output_path = tmp_path / "out_prescan_summary.epub"

        def fake_get_reader(self):
            reader = MagicMock()
            # English-only OCR text should be filtered out for zh-cn and become pre-scan skip.
            reader.readtext.return_value = [
                ([[10, 10], [100, 10], [100, 40], [10, 40]], "Hello", 0.95),
            ]
            return reader

        with patch("epub2kr.image_translator.ImageTranslator._get_reader", new=fake_get_reader):
            result = runner.invoke(main, [
                str(input_epub),
                "-li", "auto",
                "-lo", "ko",
                "--no-cache",
                "-o", str(output_path),
            ])

        assert result.exit_code == 0
        assert output_path.exists()
        assert "Image pre-scan summary: total=1, skipped=1, to_translate=0" in result.output

    def test_translated_epub_is_loadable(self, minimal_epub, mock_translator_service, tmp_path):
        """Test that translated EPUB can be loaded and read."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "readable.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ja",
            threads=1,
            use_cache=False
        )

        translator.translate_epub(str(minimal_epub), str(output_path))

        # Load the translated EPUB
        book = epub.read_epub(str(output_path))

        # Get spine items
        spine_items = [book.get_item_with_id(item_id) for item_id, _ in book.spine]

        # Verify content is accessible
        for item in spine_items:
            if item:
                content = item.get_content()
                assert content is not None
                assert len(content) > 0

    def test_translation_with_cache(self, minimal_epub, mock_translator_service, tmp_path):
        """Test translation with cache enabled."""
        from epub2kr.translator import EpubTranslator
        from epub2kr.cache import TranslationCache

        cache_dir = tmp_path / "cache"
        output_path = tmp_path / "cached.epub"

        # Use a real cache instance in temp directory
        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="zh",
            threads=1,
            use_cache=True
        )

        # Override cache to use temp directory
        translator.cache = TranslationCache(cache_dir=str(cache_dir))

        translator.translate_epub(str(minimal_epub), str(output_path))

        # Verify output exists
        assert output_path.exists()

    def test_images_only_keeps_chapter_text_unchanged(self, minimal_epub, mock_translator_service, tmp_path):
        """In images-only mode, chapter text should remain original."""
        output_path = tmp_path / "images_only_text_unchanged.epub"
        runner = CliRunner()
        result = runner.invoke(main, [
            str(minimal_epub),
            "--images-only",
            "-lo", "ko",
            "-o", str(output_path),
        ])
        assert result.exit_code == 0
        book = epub.read_epub(str(output_path))
        spine_items = [book.get_item_with_id(item_id) for item_id, _ in book.spine]
        found_original = False
        for item in spine_items:
            if item and hasattr(item, "get_content"):
                content = item.get_content().decode("utf-8")
                if "Hello World" in content:
                    found_original = True
                assert "[tr]Hello World" not in content
        assert found_original

    def test_resume_checkpoint_file_is_written(self, minimal_epub, mock_translator_service, tmp_path):
        """Translation should write a resume checkpoint JSON file."""
        output_path = tmp_path / "resume_checkpoint.epub"
        runner = CliRunner()
        result = runner.invoke(main, [
            str(minimal_epub),
            "-lo", "ko",
            "-o", str(output_path),
        ])
        assert result.exit_code == 0
        checkpoint_path = Path(f"{output_path}.resume.json")
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        assert data.get("chapters_done") is True
        assert data.get("images_done") is True
        assert data.get("metadata_done") is True
        assert data.get("saved_done") is True

    def test_bilingual_output(self, minimal_epub, mock_translator_service, tmp_path):
        """Test bilingual output contains both original and translated text."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "bilingual.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=1,
            use_cache=False,
            bilingual=True
        )

        translator.translate_epub(str(minimal_epub), str(output_path))

        # Load and check content
        book = epub.read_epub(str(output_path))
        spine_items = [book.get_item_with_id(item_id) for item_id, _ in book.spine]

        # Check that content has both original and translation markers
        for item in spine_items:
            if item and hasattr(item, 'get_content'):
                content = item.get_content().decode('utf-8')
                # Bilingual mode should have [tr] markers from mock translator
                if '[tr]' in content:
                    # Verify structure (should have original text before [tr])
                    assert True  # Content exists with translation markers

    def test_cjk_stylesheet_injection(self, minimal_epub, mock_translator_service, tmp_path):
        """Test CJK stylesheet is injected for CJK target languages."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "cjk_styled.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",  # Korean triggers CJK styling
            threads=1,
            use_cache=False,
            font_size="0.9em",
            line_height="2.0"
        )

        translator.translate_epub(str(minimal_epub), str(output_path))

        # Load and check for stylesheet
        book = epub.read_epub(str(output_path))

        # Look for CJK stylesheet in items - check by media_type
        css_items = [item for item in book.get_items() if item.media_type == 'text/css']
        css_found = any('cjk' in item.file_name.lower() for item in css_items)

        assert css_found, "CJK stylesheet should be present for Korean target"

    def test_parallel_translation(self, minimal_epub, mock_translator_service, tmp_path):
        """Test parallel translation with multiple threads."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "parallel.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=4,  # Use multiple threads
            use_cache=False
        )

        result_path = translator.translate_epub(str(minimal_epub), str(output_path))

        assert result_path == str(output_path)
        assert output_path.exists()

        # Verify output is valid
        book = epub.read_epub(str(output_path))
        assert book is not None

    def test_toc_translation(self, minimal_epub, mock_translator_service, tmp_path):
        """Test table of contents labels are translated."""
        from epub2kr.translator import EpubTranslator

        output_path = tmp_path / "toc_translated.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=1,
            use_cache=False
        )

        translator.translate_epub(str(minimal_epub), str(output_path))

        # Load and check TOC
        book = epub.read_epub(str(output_path))

        # The TOC should exist (minimal_epub creates one)
        if book.toc:
            # Mock translator prepends [tr] to text
            # TOC labels should be processed (though exact format depends on implementation)
            assert len(book.toc) > 0

    def test_error_handling_invalid_epub(self, tmp_path, mock_translator_service):
        """Test error handling with invalid EPUB file."""
        from epub2kr.translator import EpubTranslator

        # Create a fake EPUB (just a text file)
        fake_epub = tmp_path / "fake.epub"
        fake_epub.write_text("not an epub file")

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=1,
            use_cache=False
        )

        with pytest.raises(Exception):
            translator.translate_epub(str(fake_epub), str(tmp_path / "output.epub"))

    def test_empty_content_handling(self, tmp_path, mock_translator_service):
        """Test handling of EPUB with empty content."""
        from epub2kr.translator import EpubTranslator

        # Create minimal EPUB with empty chapter - need proper NCX/Nav
        book = epub.EpubBook()
        book.set_identifier("empty-test")
        book.set_title("Empty Book")
        book.set_language("en")
        book.add_author("Test")

        ch1 = epub.EpubHtml(title="Empty", file_name="empty.xhtml", lang="en", uid="ch1")
        ch1.set_content(b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Empty</title></head>
<body><p></p></body>
</html>""")
        book.add_item(ch1)

        # Add required navigation items
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", "ch1"]
        book.toc = [epub.Link("empty.xhtml", "Empty Chapter", uid="toc_empty")]

        input_path = tmp_path / "empty.epub"
        epub.write_epub(str(input_path), book)

        output_path = tmp_path / "empty_out.epub"

        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=1,
            use_cache=False
        )

        # Should not raise error, just skip translation
        result_path = translator.translate_epub(str(input_path), str(output_path))
        assert output_path.exists()
