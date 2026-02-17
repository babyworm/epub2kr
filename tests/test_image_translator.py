"""Tests for ImageTranslator (OCR-based image text translation)."""
import io
import sys
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from epub2kr.image_translator import (
    ImageTranslator,
    OCRRegion,
    EASYOCR_LANG_MAP,
    SUPPORTED_MEDIA_TYPES,
    MIN_IMAGE_DIMENSION,
    AUTO_OCR_LANGS,
)


# --- OCRRegion tests ---

class TestOCRRegion:
    def test_bbox_to_rectangle(self):
        """bbox polygon coordinates should compute x, y, width, height."""
        region = OCRRegion(
            bbox=[[10, 20], [110, 20], [110, 60], [10, 60]],
            text="hello",
            confidence=0.9,
        )
        assert region.x == 10
        assert region.y == 20
        assert region.width == 100
        assert region.height == 40

    def test_irregular_polygon(self):
        """Non-rectangular polygon should use bounding box of all points."""
        region = OCRRegion(
            bbox=[[5, 10], [100, 15], [95, 50], [10, 55]],
            text="test",
            confidence=0.8,
        )
        assert region.x == 5
        assert region.y == 10
        assert region.width == 95
        assert region.height == 45


# --- can_process tests ---

class TestCanProcess:
    def test_png_supported(self):
        translator = ImageTranslator()
        assert translator.can_process('image/png') is True

    def test_jpeg_supported(self):
        translator = ImageTranslator()
        assert translator.can_process('image/jpeg') is True

    def test_svg_not_supported(self):
        translator = ImageTranslator()
        assert translator.can_process('image/svg+xml') is False

    def test_gif_not_supported(self):
        translator = ImageTranslator()
        assert translator.can_process('image/gif') is False

    def test_webp_not_supported(self):
        translator = ImageTranslator()
        assert translator.can_process('image/webp') is False


# --- process_image tests ---

class TestProcessImage:
    def _make_mock_reader(self, ocr_results):
        """Create a mock EasyOCR reader returning given results."""
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ocr_results
        return mock_reader

    def test_tiny_image_skipped(self, tiny_image):
        """Images smaller than MIN_IMAGE_DIMENSION should return None."""
        translator = ImageTranslator()
        result = translator.process_image(
            tiny_image, 'image/png', lambda texts: texts
        )
        assert result is None

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_no_text_returns_none(self, mock_get_reader, image_without_text):
        """Image with no detected text should return None."""
        mock_get_reader.return_value = self._make_mock_reader([])
        translator = ImageTranslator()
        result = translator.process_image(
            image_without_text, 'image/png', lambda texts: texts
        )
        assert result is None

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_text_detected_and_translated(self, mock_get_reader, image_with_text):
        """Image with detected text should return modified bytes."""
        ocr_results = [
            ([[50, 80], [200, 80], [200, 110], [50, 110]], "Hello World", 0.95),
        ]
        mock_get_reader.return_value = self._make_mock_reader(ocr_results)

        def mock_translate(texts):
            return [f"[translated]{t}" for t in texts]

        translator = ImageTranslator(target_lang='ko')
        result = translator.process_image(
            image_with_text, 'image/png', mock_translate
        )
        assert result is not None
        assert len(result) > 0
        # Verify it's still a valid PNG
        img = Image.open(io.BytesIO(result))
        assert img.format == 'PNG'

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_jpeg_format_preserved(self, mock_get_reader):
        """JPEG input should produce JPEG output."""
        # Create a JPEG image
        img = Image.new('RGB', (200, 200), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        jpeg_bytes = buf.getvalue()

        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Test", 0.9),
        ]
        mock_get_reader.return_value = self._make_mock_reader(ocr_results)

        translator = ImageTranslator()
        result = translator.process_image(
            jpeg_bytes, 'image/jpeg', lambda texts: [f"T-{t}" for t in texts]
        )
        assert result is not None
        img_out = Image.open(io.BytesIO(result))
        assert img_out.format == 'JPEG'

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_rgba_image_handled(self, mock_get_reader):
        """RGBA images should be processable."""
        img = Image.new('RGBA', (200, 200), color=(255, 255, 255, 128))
        buf = io.BytesIO()
        img.save(buf, format='PNG')

        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Alpha", 0.85),
        ]
        mock_get_reader.return_value = self._make_mock_reader(ocr_results)

        translator = ImageTranslator()
        result = translator.process_image(
            buf.getvalue(), 'image/png', lambda texts: [f"T:{t}" for t in texts]
        )
        assert result is not None

    @patch('epub2kr.image_translator.ImageTranslator._detect_text')
    def test_process_image_uses_prefetched_regions(self, mock_detect_text, image_with_text):
        """When regions are provided, OCR detection should not run again."""
        translator = ImageTranslator(source_lang='zh-cn')
        regions = [
            OCRRegion(
                bbox=[[50, 80], [200, 80], [200, 110], [50, 110]],
                text="中文",
                confidence=0.95,
            )
        ]
        result = translator.process_image(
            image_with_text,
            'image/png',
            lambda texts: [f"[tr]{t}" for t in texts],
            regions=regions,
        )
        assert result is not None
        mock_detect_text.assert_not_called()

    def test_same_translation_returns_none(self, image_with_text):
        """If translation is effectively identical, image should not be rewritten."""
        translator = ImageTranslator(source_lang='en')
        regions = [
            OCRRegion(
                bbox=[[50, 80], [200, 80], [200, 110], [50, 110]],
                text="Hello  World",
                confidence=0.95,
            )
        ]
        result = translator.process_image(
            image_with_text,
            'image/png',
            lambda texts: ["hello world"],
            regions=regions,
        )
        assert result is None


