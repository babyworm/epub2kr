"""Main EPUB translation orchestrator."""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console

from .epub_parser import EpubParser
from .text_extractor import TextExtractor
from .cache import TranslationCache
from .ocr_cache import OCRPrescanCache
from .services import get_service
from .services.base import BaseTranslationService

LANG_NAMES = {
    'auto': 'Auto Detect', 'ko': 'Korean', 'en': 'English', 'zh': 'Chinese',
    'zh-cn': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)',
    'ja': 'Japanese', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'ru': 'Russian', 'pt': 'Portuguese', 'it': 'Italian', 'vi': 'Vietnamese',
    'th': 'Thai', 'ar': 'Arabic', 'hi': 'Hindi', 'id': 'Indonesian',
    'nl': 'Dutch', 'pl': 'Polish', 'tr': 'Turkish', 'uk': 'Ukrainian',
    'sv': 'Swedish', 'cs': 'Czech', 'da': 'Danish', 'fi': 'Finnish',
    'el': 'Greek', 'hu': 'Hungarian', 'no': 'Norwegian', 'ro': 'Romanian',
    'bg': 'Bulgarian', 'hr': 'Croatian', 'sk': 'Slovak', 'sl': 'Slovenian',
    'lt': 'Lithuanian', 'lv': 'Latvian', 'et': 'Estonian',
    'ms': 'Malay', 'tl': 'Filipino', 'bn': 'Bengali', 'ta': 'Tamil',
    'te': 'Telugu', 'mr': 'Marathi', 'ur': 'Urdu', 'fa': 'Persian',
    'he': 'Hebrew', 'sw': 'Swahili', 'af': 'Afrikaans',
}

# Common mistakes: country code → correct language code
LANG_CORRECTIONS = {
    'kr': 'ko',  # Korea → Korean
    'jp': 'ja',  # Japan → Japanese
    'cn': 'zh',  # China → Chinese
    'tw': 'zh-tw',  # Taiwan → Chinese Traditional
    'gb': 'en',  # Great Britain → English
    'us': 'en',  # United States → English
    'br': 'pt',  # Brazil → Portuguese
    'mx': 'es',  # Mexico → Spanish
}

SUPPORTED_LANGS = set(LANG_NAMES.keys())


def lang_label(code: str) -> str:
    """Return 'code (Name)' if known, otherwise just code."""
    name = LANG_NAMES.get(code)
    return f"{code} ({name})" if name else code


def validate_lang_code(code: str) -> str:
    """Validate language code and return it, or raise ValueError."""
    if code == 'auto':
        return code
    code_lower = code.lower()
    if code_lower in SUPPORTED_LANGS:
        return code_lower
    # Check common mistakes
    if code_lower in LANG_CORRECTIONS:
        correct = LANG_CORRECTIONS[code_lower]
        raise ValueError(
            f"'{code}' is a country code. Use language code '{correct}' ({LANG_NAMES[correct]}) instead."
        )
    # Unknown code
    raise ValueError(
        f"Unsupported language code: '{code}'. "
        f"Supported: {', '.join(sorted(k for k in SUPPORTED_LANGS if k != 'auto'))}"
    )


# CJK languages that benefit from adjusted font/line-height
CJK_LANGS = {'ko', 'ja', 'zh', 'zh-cn', 'zh-tw'}

# Font stacks per language
CJK_FONT_STACKS = {
    'ko': '"Noto Sans KR", "Noto Sans CJK KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
    'ja': '"Noto Sans JP", "Noto Sans CJK JP", "Hiragino Sans", "Yu Gothic", sans-serif',
    'zh': '"Noto Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    'zh-cn': '"Noto Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    'zh-tw': '"Noto Sans TC", "Noto Sans CJK TC", "PingFang TC", "Microsoft JhengHei", sans-serif',
}

# Character hints to disambiguate Chinese variants.
SIMPLIFIED_HINT_CHARS = set(
    "这来时个们为国发对说会后现没动过种里实点开样关么还当两经气从业"
)
TRADITIONAL_HINT_CHARS = set(
    "這來時個們為國發對說會後現沒動過種裡實點開樣關麼還當兩經氣從業"
)


