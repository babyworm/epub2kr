"""Unit tests for the TranslationCache class."""
import pytest
from epub2kr.cache import TranslationCache


class TestTranslationCacheBasics:
    """Test basic cache operations."""

    def test_get_returns_none_for_missing_entries(self, tmp_cache):
        """Test that get returns None when entry doesn't exist."""
        result = tmp_cache.get("Hello", "en", "ko", "google")
        assert result is None

    def test_put_then_get_returns_correct_translation(self, tmp_cache):
        """Test storing and retrieving a translation."""
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        result = tmp_cache.get("Hello", "en", "ko", "google")
        assert result == "안녕하세요"

    def test_different_services_dont_collide(self, tmp_cache):
        """Test that same text with different services are separate entries."""
        tmp_cache.put("Hello", "Hola (google)", "en", "es", "google")
        tmp_cache.put("Hello", "Hola (deepl)", "en", "es", "deepl")

        google_result = tmp_cache.get("Hello", "en", "es", "google")
        deepl_result = tmp_cache.get("Hello", "en", "es", "deepl")

        assert google_result == "Hola (google)"
        assert deepl_result == "Hola (deepl)"

    def test_different_language_pairs_dont_collide(self, tmp_cache):
        """Test that same text with different language pairs are separate."""
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        tmp_cache.put("Hello", "Bonjour", "en", "fr", "google")
        tmp_cache.put("Hello", "Hola", "en", "es", "google")

        ko_result = tmp_cache.get("Hello", "en", "ko", "google")
        fr_result = tmp_cache.get("Hello", "en", "fr", "google")
        es_result = tmp_cache.get("Hello", "en", "es", "google")

        assert ko_result == "안녕하세요"
        assert fr_result == "Bonjour"
        assert es_result == "Hola"


class TestTranslationCacheBatch:
    """Test batch cache operations."""

    def test_get_batch_returns_correct_dict_with_indices(self, tmp_cache):
        """Test batch lookup returns correct index mapping."""
        # Store some translations
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        tmp_cache.put("Goodbye", "안녕히 가세요", "en", "ko", "google")

        # Batch lookup with mixed hits and misses
        texts = ["Hello", "World", "Goodbye", "Unknown"]
        results = tmp_cache.get_batch(texts, "en", "ko", "google")

        assert results == {
            0: "안녕하세요",
            2: "안녕히 가세요"
        }
        assert 1 not in results  # "World" not cached
        assert 3 not in results  # "Unknown" not cached

    def test_put_batch_then_get_batch_roundtrip(self, tmp_cache):
        """Test storing and retrieving multiple translations in batch."""
        pairs = [
            ("Hello", "안녕하세요"),
            ("World", "세계"),
            ("Goodbye", "안녕히 가세요")
        ]

        tmp_cache.put_batch(pairs, "en", "ko", "google")

        texts = ["Hello", "World", "Goodbye"]
        results = tmp_cache.get_batch(texts, "en", "ko", "google")

        assert results == {
            0: "안녕하세요",
            1: "세계",
            2: "안녕히 가세요"
        }

    def test_empty_batch_operations_work(self, tmp_cache):
        """Test that batch operations handle empty lists correctly."""
        # Empty get_batch
        results = tmp_cache.get_batch([], "en", "ko", "google")
        assert results == {}

        # Empty put_batch
        tmp_cache.put_batch([], "en", "ko", "google")
        # Should not raise an error

    def test_batch_with_duplicate_texts(self, tmp_cache):
        """Test batch operations with duplicate texts return all indices."""
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")

        # Same text appears at multiple indices
        texts = ["Hello", "World", "Hello", "Hello"]
        results = tmp_cache.get_batch(texts, "en", "ko", "google")

        # All "Hello" indices should be in results
        assert results == {
            0: "안녕하세요",
            2: "안녕하세요",
            3: "안녕하세요"
        }


class TestTranslationCacheStatistics:
    """Test cache statistics tracking."""

    def test_cache_hit_miss_statistics_tracked(self, tmp_cache):
        """Test that hit/miss counts are tracked correctly."""
        # Store a translation
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")

        # Hit
        tmp_cache.get("Hello", "en", "ko", "google")

        # Miss
        tmp_cache.get("World", "en", "ko", "google")

        # Another hit
        tmp_cache.get("Hello", "en", "ko", "google")

        stats = tmp_cache.stats()
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert stats['hit_rate'] == pytest.approx(2/3)

    def test_batch_operations_update_statistics(self, tmp_cache):
        """Test that batch operations update hit/miss statistics."""
        # Store some translations
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        tmp_cache.put("Goodbye", "안녕히 가세요", "en", "ko", "google")

        # Batch lookup: 2 hits, 2 misses
        texts = ["Hello", "World", "Goodbye", "Unknown"]
        tmp_cache.get_batch(texts, "en", "ko", "google")

        stats = tmp_cache.stats()
        assert stats['hits'] == 2
        assert stats['misses'] == 2
        assert stats['hit_rate'] == 0.5

    def test_stats_returns_correct_structure(self, tmp_cache):
        """Test that stats() returns all expected fields."""
        stats = tmp_cache.stats()

        assert 'total_entries' in stats
        assert 'db_size_bytes' in stats
        assert 'hit_rate' in stats
        assert 'hits' in stats
        assert 'misses' in stats

        assert isinstance(stats['total_entries'], int)
        assert isinstance(stats['db_size_bytes'], int)
        assert isinstance(stats['hit_rate'], float)
        assert isinstance(stats['hits'], int)
        assert isinstance(stats['misses'], int)

    def test_stats_total_entries_count(self, tmp_cache):
        """Test that total_entries reflects actual database count."""
        assert tmp_cache.stats()['total_entries'] == 0

        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        assert tmp_cache.stats()['total_entries'] == 1

        tmp_cache.put("World", "세계", "en", "ko", "google")
        assert tmp_cache.stats()['total_entries'] == 2

        # Same text, different service - should add new entry
        tmp_cache.put("Hello", "Hola", "en", "es", "google")
        assert tmp_cache.stats()['total_entries'] == 3

    def test_stats_db_size_increases(self, tmp_cache):
        """Test that db_size_bytes increases as entries are added."""
        initial_size = tmp_cache.stats()['db_size_bytes']

        # Add some translations with longer content to ensure size increase
        for i in range(100):
            text = f"Text {i} " * 20  # Make text longer
            translation = f"Translation {i} " * 20
            tmp_cache.put(text, translation, "en", "ko", "google")

        final_size = tmp_cache.stats()['db_size_bytes']
        assert final_size > initial_size


