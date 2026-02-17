"""OCR-based image text translation for EPUB images."""
import io
import re
import subprocess
import shutil
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple

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
        render_quality: str = "balanced",
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.confidence_threshold = confidence_threshold
        self.render_quality = render_quality
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
        translations: Optional[List[str]] = None,
        on_translation: Optional[Callable[[List[OCRRegion], List[str]], None]] = None,
        on_timing: Optional[Callable[[Dict[str, float]], None]] = None,
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
        with Image.open(io.BytesIO(image_bytes)) as opened:
            img = opened.copy()

        # Skip tiny images
        if img.width < MIN_IMAGE_DIMENSION or img.height < MIN_IMAGE_DIMENSION:
            return None

        # Detect text regions (or reuse pre-scanned ones).
        if regions is None:
            regions = self._detect_text(img)
        else:
            # Re-apply source-language filter in case source was refined after pre-scan.
            regions = [r for r in regions if self._matches_source_lang(r.text)]
        regions = self.prepare_regions_for_translation(regions)
        if not regions:
            return None

        # Extract texts and translate
        source_texts = [r.text for r in regions]
        translate_elapsed = 0.0
        if translations is None or len(translations) != len(source_texts):
            translate_start = time.perf_counter()
            translations = translate_func(source_texts)
            translate_elapsed = time.perf_counter() - translate_start
        if on_translation is not None:
            on_translation(regions, translations)
        draw_pairs = [
            (region, translation)
            for region, translation in zip(regions, translations)
            if self._should_draw_translation(region.text, translation)
        ]
        if not draw_pairs:
            if on_timing is not None:
                on_timing({"translate_sec": translate_elapsed, "render_sec": 0.0})
            return None

        # Render translations over original
        render_start = time.perf_counter()
        result = self._render_translations(
            img,
            [region for region, _ in draw_pairs],
            [translation for _, translation in draw_pairs],
        )
        render_elapsed = time.perf_counter() - render_start

        # Encode back to original format
        output = io.BytesIO()
        fmt = 'PNG' if media_type == 'image/png' else 'JPEG'
        if fmt == 'JPEG' and result.mode == 'RGBA':
            result = result.convert('RGB')
        result.save(output, format=fmt)
        data = output.getvalue()
        output.close()
        if on_timing is not None:
            on_timing({"translate_sec": translate_elapsed, "render_sec": render_elapsed})
        return data

    def detect_regions(self, image_bytes: bytes, media_type: str) -> List[OCRRegion]:
        """Detect OCR regions from image bytes without rendering translations."""
        if media_type not in SUPPORTED_MEDIA_TYPES:
            return []

        with Image.open(io.BytesIO(image_bytes)) as opened:
            img = opened.copy()
        if img.width < MIN_IMAGE_DIMENSION or img.height < MIN_IMAGE_DIMENSION:
            return []
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        return self._detect_text(img)

    def prepare_regions_for_translation(self, regions: List[OCRRegion]) -> List[OCRRegion]:
        """Normalize region order/shape so translation units are stable across runs."""
        if not regions:
            return []
        ordered = sorted(regions, key=lambda r: (r.y, r.x))
        return self._merge_regions_for_translation(ordered)

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
            normalized = self._normalize_ocr_text(text)
            if (
                confidence >= self.confidence_threshold
                and normalized
                and not self._is_noise_text(normalized)
                and self._matches_source_lang(normalized)
            ):
                regions.append(OCRRegion(bbox=bbox, text=normalized, confidence=confidence))

        return regions

    def _normalize_ocr_text(self, text: str) -> str:
        """Normalize OCR text so translation input is cleaner and more stable."""
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _is_noise_text(self, text: str) -> bool:
        """Filter obvious OCR noise (punctuation-only or extremely short symbols)."""
        if not text:
            return True
        if len(text) == 1 and not re.search(r"[A-Za-z0-9\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]", text):
            return True
        if not re.search(
            r"[A-Za-z0-9\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3\u0400-\u04ff\u0600-\u06ff\u0590-\u05ff\u0900-\u097f\u0e00-\u0e7f]",
            text,
        ):
            return True
        return False

    def _canonical_text(self, text: str) -> str:
        normalized = self._normalize_ocr_text(text).casefold()
        return re.sub(r"\s+", "", normalized)

    def _should_draw_translation(self, source_text: str, translated_text: str) -> bool:
        """Return True only when translation implies a visible text replacement."""
        if not translated_text or not translated_text.strip():
            return False
        return self._canonical_text(source_text) != self._canonical_text(translated_text)

    def _merge_regions_for_translation(self, regions: List[OCRRegion]) -> List[OCRRegion]:
        """Merge adjacent OCR boxes into line-level units to reduce translation calls."""
        if not regions:
            return []

        merged: List[OCRRegion] = []
        current = regions[0]

        for nxt in regions[1:]:
            if self._should_merge_regions(current, nxt):
                current = self._merge_two_regions(current, nxt)
            else:
                merged.append(current)
                current = nxt
        merged.append(current)
        return merged

    def _should_merge_regions(self, left: OCRRegion, right: OCRRegion) -> bool:
        left_bottom = left.y + left.height
        right_bottom = right.y + right.height
        overlap = max(0, min(left_bottom, right_bottom) - max(left.y, right.y))
        min_height = max(1, min(left.height, right.height))
        vertical_overlap_ratio = overlap / min_height

        horiz_gap = right.x - (left.x + left.width)
        same_row = vertical_overlap_ratio >= 0.5
        close_enough = horiz_gap <= max(24, int(max(left.height, right.height) * 1.5))
        return same_row and close_enough

    def _merge_two_regions(self, a: OCRRegion, b: OCRRegion) -> OCRRegion:
        x1 = min(a.x, b.x)
        y1 = min(a.y, b.y)
        x2 = max(a.x + a.width, b.x + b.width)
        y2 = max(a.y + a.height, b.y + b.height)
        bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        use_space = not (self._is_cjk_text(a.text) and self._is_cjk_text(b.text))
        sep = " " if use_space else ""
        text = f"{a.text}{sep}{b.text}".strip()
        conf = min(a.confidence, b.confidence)
        return OCRRegion(bbox=bbox, text=text, confidence=conf)

    @staticmethod
    def _is_cjk_text(text: str) -> bool:
        return re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]", text) is not None

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

            wrapped = self._wrap_text_to_width(text, font, max_width)
            text_w, text_h = self._measure_multiline(font, wrapped)

            if text_w <= max_width and text_h <= max_height:
                best_size = mid
                best_text = wrapped
                lo = mid + 1
            else:
                hi = mid - 1

        try:
            final_font = ImageFont.truetype(font_path, best_size) if font_path else ImageFont.load_default()
        except (OSError, IOError):
            final_font = ImageFont.load_default()

        final_text = self._wrap_text_to_width(text, final_font, max_width)
        final_text = self._fit_text_to_height(final_text, final_font, max_width, max_height)
        if not final_text.strip():
            final_text = text
        return final_font, final_text

    def _fit_text_to_height(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
        max_height: int,
    ) -> str:
        """Ensure wrapped text fits in region height; truncate last line if needed."""
        wrapped = text
        _, text_h = self._measure_multiline(font, wrapped)
        if text_h <= max_height:
            return wrapped

        lines = wrapped.splitlines() or [wrapped]
        if not lines:
            return wrapped

        while lines:
            trial = "\n".join(lines)
            _, h = self._measure_multiline(font, trial)
            if h <= max_height:
                return trial
            if len(lines) > 1:
                lines.pop()
                continue

            line = lines[0]
            ellipsis = "..."
            while line:
                candidate = f"{line}{ellipsis}"
                candidate_wrapped = self._wrap_text_to_width(candidate, font, max_width)
                _, h2 = self._measure_multiline(font, candidate_wrapped)
                if h2 <= max_height:
                    return candidate_wrapped
                line = line[:-1]
            return ellipsis

        return text

    def _measure_multiline(self, font: ImageFont.ImageFont, text: str) -> Tuple[int, int]:
        lines = text.splitlines() or [text]
        max_w = 0
        total_h = 0
        line_spacing = 1 if self.render_quality == "fast" else (2 if self.render_quality == "balanced" else 3)
        for line in lines:
            bbox = font.getbbox(line if line else " ")
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            max_w = max(max_w, w)
            total_h += max(h, 1)
        # Small spacing between lines improves readability
        if len(lines) > 1:
            total_h += (len(lines) - 1) * line_spacing
        return max_w, total_h

    def _wrap_text_to_width(self, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        if max_width <= 0:
            return text
        if not text.strip():
            return text

        # Preserve explicit line breaks first.
        wrapped_lines: List[str] = []
        for paragraph in text.splitlines():
            if not paragraph.strip():
                wrapped_lines.append("")
                continue

            # Prefer word wrapping for spaced languages.
            if " " in paragraph:
                words = paragraph.split()
                line = words[0]
                for word in words[1:]:
                    candidate = f"{line} {word}"
                    bbox = font.getbbox(candidate)
                    if (bbox[2] - bbox[0]) <= max_width:
                        line = candidate
                    else:
                        wrapped_lines.append(line)
                        line = word
                wrapped_lines.append(line)
            else:
                # Character-level wrapping for CJK/no-space scripts.
                line = ""
                for ch in paragraph:
                    candidate = f"{line}{ch}"
                    bbox = font.getbbox(candidate)
                    if line and (bbox[2] - bbox[0]) > max_width:
                        wrapped_lines.append(line)
                        line = ch
                    else:
                        line = candidate
                if line:
                    wrapped_lines.append(line)

        return "\n".join(wrapped_lines)

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
