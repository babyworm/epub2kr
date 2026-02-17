"""Tests for OCRPrescanCache."""

import hashlib

from epub2kr.ocr_cache import OCRPrescanCache


class TestOCRPrescanCache:
    def test_put_and_get_roundtrip(self, tmp_path):
        cache = OCRPrescanCache(cache_dir=str(tmp_path / "ocr_cache"))
        image_hash = hashlib.sha256(b"img-bytes").hexdigest()
        regions = [
            {
                "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "text": "hello",
                "confidence": 0.91,
            }
        ]

        cache.put(
            image_hash=image_hash,
            source_lang="zh-cn",
            media_type="image/png",
            confidence_threshold=0.3,
            regions=regions,
        )

        loaded = cache.get(
            image_hash=image_hash,
            source_lang="zh-cn",
            media_type="image/png",
            confidence_threshold=0.3,
        )
        assert loaded == regions

    def test_get_miss_returns_none(self, tmp_path):
        cache = OCRPrescanCache(cache_dir=str(tmp_path / "ocr_cache"))
        image_hash = hashlib.sha256(b"other").hexdigest()
        loaded = cache.get(
            image_hash=image_hash,
            source_lang="zh-cn",
            media_type="image/png",
            confidence_threshold=0.3,
        )
        assert loaded is None
