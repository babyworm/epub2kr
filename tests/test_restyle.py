"""Tests for epub2kr restyle and GUI modules."""
import re
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from ebooklib import epub

from epub2kr.restyle import restyle_epub, main as restyle_main
from epub2kr.gui import (
    _extract_body_html,
    _get_current_css,
    FONT_PRESETS,
)
from epub2kr.translator import CJK_FONT_STACKS


# --- Fixtures ---

@pytest.fixture
def sample_epub(tmp_path):
    """Create a minimal EPUB for restyle testing."""
    book = epub.EpubBook()
    book.set_identifier("restyle-test-001")
    book.set_title("Restyle Test")
    book.set_language("ko")
    book.add_author("Test")

    ch1 = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="ko", uid="ch1")
    ch1.set_content(b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Ch1</title></head>
<body>
<h1>Test Heading</h1>
<p>First paragraph.</p>
<p>Second paragraph.</p>
</body>
</html>""")
    book.add_item(ch1)

    book.toc = [epub.Link("ch1.xhtml", "Chapter 1", uid="ch1_link")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", "ch1"]

    path = tmp_path / "test.epub"
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def epub_with_cjk_css(tmp_path):
    """Create an EPUB that already has a cjk.css stylesheet."""
    book = epub.EpubBook()
    book.set_identifier("restyle-css-test")
    book.set_title("CSS Test")
    book.set_language("ko")

    ch1 = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="ko", uid="ch1")
    ch1.set_content(b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Ch1</title></head>
<body><h2>Heading</h2><p>Text.</p></body>
</html>""")
    ch1.add_link(href='style/cjk.css', rel='stylesheet', type='text/css')
    book.add_item(ch1)

    css_content = (
        'body {\n'
        '  font-family: "Noto Sans KR", sans-serif;\n'
        '  font-size: 0.95em;\n'
        '  line-height: 1.8;\n'
        '}\n'
        'p {\n'
        '  margin-bottom: 0.5em;\n'
        '}\n'
        'h1, h2, h3, h4, h5, h6 {\n'
        '  font-family: "Noto Serif KR", serif;\n'
        '}\n'
    )
    css_item = epub.EpubItem(
        uid='style_cjk', file_name='style/cjk.css',
        media_type='text/css', content=css_content.encode('utf-8'),
    )
    book.add_item(css_item)

    book.toc = [epub.Link("ch1.xhtml", "Chapter 1", uid="ch1_link")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", "ch1"]

    path = tmp_path / "with_css.epub"
    epub.write_epub(str(path), book)
    return path


# --- restyle_epub tests ---

class TestRestyleEpub:
    def test_basic_restyle_creates_output(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        result = restyle_epub(str(sample_epub), str(output))
        assert result == str(output)
        assert output.exists()

    def test_default_css_contains_body_and_paragraph(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output))

        book = epub.read_epub(str(output))
        css = None
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                break

        assert css is not None
        assert 'font-size: 0.95em;' in css
        assert 'line-height: 1.8;' in css
        assert 'margin-bottom: 0.5em;' in css

    def test_custom_font_size_and_line_height(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output), font_size='1.1em', line_height='2.2')

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'font-size: 1.1em;' in css
                assert 'line-height: 2.2;' in css
                break

    def test_custom_paragraph_spacing(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output), paragraph_spacing='1.5em')

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'margin-bottom: 1.5em;' in css
                break

    def test_heading_font_family(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(
            str(sample_epub), str(output),
            heading_font_family='"Noto Serif KR", serif',
        )

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'h1, h2, h3, h4, h5, h6' in css
                assert '"Noto Serif KR", serif' in css
                break

    def test_no_heading_font_omits_heading_rule(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output))

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'h1, h2, h3, h4, h5, h6' not in css
                break

    def test_replaces_existing_css(self, epub_with_cjk_css, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(
            str(epub_with_cjk_css), str(output),
            font_size='1.2em', line_height='2.5', paragraph_spacing='1em',
        )

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'font-size: 1.2em;' in css
                assert 'line-height: 2.5;' in css
                assert 'margin-bottom: 1em;' in css
                # Old values should not be present
                assert 'font-size: 0.95em;' not in css
                break

    def test_auto_detects_language_from_metadata(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output))

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                # Korean EPUB should get Korean font stack
                assert 'Noto Sans KR' in css
                break

    def test_lang_override(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output), lang='ja')

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert 'Noto Sans JP' in css
                break

    def test_custom_font_family_override(self, sample_epub, tmp_path):
        output = tmp_path / "restyled.epub"
        restyle_epub(str(sample_epub), str(output), font_family='"Custom Font", serif')

        book = epub.read_epub(str(output))
        for item in book.get_items():
            if item.get_name() == 'style/cjk.css':
                css = item.get_content().decode('utf-8')
                assert '"Custom Font", serif' in css
                break


