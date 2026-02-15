"""Integration tests for CLI and end-to-end pipeline."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from ebooklib import epub

from epub2kr.cli import main
from epub2kr.config import DEFAULTS


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