class EpubTranslator:
    """Orchestrates the EPUB translation pipeline."""

    def __init__(
        self,
        service_name: str = "google",
        source_lang: str = "auto",
        target_lang: str = "en",
        threads: int = 4,
        image_threads: Optional[int] = None,
        use_cache: bool = True,
        bilingual: bool = False,
        font_size: str = "0.95em",
        line_height: str = "1.8",
        font_family: Optional[str] = None,
        heading_font_family: Optional[str] = None,
        paragraph_spacing: str = "0.5em",
        translate_images: bool = True,
        images_only: bool = False,
        resume: bool = False,
        verbose: bool = False,
        quiet: bool = False,
        **service_kwargs
    ):
        """Initialize the EPUB translator.

        Args:
            service_name: Translation service to use
            source_lang: Source language code (auto-detect if 'auto')
            target_lang: Target language code
            threads: Number of parallel threads for chapter translation
            image_threads: Number of parallel threads for image OCR/translation
            use_cache: Whether to use translation cache
            bilingual: Generate bilingual output (original + translated)
            font_size: CSS font-size for CJK output (e.g. '0.95em', '14px')
            line_height: CSS line-height for CJK output (e.g. '1.8', '2.0')
            font_family: CSS font-family override (None = auto-detect by language)
            heading_font_family: CSS font-family for headings (None = same as body)
            paragraph_spacing: CSS margin-bottom for paragraphs (e.g. '0.5em')
            translate_images: Whether to OCR and translate text in images
            images_only: Only run image OCR/translation pipeline
            resume: Resume from existing output (image-focused continuation)
            verbose: Enable verbose logs
            quiet: Suppress non-essential logs
            **service_kwargs: Additional arguments for translation service
        """
        self.service = get_service(service_name, **service_kwargs)
        self.source_lang = source_lang
        self.effective_source_lang = source_lang
        self._source_lang_locked = source_lang != 'auto'
        self._source_lang_lock = threading.Lock()
        self.target_lang = target_lang
        self.threads = threads
        self.image_threads = image_threads if image_threads is not None else threads
        self.cache = TranslationCache() if use_cache else None
        self.ocr_cache = OCRPrescanCache() if use_cache else None
        self.bilingual = bilingual
        self.translate_images = translate_images
        self.images_only = images_only
        self.resume = resume
        self.verbose = verbose
        self.quiet = quiet
        self.font_size = font_size
        self.line_height = line_height
        self.font_family = font_family
        self.heading_font_family = heading_font_family
        self.paragraph_spacing = paragraph_spacing
        self.extractor = TextExtractor()
        self.parser = EpubParser()
        self.console = Console(quiet=quiet)
        self._last_report: Dict = {}

    @staticmethod
    def _resume_path(output_path: str) -> Path:
        return Path(f"{output_path}.resume.json")

    def _load_resume_checkpoint(self, output_path: str) -> Dict:
        p = self._resume_path(output_path)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_resume_checkpoint(self, output_path: str, payload: Dict) -> None:
        p = self._resume_path(output_path)
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def translate_epub(self, input_path: str, output_path: Optional[str] = None) -> str:
        """Main entry point: translate an EPUB file.

        Steps:
        1. Load EPUB
        2. Get all content documents in spine order
        3. For each document, extract text, translate (with cache), replace text
        4. Update metadata language
        5. Translate TOC labels
        6. Save output EPUB

        Args:
            input_path: Path to input EPUB file
            output_path: Optional output path (auto-generated if not provided)

        Returns:
            Path to output EPUB file
        """
        # Generate output path if not provided
        if output_path is None:
            input_file = Path(input_path)
            output_path = str(input_file.parent / f"{input_file.stem}.{self.target_lang}.epub")

        total_start = time.perf_counter()
        load_path = input_path
        effective_images_only = self.images_only
        checkpoint = {
            "chapters_done": False,
            "images_done": False,
            "metadata_done": False,
            "saved_done": False,
        }
        if self.resume and output_path:
            checkpoint.update(self._load_resume_checkpoint(output_path))
        if self.resume and output_path and Path(output_path).exists() and not effective_images_only:
            load_path = output_path
            effective_images_only = True
            self.console.print(
                f"[cyan]Resume:[/cyan] existing output detected, continuing with image-only mode from {load_path}"
            )

        self.console.print(f"[cyan]Loading EPUB:[/cyan] {load_path}")
        book = self.parser.load(load_path)

        # Get all content documents in spine order
        content_docs = self.parser.get_content_documents(book)
        total_docs = len(content_docs)
        # Try early source detection so the initial log can show detected language.
        if self.source_lang == 'auto' and not self._source_lang_locked:
            early_detected = self._resolve_effective_source_lang(content_docs)
            if early_detected != 'auto':
                self.effective_source_lang = early_detected
                self._source_lang_locked = True

        self.console.print(f"[cyan]Found {total_docs} content documents[/cyan]")
        self.console.print(
            f"[cyan]Translation:[/cyan] "
            f"{self._source_lang_display()} → {lang_label(self.target_lang)}"
        )
        self.console.print(f"[cyan]Service:[/cyan] {self.service.__class__.__name__}")
        self.console.print(f"[cyan]Threads:[/cyan] {self.threads}")
        self.console.print(f"[cyan]Image threads:[/cyan] {self.image_threads}")
        self.console.print(f"[cyan]Cache:[/cyan] {'enabled' if self.cache else 'disabled'}")
        if effective_images_only:
            self.console.print("[cyan]Mode:[/cyan] Images-only")
        if self.bilingual:
            self.console.print("[cyan]Mode:[/cyan] Bilingual")

        # Translate documents with progress bar
        chapter_start = time.perf_counter()
        image_prefetch_executor = None
        image_prefetch_future = None
        image_translate_executor = None
        image_translate_future = None
        image_translate_started = False
        prefetched_regions = None
        prefetch_state = {"total": 0, "completed": 0}
        prefetch_lock = threading.Lock()
        if self.translate_images:
            self.console.print("[cyan]Pre-scanning images for OCR candidates (background)...[/cyan]")
            image_prefetch_executor = ThreadPoolExecutor(max_workers=1)
            image_prefetch_future = image_prefetch_executor.submit(
                self._prefetch_image_regions,
                book,
                self.effective_source_lang,
                prefetch_state,
                prefetch_lock,
            )

        def maybe_start_image_translation():
            nonlocal image_translate_executor, image_translate_future
            nonlocal image_translate_started, prefetched_regions
            if not self.translate_images or image_translate_started:
                return
            if image_prefetch_future is None or not image_prefetch_future.done():
                return
            if self.source_lang == "auto" and not self._source_lang_locked:
                return

            prefetched_regions = image_prefetch_future.result()
            if image_prefetch_executor is not None:
                image_prefetch_executor.shutdown(wait=False, cancel_futures=False)
            image_translate_executor = ThreadPoolExecutor(max_workers=1)
            image_translate_future = image_translate_executor.submit(
                self._translate_images,
                book,
                prefetched_regions,
                False,
            )
            image_translate_started = True
            self.console.print("[cyan]Pre-scan ready. Starting image translation in background...[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            main_task = progress.add_task("[green]Translating chapters...", total=total_docs)
            prefetch_task = None
            if self.translate_images:
                prefetch_task = progress.add_task("[blue]Pre-scanning images 0/0...[/blue]", total=0)

            if self.threads > 1:
                # Parallel translation
                executor = ThreadPoolExecutor(max_workers=self.threads)
                interrupted = False
                try:
                    futures = {
                        executor.submit(self._translate_document, item, idx + 1, total_docs): idx
                        for idx, item in enumerate(content_docs) if not effective_images_only
                    }

                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            self.console.print(f"[red]Error translating document {idx + 1}:[/red] {e}")
                        progress.advance(main_task)
                        if prefetch_task is not None:
                            self._update_prefetch_progress(progress, prefetch_task, prefetch_state, prefetch_lock)
                        maybe_start_image_translation()
                    if effective_images_only:
                        progress.update(main_task, completed=total_docs)
                except KeyboardInterrupt:
                    interrupted = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                finally:
                    if not interrupted:
                        executor.shutdown(wait=True, cancel_futures=False)
            else:
                # Sequential translation
                if effective_images_only:
                    progress.update(main_task, completed=total_docs)
                else:
                    for idx, item in enumerate(content_docs):
                        try:
                            self._translate_document(item, idx + 1, total_docs)
                        except Exception as e:
                            self.console.print(f"[red]Error translating document {idx + 1}:[/red] {e}")
                        progress.advance(main_task)
                        if prefetch_task is not None:
                            self._update_prefetch_progress(progress, prefetch_task, prefetch_state, prefetch_lock)
                        maybe_start_image_translation()

            if prefetch_task is not None and image_prefetch_future is not None:
                while not image_prefetch_future.done() and not image_translate_started:
                    self._update_prefetch_progress(progress, prefetch_task, prefetch_state, prefetch_lock)
                    time.sleep(0.1)
                    maybe_start_image_translation()
                self._update_prefetch_progress(progress, prefetch_task, prefetch_state, prefetch_lock)
                maybe_start_image_translation()
        chapter_elapsed = time.perf_counter() - chapter_start
        if output_path:
            checkpoint["chapters_done"] = True
            self._save_resume_checkpoint(output_path, checkpoint)

        if self.source_lang == 'auto':
            if not self._source_lang_locked:
                fallback = self._resolve_effective_source_lang(content_docs)
                if fallback != 'auto':
                    self.effective_source_lang = fallback
                    self._source_lang_locked = True
            self.console.print(
                f"[cyan]Translation:[/cyan] "
                f"{self._source_lang_display()} → {lang_label(self.target_lang)}"
            )

        # If source got locked only after chapter translation, start background image translation now.
        if self.translate_images and not image_translate_started and image_prefetch_future is not None:
            if image_prefetch_future.done():
                maybe_start_image_translation()

        # Add CJK stylesheet if targeting CJK language
        style_start = time.perf_counter()
        if self.target_lang.lower() in CJK_LANGS and not effective_images_only:
            self.console.print("[cyan]Adding CJK font stylesheet...[/cyan]")
            self._add_cjk_stylesheet(book, content_docs)
        style_elapsed = time.perf_counter() - style_start

        # Image text translation (OCR)
        images_start = time.perf_counter()
        if self.translate_images:
            self.console.print(f"[cyan]OCR source language:[/cyan] {lang_label(self.effective_source_lang)}")
            if image_translate_started and image_translate_future is not None:
                self.console.print("[cyan]Waiting for background image translation to finish...[/cyan]")
                try:
                    processed, skipped, errors, total = image_translate_future.result()
                finally:
                    if image_translate_executor is not None:
                        image_translate_executor.shutdown(wait=False, cancel_futures=False)
            else:
                prefetched_regions = {}
                if image_prefetch_future is not None:
                    try:
                        prefetched_regions = image_prefetch_future.result()
                    except Exception as e:
                        self.console.print(f"[yellow]Warning: Image pre-scan failed: {e}[/yellow]")
                        prefetched_regions = {}
                    finally:
                        if image_prefetch_executor is not None:
                            image_prefetch_executor.shutdown(wait=False, cancel_futures=False)
                self.console.print("[cyan]Scanning images for text (OCR)...[/cyan]")
                processed, skipped, errors, total = self._translate_images(book, prefetched_regions, True)
            self.console.print(
                f"[cyan]Image OCR summary:[/cyan] processed={processed}, skipped={skipped}, errors={errors}, total={total}"
            )
        else:
            processed = skipped = errors = total = 0
        images_elapsed = time.perf_counter() - images_start
        if output_path:
            checkpoint["images_done"] = True
            self._save_resume_checkpoint(output_path, checkpoint)

        # Helper: translate a single short text (used for metadata + TOC)
        def translate_single(text: str) -> str:
            """Translate a single short text string."""
            if not text or not text.strip():
                return text

            if self.cache:
                cached = self.cache.get(
                    text,
                    self.effective_source_lang,
                    self.target_lang,
                    self.service.__class__.__name__
                )
                if cached:
                    return cached

            try:
                translations = self.service.translate([text], self.effective_source_lang, self.target_lang)
                translated = translations[0] if translations else text

                if self.cache:
                    self.cache.put(
                        text,
                        translated,
                        self.effective_source_lang,
                        self.target_lang,
                        self.service.__class__.__name__
                    )

                return translated
            except Exception as e:
                self.console.print(f"[yellow]Warning: Failed to translate '{text}': {e}[/yellow]")
                return text

        # Translate metadata (title, description, subject)
        meta_start = time.perf_counter()
        if not effective_images_only:
            self.console.print("[cyan]Translating book metadata...[/cyan]")
            translated_meta = self.parser.translate_metadata(book, translate_single)
            for field, pairs in translated_meta.items():
                for original, translated in pairs:
                    self.console.print(f"  [dim]{field}:[/dim] {original} → {translated}")

            # Update metadata language
            self.console.print("[cyan]Updating metadata language...[/cyan]")
            self.parser.update_metadata_language(book, self.target_lang)

            # Translate TOC labels
            self.console.print("[cyan]Translating table of contents...[/cyan]")
            self.parser.update_toc_labels(book, translate_single)
        meta_elapsed = time.perf_counter() - meta_start
        if output_path:
            checkpoint["metadata_done"] = True
            self._save_resume_checkpoint(output_path, checkpoint)

        # Save output EPUB
        save_start = time.perf_counter()
        self.console.print(f"[cyan]Saving translated EPUB to:[/cyan] {output_path}")
        self.parser.save(book, output_path)
        save_elapsed = time.perf_counter() - save_start
        if output_path:
            checkpoint["saved_done"] = True
            self._save_resume_checkpoint(output_path, checkpoint)

        total_elapsed = time.perf_counter() - total_start
        perf = {
            "total_sec": round(total_elapsed, 3),
            "chapters_sec": round(chapter_elapsed, 3),
            "images_sec": round(images_elapsed, 3),
            "metadata_toc_sec": round(meta_elapsed, 3),
            "styles_sec": round(style_elapsed, 3),
            "save_sec": round(save_elapsed, 3),
        }
        if self.cache:
            perf["translation_cache"] = self.cache.stats()
        if self.ocr_cache:
            perf["ocr_cache"] = self.ocr_cache.stats()
        self._last_report = {
            "output_path": output_path,
            "effective_source_lang": self.effective_source_lang,
            "target_lang": self.target_lang,
            "images": {
                "processed": processed,
                "skipped": skipped,
                "errors": errors,
                "total": total,
            },
            "performance": perf,
        }
        self.console.print("[cyan]Performance:[/cyan] " + json.dumps(perf, ensure_ascii=False))

        self.console.print(f"[green]✓ Translation complete![/green]")
        return output_path

    def get_last_report(self) -> Dict:
        return dict(self._last_report) if self._last_report else {}

    def _translate_images(
        self,
        book,
        prefetched_regions: Optional[Dict[str, List]] = None,
        show_progress: bool = True,
        background_log_interval: int = 10,
    ) -> tuple[int, int, int, int]:
        """Translate text found in images via OCR.

        Returns:
            A tuple: (processed, skipped, errors, total)
        """
        from ebooklib import epub
        from .image_translator import ImageTranslator

        # Keep OCR reader instances thread-local to avoid cross-thread sharing.
        thread_state = threading.local()

        def get_image_translator() -> ImageTranslator:
            translator = getattr(thread_state, "image_translator", None)
            if translator is None:
                translator = ImageTranslator(
                    source_lang=self.effective_source_lang,
                    target_lang=self.target_lang,
                )
                thread_state.image_translator = translator
            return translator

        prefetch_map = prefetched_regions or {}

        def process_one_image(item):
            translator = get_image_translator()
            regions = prefetch_map.get(item.file_name) if item.file_name in prefetch_map else None
            result = translator.process_image(
                item.get_content(),
                item.media_type,
                self._translate_texts_with_cache,
                regions=regions,
            )
            return item, result

        # Collect processable images first to know the total count
        image_items = [
            item for item in book.get_items()
            if isinstance(item, epub.EpubImage) and get_image_translator().can_process(item.media_type)
        ]

        total = len(image_items)
        if total == 0:
            return (0, 0, 0, 0)

        processed = 0
        skipped = 0
        errors = 0

        # If pre-scan already determined "no translatable text", skip those upfront.
        translate_items = []
        pre_skipped = 0
        for item in image_items:
            if item.file_name in prefetch_map and prefetch_map[item.file_name] == []:
                pre_skipped += 1
            else:
                translate_items.append(item)

        skipped += pre_skipped
        translate_total = len(translate_items)
        self.console.print(
            f"[cyan]Image pre-scan summary:[/cyan] total={total}, skipped={pre_skipped}, to_translate={translate_total}"
        )

        if translate_total == 0:
            return (0, skipped, errors, total)

        def run_translate_with_progress():
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console,
            ) as progress:
                task = progress.add_task(
                    f"[green]Translating images 0/{translate_total}...",
                    total=translate_total,
                )
                run_translate_core(progress, task)

        def run_translate_core(progress: Optional[Progress], task: Optional[int]):
            nonlocal processed, skipped, errors
            completed = 0

            def maybe_log_background_progress(force: bool = False):
                if show_progress:
                    return
                if completed == 0:
                    return
                if force or (completed % max(1, background_log_interval) == 0):
                    self.console.print(
                        f"[cyan]Background image translation:[/cyan] {completed}/{translate_total}"
                    )

            if self.image_threads > 1:
                executor = ThreadPoolExecutor(max_workers=self.image_threads)
                interrupted = False
                try:
                    futures = {
                        executor.submit(process_one_image, item): item
                        for item in translate_items
                    }

                    for future in as_completed(futures):
                        item = futures[future]
                        try:
                            _, result = future.result()
                            if result is not None:
                                item.set_content(result)
                                processed += 1
                            else:
                                skipped += 1
                        except Exception as e:
                            self.console.print(
                                f"[yellow]Warning: Failed to process image '{item.file_name}': {e}[/yellow]"
                            )
                            errors += 1
                        finally:
                            completed += 1
                            if progress is not None and task is not None:
                                progress.update(
                                    task,
                                    advance=1,
                                    description=f"[green]Translating images {completed}/{translate_total}...",
                                )
                            else:
                                maybe_log_background_progress()
                except KeyboardInterrupt:
                    interrupted = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                finally:
                    if not interrupted:
                        executor.shutdown(wait=True, cancel_futures=False)
            else:
                for idx, item in enumerate(translate_items, start=1):
                    try:
                        _, result = process_one_image(item)
                        if result is not None:
                            item.set_content(result)
                            processed += 1
                        else:
                            skipped += 1
                    except Exception as e:
                        self.console.print(
                            f"[yellow]Warning: Failed to process image '{item.file_name}': {e}[/yellow]"
                        )
                        errors += 1
                    finally:
                        completed += 1
                        if progress is not None and task is not None:
                            progress.update(
                                task,
                                advance=1,
                                description=f"[green]Translating images {idx}/{translate_total}...",
                            )
                        else:
                            maybe_log_background_progress()

            maybe_log_background_progress(force=True)

        if show_progress:
            run_translate_with_progress()
        else:
            run_translate_core(None, None)

        return (processed, skipped, errors, total)

    @staticmethod
    def _update_prefetch_progress(
        progress: Progress,
        task_id: int,
        prefetch_state: Dict[str, int],
        prefetch_lock: threading.Lock,
    ) -> None:
        """Refresh pre-scan progress task from shared state."""
        with prefetch_lock:
            total = prefetch_state.get("total", 0)
            completed = prefetch_state.get("completed", 0)
        progress.update(
            task_id,
            total=total if total > 0 else 0,
            completed=min(completed, total) if total > 0 else 0,
            description=f"[blue]Pre-scanning images {completed}/{total}...[/blue]",
        )

    def _prefetch_image_regions(
        self,
        book,
        source_lang: str,
        prefetch_state: Optional[Dict[str, int]] = None,
        prefetch_lock: Optional[threading.Lock] = None,
    ) -> Dict[str, List]:
        """Pre-scan OCR regions for images so OCR work can overlap chapter translation."""
        from ebooklib import epub
        from .image_translator import ImageTranslator

        thread_state = threading.local()

        def get_image_translator() -> ImageTranslator:
            translator = getattr(thread_state, "image_translator", None)
            if translator is None:
                translator = ImageTranslator(
                    source_lang=source_lang,
                    target_lang=self.target_lang,
                )
                thread_state.image_translator = translator
            return translator

        image_items = [
            item for item in book.get_items()
            if isinstance(item, epub.EpubImage) and get_image_translator().can_process(item.media_type)
        ]

        if not image_items:
            if prefetch_state is not None and prefetch_lock is not None:
                with prefetch_lock:
                    prefetch_state["total"] = 0
                    prefetch_state["completed"] = 0
            return {}
        if prefetch_state is not None and prefetch_lock is not None:
            with prefetch_lock:
                prefetch_state["total"] = len(image_items)
                prefetch_state["completed"] = 0

        regions_by_file: Dict[str, List] = {}

        def serialize_regions(regions) -> List[Dict]:
            return [
                {
                    "bbox": region.bbox,
                    "text": region.text,
                    "confidence": region.confidence,
                }
                for region in regions
            ]

        def deserialize_regions(rows: List[Dict]):
            from .image_translator import OCRRegion
            return [
                OCRRegion(
                    bbox=row.get("bbox"),
                    text=row.get("text", ""),
                    confidence=float(row.get("confidence", 0.0)),
                )
                for row in rows
                if row.get("bbox") is not None
            ]

        def detect_one(item):
            translator = get_image_translator()
            image_bytes = item.get_content()
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            cache_key_source = source_lang
            cache_key_media = item.media_type
            cache_key_threshold = float(translator.confidence_threshold)

            if self.ocr_cache:
                cached = self.ocr_cache.get(
                    image_hash=image_hash,
                    source_lang=cache_key_source,
                    media_type=cache_key_media,
                    confidence_threshold=cache_key_threshold,
                )
                if cached is not None:
                    return item.file_name, deserialize_regions(cached)

            regions = translator.detect_regions(image_bytes, item.media_type)

            if self.ocr_cache:
                self.ocr_cache.put(
                    image_hash=image_hash,
                    source_lang=cache_key_source,
                    media_type=cache_key_media,
                    confidence_threshold=cache_key_threshold,
                    regions=serialize_regions(regions),
                )
            return item.file_name, regions

        if self.image_threads > 1:
            executor = ThreadPoolExecutor(max_workers=self.image_threads)
            interrupted = False
            try:
                futures = {executor.submit(detect_one, item): item for item in image_items}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        file_name, regions = future.result()
                        regions_by_file[file_name] = regions
                    except Exception:
                        # Leave missing entries to fall back to normal OCR path.
                        if item.file_name in regions_by_file:
                            del regions_by_file[item.file_name]
                    finally:
                        if prefetch_state is not None and prefetch_lock is not None:
                            with prefetch_lock:
                                prefetch_state["completed"] = prefetch_state.get("completed", 0) + 1
            except KeyboardInterrupt:
                interrupted = True
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            finally:
                if not interrupted:
                    executor.shutdown(wait=True, cancel_futures=False)
        else:
            for item in image_items:
                try:
                    file_name, regions = detect_one(item)
                    regions_by_file[file_name] = regions
                except Exception:
                    if item.file_name in regions_by_file:
                        del regions_by_file[item.file_name]
                finally:
                    if prefetch_state is not None and prefetch_lock is not None:
                        with prefetch_lock:
                            prefetch_state["completed"] = prefetch_state.get("completed", 0) + 1

        return regions_by_file

    def _translate_document(self, item, doc_num: int, total_docs: int):
        """Translate a single EPUB HTML document item.

        Args:
            item: EPUB document item (has get_content() and set_content())
            doc_num: Current document number (1-indexed)
            total_docs: Total number of documents
        """
        # Get content bytes
        content_bytes = item.get_content()

        # Extract texts
        texts, tree = self.extractor.extract_texts(content_bytes)

        if not texts:
            # No translatable text in this document
            return

        # Translate texts with cache
        translations = self._translate_texts_with_cache(texts)

        # Handle bilingual mode
        if self.bilingual:
            # Create bilingual pairs: original + translated
            bilingual_texts = []
            for original, translated in zip(texts, translations):
                if original.strip():
                    bilingual_texts.append(f"{original}\n\n{translated}")
                else:
                    bilingual_texts.append(translated)
            translations = bilingual_texts

        # Replace texts in tree
        new_content = self.extractor.replace_texts(tree, translations)

        # Set new content
        item.set_content(new_content)

    def _add_cjk_stylesheet(self, book, content_docs):
        """Add CJK-optimized CSS stylesheet to the EPUB book.

        Creates a CSS file with font-family, reduced font-size, and
        increased line-height, then links it to all content documents.
        Uses user-configured values from self.font_size, self.line_height,
        and self.font_family.
        """
        from ebooklib import epub

        lang = self.target_lang.lower()
        if self.font_family:
            font_stack = self.font_family
        else:
            font_stack = CJK_FONT_STACKS.get(lang, CJK_FONT_STACKS.get('ko'))

        css_content = (
            f'body {{\n'
            f'  font-family: {font_stack};\n'
            f'  font-size: {self.font_size};\n'
            f'  line-height: {self.line_height};\n'
            f'}}\n'
            f'p {{\n'
            f'  margin-bottom: {self.paragraph_spacing};\n'
            f'}}\n'
        )
        if self.heading_font_family:
            css_content += (
                f'h1, h2, h3, h4, h5, h6 {{\n'
                f'  font-family: {self.heading_font_family};\n'
                f'}}\n'
            )

        css_item = epub.EpubItem(
            uid='style_cjk',
            file_name='style/cjk.css',
            media_type='text/css',
            content=css_content.encode('utf-8'),
        )
        book.add_item(css_item)

        for item in content_docs:
            item.add_link(href='style/cjk.css', rel='stylesheet', type='text/css')

    def _translate_texts_with_cache(self, texts: List[str]) -> List[str]:
        """Translate texts, using cache where available.

        Args:
            texts: List of text strings to translate

        Returns:
            List of translated strings (same order as input)
        """
        if not texts:
            return []

        self._maybe_lock_source_lang(texts)
        source_lang = self.effective_source_lang
        translations = [None] * len(texts)
        texts_to_translate = []
        indices_to_translate = []

        # Check cache if enabled
        if self.cache:
            cached_translations = self.cache.get_batch(
                texts,
                source_lang,
                self.target_lang,
                self.service.__class__.__name__
            )

            for idx, text in enumerate(texts):
                if idx in cached_translations:
                    translations[idx] = cached_translations[idx]
                else:
                    texts_to_translate.append(text)
                    indices_to_translate.append(idx)
        else:
            # No cache, translate everything
            texts_to_translate = texts
            indices_to_translate = list(range(len(texts)))

        # Translate uncached texts
        if texts_to_translate:
            try:
                new_translations = self.service.translate(
                    texts_to_translate,
                    source_lang,
                    self.target_lang
                )

                # Store in cache and fill results
                if self.cache:
                    pairs = list(zip(texts_to_translate, new_translations))
                    self.cache.put_batch(
                        pairs,
                        source_lang,
                        self.target_lang,
                        self.service.__class__.__name__
                    )

                for idx, translated in zip(indices_to_translate, new_translations):
                    translations[idx] = translated

            except Exception as e:
                self.console.print(f"[red]Translation error: {e}[/red]")
                # Fill untranslated texts with originals
                for idx in indices_to_translate:
                    if translations[idx] is None:
                        translations[idx] = texts[idx]

        # Ensure no None values (fallback to original)
        for idx, text in enumerate(texts):
            if translations[idx] is None:
                translations[idx] = text

        return translations

    def _maybe_lock_source_lang(self, texts: List[str]) -> None:
        """Lock auto source language based on translated document texts."""
        if self._source_lang_locked or self.source_lang != 'auto':
            return

        sample = " ".join(t.strip() for t in texts if t and t.strip())
        if not sample:
            return

        detected = self._detect_lang_from_text(sample)
        if detected == 'auto':
            return
        # Avoid locking too early on short Latin-only fragments (e.g., nav labels).
        if detected == 'en':
            return

        with self._source_lang_lock:
            if self._source_lang_locked:
                return
            self.effective_source_lang = detected
            self._source_lang_locked = True

    def _resolve_effective_source_lang(self, content_docs) -> str:
        """Resolve source language used by all translation steps."""
        if self.source_lang != 'auto':
            return self.source_lang

        sample_text = self._build_source_lang_sample(content_docs)
        if not sample_text:
            return 'auto'

        detected = self._detect_lang_from_text(sample_text)
        return detected or 'auto'

    def _build_source_lang_sample(self, content_docs, max_chars: int = 12000) -> str:
        """Extract a bounded text sample from content documents."""
        chunks: List[str] = []
        current = 0

        for item in content_docs:
            try:
                texts, _ = self.extractor.extract_texts(item.get_content())
            except Exception:
                continue

            for text in texts:
                s = text.strip()
                if not s:
                    continue
                chunks.append(s)
                current += len(s)
                if current >= max_chars:
                    return " ".join(chunks)

        return " ".join(chunks)

    @staticmethod
    def _detect_lang_from_text(text: str) -> str:
        """Heuristic language detection for OCR/translation source alignment."""
        hangul = len(re.findall(r'[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]', text))
        hiragana = len(re.findall(r'[\u3040-\u309f]', text))
        katakana = len(re.findall(r'[\u30a0-\u30ff]', text))
        han = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', text))
        latin = len(re.findall(r'[A-Za-z]', text))
        bopomofo = len(re.findall(r'[\u3100-\u312f\u31a0-\u31bf]', text))

        if hangul > 0 and hangul >= (hiragana + katakana + han):
            return 'ko'

        if (hiragana + katakana) > 0:
            return 'ja'

        if han > 0:
            simplified_hits = sum(1 for ch in text if ch in SIMPLIFIED_HINT_CHARS)
            traditional_hits = sum(1 for ch in text if ch in TRADITIONAL_HINT_CHARS)

            if bopomofo > 0 or traditional_hits > simplified_hits:
                return 'zh-tw'
            if simplified_hits > traditional_hits:
                return 'zh-cn'
            return 'zh'

        if latin > 0:
            return 'en'

        return 'auto'

    def _source_lang_display(self) -> str:
        """Human-readable source language label with auto-detection detail."""
        if self.source_lang != 'auto':
            return lang_label(self.source_lang)
        if self.effective_source_lang != 'auto':
            return f"auto (detected: {self.effective_source_lang})"
        return lang_label('auto')