# --- GUI helper tests ---

class TestExtractBodyHtml:
    def test_extracts_body_content(self):
        xhtml = b"""<?xml version="1.0" encoding="utf-8"?>
<html><head><title>T</title></head>
<body><h1>Title</h1><p>Text</p></body></html>"""
        result = _extract_body_html(xhtml)
        assert '<h1>' in result
        assert '<p>' in result
        assert 'Title' in result
        assert 'Text' in result

    def test_empty_body_returns_empty(self):
        xhtml = b"""<html><body></body></html>"""
        result = _extract_body_html(xhtml)
        assert result == ""

    def test_invalid_content_returns_empty(self):
        result = _extract_body_html(b"not xml at all")
        # Should not raise, returns whatever it can parse or empty
        assert isinstance(result, str)


class TestGetCurrentCss:
    def test_reads_all_settings(self, epub_with_cjk_css):
        book = epub.read_epub(str(epub_with_cjk_css))
        settings = _get_current_css(book)

        assert settings['font_size'] == '0.95em'
        assert settings['line_height'] == '1.8'
        assert 'Noto Sans KR' in settings['font_family']
        assert settings['paragraph_spacing'] == '0.5em'
        assert 'Noto Serif KR' in settings['heading_font_family']

    def test_defaults_when_no_css(self, sample_epub):
        book = epub.read_epub(str(sample_epub))
        settings = _get_current_css(book)

        assert settings['font_size'] == '0.95em'
        assert settings['line_height'] == '1.8'
        assert settings['font_family'] == ''
        assert settings['paragraph_spacing'] == '0.5em'
        assert settings['heading_font_family'] == ''


class TestFontPresets:
    def test_korean_presets_exist(self):
        assert 'ko' in FONT_PRESETS
        ko_fonts = FONT_PRESETS['ko']
        assert len(ko_fonts) >= 4
        labels = [f['label'] for f in ko_fonts]
        assert any('Noto Sans' in l for l in labels)
        assert any('Noto Serif' in l or '명조' in l for l in labels)
        assert any('나눔고딕' in l for l in labels)
        assert any('나눔명조' in l for l in labels)

    def test_all_cjk_languages_have_presets(self):
        for lang in ['ko', 'ja', 'zh', 'zh-cn', 'zh-tw']:
            assert lang in FONT_PRESETS, f"Missing presets for {lang}"
            assert len(FONT_PRESETS[lang]) >= 2

    def test_presets_have_value_and_label(self):
        for lang, presets in FONT_PRESETS.items():
            for preset in presets:
                assert 'value' in preset, f"Missing value in {lang} preset"
                assert 'label' in preset, f"Missing label in {lang} preset"


# --- CLI tests ---

class TestRestyleCLI:
    def test_help_option(self):
        runner = CliRunner()
        result = runner.invoke(restyle_main, ['-h'])
        assert result.exit_code == 0
        assert '--gui' in result.output
        assert '--heading-font' in result.output
        assert '--paragraph-spacing' in result.output

    def test_basic_restyle(self, sample_epub, tmp_path):
        output = tmp_path / "out.epub"
        runner = CliRunner()
        result = runner.invoke(restyle_main, [
            str(sample_epub), '-o', str(output),
        ])
        assert result.exit_code == 0
        assert 'Done!' in result.output
        assert output.exists()

    def test_restyle_with_heading_font(self, sample_epub, tmp_path):
        output = tmp_path / "out.epub"
        runner = CliRunner()
        result = runner.invoke(restyle_main, [
            str(sample_epub), '-o', str(output),
            '--heading-font', '"Noto Serif KR", serif',
        ])
        assert result.exit_code == 0
        assert 'Heading:' in result.output
        assert 'Noto Serif KR' in result.output

    def test_restyle_with_paragraph_spacing(self, sample_epub, tmp_path):
        output = tmp_path / "out.epub"
        runner = CliRunner()
        result = runner.invoke(restyle_main, [
            str(sample_epub), '-o', str(output),
            '--paragraph-spacing', '1.2em',
        ])
        assert result.exit_code == 0
        assert 'spacing=1.2em' in result.output

    def test_inplace_and_output_conflict(self, sample_epub):
        runner = CliRunner()
        result = runner.invoke(restyle_main, [
            str(sample_epub), '--inplace', '-o', 'other.epub',
        ])
        assert result.exit_code != 0

    def test_default_output_name(self, sample_epub):
        runner = CliRunner()
        result = runner.invoke(restyle_main, [str(sample_epub)])
        assert result.exit_code == 0
        assert '.restyled.epub' in result.output

    def test_gui_option_exists(self):
        runner = CliRunner()
        result = runner.invoke(restyle_main, ['-h'])
        assert '--gui' in result.output
