"""Abstract base class for translation services."""
from abc import ABC, abstractmethod
import time
from typing import Callable, List, Optional, TypeVar

T = TypeVar("T")

class BaseTranslationService(ABC):
    """Abstract base for all translation service providers."""

    def __init__(
        self,
        max_retries: int = 2,
        retry_backoff_base: float = 0.5,
        retry_backoff_max: float = 4.0,
    ):
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_base = max(0.0, float(retry_backoff_base))
        self.retry_backoff_max = max(float(retry_backoff_max), self.retry_backoff_base)

    def _with_retries(
        self,
        fn: Callable[[], T],
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ) -> T:
        """Run callable with exponential backoff retries."""
        attempt = 0
        while True:
            try:
                return fn()
            except Exception as exc:
                if attempt >= self.max_retries:
                    raise
                if on_retry is not None:
                    on_retry(attempt + 1, exc)
                sleep_s = min(self.retry_backoff_max, self.retry_backoff_base * (2 ** attempt))
                if sleep_s > 0:
                    time.sleep(sleep_s)
                attempt += 1

    @abstractmethod
    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments.

        Args:
            texts: List of text strings to translate
            source_lang: Source language code (e.g., 'en', 'zh-CN')
            target_lang: Target language code (e.g., 'en', 'zh-CN')

        Returns:
            List of translated strings in the same order as input
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return service name.

        Returns:
            String identifier for the service
        """
        pass