class TestTranslationCacheClear:
    """Test cache clearing functionality."""

    def test_clear_removes_all_entries(self, tmp_cache):
        """Test that clear() removes all cached translations."""
        # Add multiple entries
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        tmp_cache.put("World", "세계", "en", "ko", "google")
        tmp_cache.put("Hello", "Hola", "en", "es", "deepl")

        assert tmp_cache.stats()['total_entries'] == 3

        tmp_cache.clear()

        assert tmp_cache.stats()['total_entries'] == 0
        assert tmp_cache.get("Hello", "en", "ko", "google") is None
        assert tmp_cache.get("World", "en", "ko", "google") is None

    def test_clear_resets_statistics(self, tmp_cache):
        """Test that clear() resets hit/miss statistics."""
        # Generate some statistics
        tmp_cache.put("Hello", "안녕하세요", "en", "ko", "google")
        tmp_cache.get("Hello", "en", "ko", "google")  # hit
        tmp_cache.get("World", "en", "ko", "google")  # miss

        stats = tmp_cache.stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1

        tmp_cache.clear()

        stats = tmp_cache.stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['hit_rate'] == 0.0


class TestTranslationCacheHashFunction:
    """Test hash function behavior."""

    def test_hash_function_is_deterministic(self, tmp_cache):
        """Test that _hash_text produces consistent results."""
        text = "Hello, World!"
        hash1 = tmp_cache._hash_text(text)
        hash2 = tmp_cache._hash_text(text)

        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex digest length

    def test_hash_function_differs_for_different_texts(self, tmp_cache):
        """Test that different texts produce different hashes."""
        hash1 = tmp_cache._hash_text("Hello")
        hash2 = tmp_cache._hash_text("World")
        hash3 = tmp_cache._hash_text("hello")  # Different case

        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

    def test_hash_function_handles_unicode(self, tmp_cache):
        """Test that _hash_text handles Unicode text correctly."""
        texts = [
            "안녕하세요",  # Korean
            "こんにちは",  # Japanese
            "你好",        # Chinese
            "Привет",      # Russian
            "مرحبا",       # Arabic
        ]

        hashes = [tmp_cache._hash_text(text) for text in texts]

        # All hashes should be unique
        assert len(set(hashes)) == len(texts)

        # All should be valid SHA-256 hashes
        for h in hashes:
            assert len(h) == 64
            assert all(c in '0123456789abcdef' for c in h)


class TestTranslationCacheEdgeCases:
    """Test edge cases and special scenarios."""

    def test_cache_handles_empty_strings(self, tmp_cache):
        """Test caching empty strings."""
        tmp_cache.put("", "", "en", "ko", "google")
        result = tmp_cache.get("", "en", "ko", "google")
        assert result == ""

    def test_cache_handles_whitespace_only(self, tmp_cache):
        """Test caching whitespace-only strings."""
        tmp_cache.put("   ", "   ", "en", "ko", "google")
        result = tmp_cache.get("   ", "en", "ko", "google")
        assert result == "   "

    def test_cache_handles_very_long_text(self, tmp_cache):
        """Test caching very long text."""
        long_text = "A" * 10000
        long_translation = "B" * 10000

        tmp_cache.put(long_text, long_translation, "en", "ko", "google")
        result = tmp_cache.get(long_text, "en", "ko", "google")  # Fixed: was passing wrong params
        assert result == long_translation

    def test_cache_handles_special_characters(self, tmp_cache):
        """Test caching text with special characters."""
        special_text = "Hello\n\t<>&\"'World"
        special_translation = "안녕\n\t<>&\"'세계"

        tmp_cache.put(special_text, special_translation, "en", "ko", "google")
        result = tmp_cache.get(special_text, "en", "ko", "google")
        assert result == special_translation

    def test_cache_overwrites_existing_entry(self, tmp_cache):
        """Test that putting same key overwrites previous value."""
        tmp_cache.put("Hello", "First translation", "en", "ko", "google")
        tmp_cache.put("Hello", "Second translation", "en", "ko", "google")

        result = tmp_cache.get("Hello", "en", "ko", "google")
        assert result == "Second translation"

        # Should still be only 1 entry
        assert tmp_cache.stats()['total_entries'] == 1


class TestTranslationCacheThreadSafety:
    """Test thread safety (basic verification)."""

    def test_concurrent_operations_dont_corrupt_cache(self, tmp_cache):
        """Test that concurrent operations maintain data integrity."""
        import threading

        def worker(cache, thread_id):
            for i in range(10):
                text = f"Text {thread_id}-{i}"
                translation = f"Translation {thread_id}-{i}"
                cache.put(text, translation, "en", "ko", "google")
                result = cache.get(text, "en", "ko", "google")
                assert result == translation

        threads = []
        for tid in range(5):
            t = threading.Thread(target=worker, args=(tmp_cache, tid))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify all entries were stored
        assert tmp_cache.stats()['total_entries'] == 50
