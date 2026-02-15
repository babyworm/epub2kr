"""OpenAI and compatible API translation service."""
import os
from typing import List

from .base import BaseTranslationService


class OpenAIService(BaseTranslationService):
    """OpenAI API implementation with support for compatible APIs."""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.3,
        max_tokens: int = 2000
    ):
        """Initialize OpenAI service.

        Args:
            api_key: OpenAI API key (if None, reads from OPENAI_API_KEY env var)
            base_url: Custom base URL for compatible APIs (e.g., local LLMs)
            model: Model name to use (default: gpt-3.5-turbo)
            temperature: Sampling temperature (default: 0.3 for consistent translations)
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY or pass api_key parameter")

        self.base_url = base_url or os.getenv('OPENAI_BASE_URL')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        try:
            import openai
            self.openai = openai
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")

        # Initialize client
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = openai.OpenAI(**client_kwargs)

    def name(self) -> str:
        """Return service name."""
        return "openai"

    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments.

        Args:
            texts: List of text strings to translate
            source_lang: Source language code (e.g., 'en', 'zh')
            target_lang: Target language code (e.g., 'en', 'zh')

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
                translated = self._translate_single(text, source_lang, target_lang)
                results.append(translated)
            except Exception as e:
                print(f"OpenAI translation error: {e}")
                results.append(text)  # Return original on error

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
        # Format language names
        source_name = self._format_language_name(source_lang)
        target_name = self._format_language_name(target_lang)

        system_prompt = (
            f"You are a professional translator. Translate the following text from "
            f"{source_name} to {target_name}. Only output the translation, nothing else."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            translated = response.choices[0].message.content.strip()
            return translated

        except Exception as e:
            raise Exception(f"API call failed: {e}")

    def _format_language_name(self, lang_code: str) -> str:
        """Format language code to human-readable name.

        Args:
            lang_code: Language code

        Returns:
            Human-readable language name
        """
        lang_code = lang_code.lower()
        mapping = {
            'en': 'English',
            'zh': 'Chinese',
            'zh-cn': 'Simplified Chinese',
            'zh-tw': 'Traditional Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish',
            'ru': 'Russian',
            'pt': 'Portuguese',
            'it': 'Italian',
            'nl': 'Dutch',
            'pl': 'Polish',
            'ar': 'Arabic',
            'hi': 'Hindi',
        }
        return mapping.get(lang_code, lang_code.upper())
