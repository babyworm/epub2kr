"""OCR-based image text translation for EPUB images."""
import io
import re
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Tuple

from PIL import Image, ImageDraw, ImageFont


# EasyOCR uses its own language codes
EASYOCR_LANG_MAP = {
    'zh': 'ch_sim',
    'zh-cn': 'ch_sim',
    'zh-tw': 'ch_tra',
    'ko': 'ko',
    'ja': 'ja',
    'en': 'en',
    'es': 'es',
    'fr': 'fr',
    'de': 'de',
    'ru': 'ru',
    'pt': 'pt',
    'it': 'it',
    'vi': 'vi',
    'th': 'th',
    'ar': 'ar',
    'hi': 'hi',
    'id': 'id',
    'nl': 'nl',
    'pl': 'pl',
    'tr': 'tr',
    'uk': 'uk',
}

# Font search paths per target language
FONT_PREFERENCES = {
    'ko': ['NanumGothic', 'NanumBarunGothic', 'Noto Sans KR', 'Noto Sans CJK KR', 'UnDotum', 'Malgun Gothic'],
    'ja': ['IPAGothic', 'IPAPGothic', 'Noto Sans JP', 'Noto Sans CJK JP', 'TakaoGothic'],
    'zh': ['Droid Sans Fallback', 'Noto Sans SC', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei'],
    'zh-cn': ['Droid Sans Fallback', 'Noto Sans SC', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei'],
    'zh-tw': ['Droid Sans Fallback', 'Noto Sans TC', 'Noto Sans CJK TC', 'WenQuanYi Micro Hei'],
}

SUPPORTED_MEDIA_TYPES = {'image/png', 'image/jpeg'}

MIN_IMAGE_DIMENSION = 100  # Skip images smaller than this (px)
AUTO_OCR_LANGS = ['en', 'ch_sim', 'ch_tra', 'ja', 'ko']


@dataclass
class OCRRegion:
    """A detected text region from OCR."""
    bbox: list  # EasyOCR polygon coordinates [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    text: str
    confidence: float
    # Bounding rectangle computed from polygon
    x: int = field(init=False)
    y: int = field(init=False)
    width: int = field(init=False)
    height: int = field(init=False)

    def __post_init__(self):
        xs = [pt[0] for pt in self.bbox]
        ys = [pt[1] for pt in self.bbox]
        self.x = int(min(xs))
        self.y = int(min(ys))
        self.width = int(max(xs) - self.x)
        self.height = int(max(ys) - self.y)


class ImageTranslator:
    """Translates text found in images using OCR."""

    def __init__(
        self,
        source_lang: str = "auto",
        target_lang: str = "en",
        confidence_threshold: float = 0.3,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.confidence_threshold = confidence_threshold
        self._reader = None
        self._font_path = None

    def can_process(self, media_type: str) -> bool:
        """Check if we can process this image type."""
        return media_type in SUPPORTED_MEDIA_TYPES

    def process_image(
        self,
        image_bytes: bytes,
        media_type: str,
        translate_func: Callable[[List[str]], List[str]],
        regions: Optional[List[OCRRegion]] = None,
    ) -> Optional[bytes]:
        """Process an image: OCR detect text, translate, overlay.

        Args:
            image_bytes: Raw image bytes
            media_type: MIME type (image/png or image/jpeg)
            translate_func: Function that takes list of texts, returns list of translations
            regions: Optional pre-detected OCR regions to reuse

        Returns:
            Modified image bytes, or None if no text was found
        """
        img = Image.open(io.BytesIO(image_bytes))

        # Skip tiny images
        if img.width < MIN_IMAGE_DIMENSION or img.height < MIN_IMAGE_DIMENSION:
            return None

        # Convert to RGB if needed (RGBA, palette, etc.)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # Detect text regions (or reuse pre-scanned ones).
        if regions is None:
            regions = self._detect_text(img)
        else:
            # Re-apply source-language filter in case source was refined after pre-scan.
            regions = [r for r in regions if self._matches_source_lang(r.text)]
        if not regions:
            return None

        # Extract texts and translate
        source_texts = [r.text for r in regions]
        translations = translate_func(source_texts)

        # Render translations over original
        result = self._render_translations(img, regions, translations)

        # Encode back to original format
        output = io.BytesIO()
        fmt = 'PNG' if media_type == 'image/png' else 'JPEG'
        if fmt == 'JPEG' and result.mode == 'RGBA':
            result = result.convert('RGB')
        result.save(output, format=fmt)
        return output.getvalue()

    def detect_regions(self, image_bytes: bytes, media_type: str) -> List[OCRRegion]:
        """Detect OCR regions from image bytes without rendering translations."""
        if media_type not in SUPPORTED_MEDIA_TYPES:
            return []

        img = Image.open(io.BytesIO(image_bytes))
        if img.width < MIN_IMAGE_DIMENSION or img.height < MIN_IMAGE_DIMENSION:
            return []
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        return self._detect_text(img)

    def _get_reader(self):
        """Lazy-initialize EasyOCR reader."""
        if self._reader is None:
            import easyocr

            if self.source_lang == 'auto':
                # Auto mode: include common OCR source languages used in EPUBs.
                langs = list(AUTO_OCR_LANGS)
            else:
                langs = ['en']  # Keep English for mixed-language content
                ocr_lang = EASYOCR_LANG_MAP.get(self.source_lang, self.source_lang)
                if ocr_lang != 'en' and ocr_lang not in langs:
                    langs.append(ocr_lang)

            self._reader = easyocr.Reader(langs, gpu=False)
        return self._reader

    def _detect_text(self, img: Image.Image) -> List[OCRRegion]:
        """Run OCR on image and return detected text regions."""
        import numpy as np

        reader = self._get_reader()
        # Convert PIL Image to numpy array for EasyOCR
        img_array = np.array(img.convert('RGB'))
        results = reader.readtext(img_array)

        regions = []
        for bbox, text, confidence in results:
            if (
                confidence >= self.confidence_threshold
                and text.strip()
                and self._matches_source_lang(text)
            ):
                regions.append(OCRRegion(bbox=bbox, text=text, confidence=confidence))

        return regions

    def _matches_source_lang(self, text: str) -> bool:
        """Check whether OCR text matches the configured source language script."""
        lang = self.source_lang.lower()
        if lang == 'auto':
            return True

        # CJK
        if lang in {'zh', 'zh-cn', 'zh-tw'}:
            if lang == 'zh-tw' and re.search(r'[\u3100-\u312f\u31a0-\u31bf]', text):
                return True
            return re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]', text) is not None
        if lang == 'ko':
            return re.search(r'[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]', text) is not None
        if lang == 'ja':
            return re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text) is not None

        # Script-based languages
        if lang in {'ru', 'uk', 'bg'}:
            return re.search(r'[\u0400-\u04ff]', text) is not None
        if lang in {'ar', 'fa', 'ur'}:
            return re.search(r'[\u0600-\u06ff]', text) is not None
        if lang == 'he':
            return re.search(r'[\u0590-\u05ff]', text) is not None
        if lang == 'hi':
            return re.search(r'[\u0900-\u097f]', text) is not None
        if lang == 'th':
            return re.search(r'[\u0e00-\u0e7f]', text) is not None

        # Default: Latin-script languages.
        return re.search(r'[A-Za-z]', text) is not None

    def _render_translations(
        self,
        img: Image.Image,
        regions: List[OCRRegion],
        translations: List[str],
    ) -> Image.Image:
        """Overlay translated text on image regions."""
        result = img.copy()
        draw = ImageDraw.Draw(result)

        for region, translation in zip(regions, translations):
            if not translation or not translation.strip():
                continue

            # Sample background color from region edges
            bg_color = self._sample_background(img, region)

            # Cover original text with background color
            draw.rectangle(
                [region.x, region.y, region.x + region.width, region.y + region.height],
                fill=bg_color,
            )

            # Fit font to region
            font, text_to_draw = self._fit_font(translation, region.width, region.height)

            # Calculate text position (centered in region)
            text_bbox = draw.textbbox((0, 0), text_to_draw, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            text_x = region.x + (region.width - text_w) // 2
            text_y = region.y + (region.height - text_h) // 2

            # Choose text color (contrast with background)
            text_color = self._contrast_color(bg_color)

            draw.text((text_x, text_y), text_to_draw, fill=text_color, font=font)

        return result

    def _sample_background(self, img: Image.Image, region: OCRRegion) -> Tuple[int, ...]:
        """Sample background color from corners of the region."""
        rgb_img = img.convert('RGB')
        samples = []
        # Sample 4 corners with small offset inward
        margin = 2
        corners = [
            (max(0, region.x - margin), max(0, region.y - margin)),
            (min(rgb_img.width - 1, region.x + region.width + margin), max(0, region.y - margin)),
            (max(0, region.x - margin), min(rgb_img.height - 1, region.y + region.height + margin)),
            (min(rgb_img.width - 1, region.x + region.width + margin),
             min(rgb_img.height - 1, region.y + region.height + margin)),
        ]
        for cx, cy in corners:
            samples.append(rgb_img.getpixel((cx, cy)))

        # Average the sampled colors
        avg_r = sum(s[0] for s in samples) // len(samples)
        avg_g = sum(s[1] for s in samples) // len(samples)
        avg_b = sum(s[2] for s in samples) // len(samples)
        return (avg_r, avg_g, avg_b)

    def _contrast_color(self, bg_color: Tuple[int, ...]) -> Tuple[int, int, int]:
        """Return black or white text color based on background luminance."""
        luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        return (0, 0, 0) if luminance > 128 else (255, 255, 255)

    def _fit_font(self, text: str, max_width: int, max_height: int) -> Tuple[ImageFont.FreeTypeFont, str]:
        """Find the largest font size that fits text in the bounding box.

        Returns:
            Tuple of (font, text_to_draw) where text may be wrapped
        """
        font_path = self._find_font()
        min_size = 8
        max_size = max(min_size, max_height)

        # Binary search for optimal font size
        best_size = min_size
        lo, hi = min_size, max_size

        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                font = ImageFont.truetype(font_path, mid) if font_path else ImageFont.load_default()
            except (OSError, IOError):
                font = ImageFont.load_default()
                best_size = min_size
                break

            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            if text_w <= max_width and text_h <= max_height:
                best_size = mid
                lo = mid + 1
            else:
                hi = mid - 1

        try:
            final_font = ImageFont.truetype(font_path, best_size) if font_path else ImageFont.load_default()
        except (OSError, IOError):
            final_font = ImageFont.load_default()

        return final_font, text

    def _find_font(self) -> Optional[str]:
        """Find a suitable system font for the target language."""
        if self._font_path is not None:
            return self._font_path if self._font_path != '' else None

        # Try language-specific fonts first
        preferred = FONT_PREFERENCES.get(self.target_lang, [])
        for font_name in preferred:
            path = self._find_system_font(font_name)
            if path:
                self._font_path = path
                return path

        # Try fc-match as fallback
        path = self._fc_match_font()
        if path:
            self._font_path = path
            return path

        # Try common fallback fonts
        for fallback in ['DejaVuSans', 'DejaVu Sans', 'Arial', 'FreeSans']:
            path = self._find_system_font(fallback)
            if path:
                self._font_path = path
                return path

        self._font_path = ''  # Mark as "searched but not found"
        return None

    def _find_system_font(self, font_name: str) -> Optional[str]:
        """Search for a font file by name in common system paths."""
        import glob

        search_dirs = [
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            '/usr/share/fonts/truetype',
        ]
        name_lower = font_name.lower().replace(' ', '')

        for search_dir in search_dirs:
            for path in glob.glob(f"{search_dir}/**/*.ttf", recursive=True):
                basename = path.lower().replace(' ', '')
                if name_lower in basename:
                    return path
            for path in glob.glob(f"{search_dir}/**/*.otf", recursive=True):
                basename = path.lower().replace(' ', '')
                if name_lower in basename:
                    return path

        return None

    def _fc_match_font(self) -> Optional[str]:
        """Use fc-match to find a font supporting the target language."""
        if not shutil.which('fc-match'):
            return None
        try:
            result = subprocess.run(
                ['fc-match', '-f', '%{file}', f':lang={self.target_lang}'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                if path.endswith(('.ttf', '.otf', '.ttc')):
                    return path
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None
