"""Ollama local LLM translation service."""
import os
import requests
from typing import List

from .base import BaseTranslationService


class OllamaService(BaseTranslationService):
    """Ollama local LLM implementation."""

    def __init__(
        self,
        model: str = "llama2",
        base_url: str = None,
        temperature: float = 0.3,
        timeout: int = 60
    ):
        """Initialize Ollama service.

        Args:
            model: Ollama model name (default: llama2)
            base_url: Ollama API base URL (default: http://localhost:11434)
            temperature: Sampling temperature (default: 0.3 for consistent translations)
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.temperature = temperature
        self.timeout = timeout
        self.api_url = f"{self.base_url}/api/generate"

    def name(self) -> str:
        """Return service name."""
        return "ollama"

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
                print(f"Ollama translation error: {e}")
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

        prompt = (
            f"Translate the following text from {source_name} to {target_name}. "
            f"Only provide the translation without any explanations or additional text.\n\n"
            f"Text: {text}\n\n"
            f"Translation:"
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            translated = data.get('response', '').strip()

            # Clean up common LLM artifacts
            translated = self._clean_translation(translated)

            return translated if translated else text

        except requests.exceptions.ConnectionError:
            raise Exception(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Make sure Ollama is running."
            )
        except requests.exceptions.Timeout:
            raise Exception(f"Ollama request timed out after {self.timeout} seconds")
        except Exception as e:
            raise Exception(f"Ollama API call failed: {e}")

    def _clean_translation(self, text: str) -> str:
        """Remove common LLM artifacts from translation.

        Args:
            text: Raw translation text

        Returns:
            Cleaned translation
        """
        # Remove common prefixes
        prefixes = [
            "Translation:",
            "Here is the translation:",
            "The translation is:",
        ]

        for prefix in prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()

        # Remove quotes if the entire text is quoted
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        elif text.startswith("'") and text.endswith("'"):
            text = text[1:-1]

        return text

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

    def check_availability(self) -> bool:
        """Check if Ollama service is available.

        Returns:
            True if Ollama is running and model is available
        """
        try:
            # Check if Ollama is running
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            response.raise_for_status()

            # Check if the specified model is available
            models = response.json().get('models', [])
            model_names = [m.get('name') for m in models]

            return any(self.model in name for name in model_names)

        except Exception:
            return False
