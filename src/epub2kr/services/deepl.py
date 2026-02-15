"""DeepL translation service."""
import os
from typing import List

from .base import BaseTranslationService


class DeepLService(BaseTranslationService):
    """DeepL API implementation."""

    def __init__(self, api_key: str = None, use_free: bool = True):
        """Initialize DeepL service.

        Args:
            api_key: DeepL API key (if None, reads from DEEPL_API_KEY env var)
            use_free: Whether to use free API endpoint (default: True)
        """
        self.api_key = api_key or os.getenv('DEEPL_API_KEY')
        if not self.api_key:
            raise ValueError("DeepL API key required. Set DEEPL_API_KEY or pass api_key parameter")

        try:
            import deepl
            self.deepl = deepl
        except ImportError:
            raise ImportError("deepl package required. Install with: pip install deepl")

        # Initialize translator
        self.translator = deepl.Translator(self.api_key)

    def name(self) -> str:
        """Return service name."""
        return "deepl"

    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments.

        Args:
            texts: List of text strings to translate
            source_lang: Source language code (e.g., 'EN', 'ZH')
            target_lang: Target language code (e.g., 'EN-US', 'ZH')

        Returns:
            List of translated strings in the same order as input
        """
        if not texts:
            return []

        # Filter out empty strings but preserve their positions
        indices_to_translate = []
        texts_to_translate = []

        for i, text in enumerate(texts):
            if text and not text.isspace():
                indices_to_translate.append(i)
                texts_to_translate.append(text)

        if not texts_to_translate:
            return texts

        # Normalize language codes for DeepL
        source = self._normalize_lang_code(source_lang, is_target=False)
        target = self._normalize_lang_code(target_lang, is_target=True)

        try:
            # Translate batch
            results = self.translator.translate_text(
                texts_to_translate,
                source_lang=source if source else None,  # None = auto-detect
                target_lang=target
            )

            # Handle both single result and list of results
            if not isinstance(results, list):
                results = [results]

            # Reconstruct full list with translated texts at correct positions
            output = list(texts)  # Copy original list
            for i, result in zip(indices_to_translate, results):
                output[i] = result.text

            return output

        except Exception as e:
            print(f"DeepL translation error: {e}")
            return texts  # Return original on error

    def _normalize_lang_code(self, lang: str, is_target: bool) -> str:
        """Normalize language code for DeepL API.

        Args:
            lang: Language code
            is_target: Whether this is a target language (affects English variants)

        Returns:
            Normalized language code
        """
        lang = lang.upper()

        # DeepL source languages
        source_mapping = {
            'EN': 'EN',
            'ZH': 'ZH',
            'ZH-CN': 'ZH',
            'ZH-TW': 'ZH',
            'JA': 'JA',
            'KO': 'KO',
            'FR': 'FR',
            'DE': 'DE',
            'ES': 'ES',
            'RU': 'RU',
            'PT': 'PT',
            'IT': 'IT',
            'NL': 'NL',
            'PL': 'PL',
        }

        # DeepL target languages (more specific for English, Portuguese)
        target_mapping = {
            'EN': 'EN-US',
            'EN-US': 'EN-US',
            'EN-GB': 'EN-GB',
            'ZH': 'ZH',
            'ZH-CN': 'ZH',
            'ZH-TW': 'ZH',
            'JA': 'JA',
            'KO': 'KO',
            'FR': 'FR',
            'DE': 'DE',
            'ES': 'ES',
            'RU': 'RU',
            'PT': 'PT-PT',
            'PT-PT': 'PT-PT',
            'PT-BR': 'PT-BR',
            'IT': 'IT',
            'NL': 'NL',
            'PL': 'PL',
        }

        mapping = target_mapping if is_target else source_mapping
        return mapping.get(lang, lang)