# --- Confidence filtering tests ---

class TestConfidenceFiltering:
    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_low_confidence_filtered(self, mock_get_reader, image_with_text):
        """Text with confidence below threshold should be filtered out."""
        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Low conf", 0.1),
            ([[10, 50], [100, 50], [100, 80], [10, 80]], "High conf", 0.9),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        translator = ImageTranslator(confidence_threshold=0.3)

        calls = []
        def capture_translate(texts):
            calls.append(texts)
            return [f"T:{t}" for t in texts]

        translator.process_image(image_with_text, 'image/png', capture_translate)
        # Only "High conf" should be passed to translate
        assert len(calls) == 1
        assert calls[0] == ["High conf"]

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_all_below_threshold_returns_none(self, mock_get_reader, image_with_text):
        """If all detections are below threshold, return None."""
        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Low", 0.1),
            ([[10, 50], [100, 50], [100, 80], [10, 80]], "Also low", 0.2),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        translator = ImageTranslator(confidence_threshold=0.3)
        result = translator.process_image(
            image_with_text, 'image/png', lambda texts: texts
        )
        assert result is None

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_source_lang_filter_skips_non_matching_scripts(self, mock_get_reader, image_with_text):
        """For Chinese source, non-Han OCR text should be ignored."""
        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Hello", 0.9),
            ([[10, 50], [140, 50], [140, 90], [10, 90]], "中文", 0.9),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        calls = []

        def capture_translate(texts):
            calls.append(texts)
            return [f"T:{t}" for t in texts]

        translator = ImageTranslator(source_lang='zh-cn')
        result = translator.process_image(image_with_text, 'image/png', capture_translate)

        assert result is not None
        assert calls == [["中文"]]

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_source_lang_filter_all_non_matching_returns_none(self, mock_get_reader, image_with_text):
        """If no OCR text matches source language script, image is skipped."""
        ocr_results = [
            ([[10, 10], [100, 10], [100, 40], [10, 40]], "Hello", 0.9),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        translator = ImageTranslator(source_lang='zh-cn')
        result = translator.process_image(image_with_text, 'image/png', lambda texts: texts)
        assert result is None

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_ocr_text_is_normalized_before_translation(self, mock_get_reader, image_with_text):
        """OCR text should be normalized (NFKC + whitespace cleanup)."""
        ocr_results = [
            ([[10, 10], [120, 10], [120, 40], [10, 40]], "  Hello\n   World  ", 0.9),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        captured = []

        def capture_translate(texts):
            captured.append(texts)
            return ["안녕하세요 세계"]

        translator = ImageTranslator(source_lang='en')
        translator.process_image(image_with_text, 'image/png', capture_translate)
        assert captured == [["Hello World"]]

    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_noise_only_ocr_text_is_skipped(self, mock_get_reader, image_with_text):
        """Punctuation-only OCR noise should not trigger translation."""
        ocr_results = [
            ([[10, 10], [30, 10], [30, 30], [10, 30]], "...", 0.95),
            ([[40, 40], [60, 40], [60, 60], [40, 60]], "—", 0.95),
        ]
        mock_get_reader.return_value = MagicMock()
        mock_get_reader.return_value.readtext.return_value = ocr_results

        translator = ImageTranslator(source_lang='en')
        result = translator.process_image(image_with_text, 'image/png', lambda texts: texts)
        assert result is None


# --- Font tests ---

class TestFontHandling:
    def test_fit_font_returns_font_and_text(self):
        """_fit_font should return a (font, text) tuple."""
        translator = ImageTranslator(target_lang='en')
        font, text = translator._fit_font("Hello", 200, 50)
        assert text == "Hello"
        assert font is not None

    def test_fit_font_minimum_size(self):
        """Very small box should still return a font (minimum size)."""
        translator = ImageTranslator(target_lang='en')
        font, text = translator._fit_font("A very long text that won't fit", 10, 10)
        assert font is not None

    @patch('epub2kr.image_translator.ImageTranslator._find_system_font')
    @patch('epub2kr.image_translator.ImageTranslator._fc_match_font')
    def test_find_font_fallback(self, mock_fc, mock_sys):
        """If no system font found, should gracefully handle it."""
        mock_sys.return_value = None
        mock_fc.return_value = None
        translator = ImageTranslator(target_lang='ko')
        translator._font_path = None  # Reset cache
        result = translator._find_font()
        # Should return None but not crash
        # (will use PIL default font)
        assert result is None or isinstance(result, str)


# --- Background sampling tests ---

class TestBackgroundSampling:
    def test_white_background(self):
        """White background should sample as approximately white."""
        img = Image.new('RGB', (200, 200), color=(255, 255, 255))
        region = OCRRegion(
            bbox=[[50, 50], [150, 50], [150, 150], [50, 150]],
            text="test", confidence=0.9
        )
        translator = ImageTranslator()
        bg = translator._sample_background(img, region)
        assert all(c > 240 for c in bg)

    def test_colored_background(self):
        """Colored background should sample as approximately that color."""
        img = Image.new('RGB', (200, 200), color=(100, 50, 150))
        region = OCRRegion(
            bbox=[[50, 50], [150, 50], [150, 150], [50, 150]],
            text="test", confidence=0.9
        )
        translator = ImageTranslator()
        bg = translator._sample_background(img, region)
        assert abs(bg[0] - 100) < 20
        assert abs(bg[1] - 50) < 20
        assert abs(bg[2] - 150) < 20


# --- Contrast color tests ---

class TestContrastColor:
    def test_dark_background_gives_white_text(self):
        translator = ImageTranslator()
        assert translator._contrast_color((0, 0, 0)) == (255, 255, 255)

    def test_light_background_gives_black_text(self):
        translator = ImageTranslator()
        assert translator._contrast_color((255, 255, 255)) == (0, 0, 0)

    def test_mid_dark_background(self):
        translator = ImageTranslator()
        # Luminance < 128 → white text
        assert translator._contrast_color((50, 50, 50)) == (255, 255, 255)

    def test_mid_light_background(self):
        translator = ImageTranslator()
        # Luminance > 128 → black text
        assert translator._contrast_color((200, 200, 200)) == (0, 0, 0)


# --- EasyOCR language mapping tests ---

class TestEasyOCRLangMap:
    def test_chinese_simplified(self):
        assert EASYOCR_LANG_MAP['zh'] == 'ch_sim'
        assert EASYOCR_LANG_MAP['zh-cn'] == 'ch_sim'

    def test_chinese_traditional(self):
        assert EASYOCR_LANG_MAP['zh-tw'] == 'ch_tra'

    def test_korean(self):
        assert EASYOCR_LANG_MAP['ko'] == 'ko'

    def test_japanese(self):
        assert EASYOCR_LANG_MAP['ja'] == 'ja'

    def test_english(self):
        assert EASYOCR_LANG_MAP['en'] == 'en'


class TestEasyOCRReaderLanguages:
    def test_auto_mode_uses_multilingual_ocr_languages(self):
        fake_easyocr = MagicMock()
        fake_easyocr.Reader.return_value = MagicMock()

        with patch.dict(sys.modules, {'easyocr': fake_easyocr}):
            translator = ImageTranslator(source_lang='auto')
            translator._get_reader()

        fake_easyocr.Reader.assert_called_once_with(list(AUTO_OCR_LANGS), gpu=False)

    def test_explicit_source_lang_adds_mapped_lang(self):
        fake_easyocr = MagicMock()
        fake_easyocr.Reader.return_value = MagicMock()

        with patch.dict(sys.modules, {'easyocr': fake_easyocr}):
            translator = ImageTranslator(source_lang='zh-cn')
            translator._get_reader()

        fake_easyocr.Reader.assert_called_once_with(['en', 'ch_sim'], gpu=False)


# --- Integration with translator ---

class TestTranslatorIntegration:
    @patch('epub2kr.image_translator.ImageTranslator._get_reader')
    def test_translate_images_disabled(self, mock_get_reader, minimal_epub, tmp_path):
        """When translate_images=False, OCR should not run."""
        from epub2kr.translator import EpubTranslator

        output = str(tmp_path / "out.epub")
        translator = EpubTranslator(
            service_name='google',
            source_lang='en',
            target_lang='ko',
            translate_images=False,
            use_cache=False,
        )
        # Mock the service to avoid real API calls
        translator.service = MagicMock()
        translator.service.__class__.__name__ = 'MockService'
        translator.service.translate.side_effect = lambda texts, s, t: [f"[ko]{x}" for x in texts]

        translator.translate_epub(str(minimal_epub), output)
        # EasyOCR reader should never be initialized
        mock_get_reader.assert_not_called()
