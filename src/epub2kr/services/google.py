"""Google Translate service using free web API."""
import time
import requests
from typing import List
from urllib.parse import quote

from .base import BaseTranslationService


class GoogleTranslateService(BaseTranslationService):
    """Google Translate implementation using free web endpoint."""

    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        max_retries: int = 2,
        retry_backoff_base: float = 0.5,
        retry_backoff_max: float = 4.0,
    ):
        """Initialize Google Translate service.

        Args:
            rate_limit_delay: Delay in seconds between requests to avoid rate limiting
        """
        super().__init__(
            max_retries=max_retries,
            retry_backoff_base=retry_backoff_base,
            retry_backoff_max=retry_backoff_max,
        )
        self.rate_limit_delay = rate_limit_delay
        self.base_url = "https://translate.googleapis.com/translate_a/single"

    def name(self) -> str:
        """Return service name."""
        return "google"

    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments.

        Args:
            texts: List of text strings to translate
            source_lang: Source language code (e.g., 'en', 'zh-CN')
            target_lang: Target language code (e.g., 'en', 'zh-CN')

        Returns:
            List of translated strings in the same order as input
        """
        if not texts:
            return []

        results = []
        for text in texts:
            # Handle empty strings
            if not text or text.isspace():
                results.append(text)
                continue

            try:
                translated = self._with_retries(
                    lambda: self._translate_single(text, source_lang, target_lang)
                )
                results.append(translated)
            except Exception as e:
                # On error, return original text
                print(f"Translation error: {e}")
                results.append(text)

            # Rate limiting
            if len(texts) > 1:
                time.sleep(self.rate_limit_delay)

        return results

    def _translate_single(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate a single text segment.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Translated text
        """
        # Normalize language codes (Google uses 'zh-CN' format)
        source = self._normalize_lang_code(source_lang)
        target = self._normalize_lang_code(target_lang)

        params = {
            'client': 'gtx',
            'sl': source,
            'tl': target,
            'dt': 't',
            'q': text
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(
            self.base_url,
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()

        # Parse response: [[["translated text","original text",...]]]
        data = response.json()
        if data and len(data) > 0 and len(data[0]) > 0:
            # Concatenate all translation segments
            translated = ''.join([segment[0] for segment in data[0] if segment[0]])
            return translated

        return text

    def _normalize_lang_code(self, lang: str) -> str:
        """Normalize language code for Google Translate.

        Args:
            lang: Language code

        Returns:
            Normalized language code
        """
        # Convert common variations
        lang = lang.lower()
        mapping = {
            'zh': 'zh-CN',
            'zh-cn': 'zh-CN',
            'zh-tw': 'zh-TW',
            'en': 'en',
            'ja': 'ja',
            'ko': 'ko',
            'fr': 'fr',
            'de': 'de',
            'es': 'es',
            'ru': 'ru',
        }
        return mapping.get(lang, lang)
