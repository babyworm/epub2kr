"""Lightweight benchmark-oriented smoke tests."""

import time
from unittest.mock import MagicMock, patch


def test_translation_pipeline_benchmark_smoke(minimal_epub, tmp_path):
    """Collect a basic timing metric without strict performance assertions."""
    from epub2kr.translator import EpubTranslator

    mock_svc = MagicMock()
    mock_svc.__class__.__name__ = "MockService"
    mock_svc.translate.side_effect = lambda texts, sl, tl: [f"[tr]{t}" for t in texts]

    output_path = tmp_path / "bench_out.epub"
    with patch("epub2kr.translator.get_service", return_value=mock_svc):
        translator = EpubTranslator(
            service_name="google",
            source_lang="en",
            target_lang="ko",
            threads=4,
            image_threads=4,
            use_cache=False,
        )
        start = time.perf_counter()
        translator.translate_epub(str(minimal_epub), str(output_path))
        elapsed = time.perf_counter() - start

    assert output_path.exists()
    # Keep this very loose: guard against hangs/regressions, not micro-optimization noise.
    assert elapsed < 30.0
