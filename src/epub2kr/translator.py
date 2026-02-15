"""Main EPUB translation orchestrator."""
import os
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console

from .epub_parser import EpubParser
from .text_extractor import TextExtractor
from .cache import TranslationCache
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


class EpubTranslator:
    """Orchestrates the EPUB translation pipeline."""

    def __init__(
        self,
        service_name: str = "google",
        source_lang: str = "auto",
        target_lang: str = "en",
        threads: int = 1,
        use_cache: bool = True,
        bilingual: bool = False,
        font_size: str = "0.95em",
        line_height: str = "1.8",
        font_family: Optional[str] = None,
        heading_font_family: Optional[str] = None,
        paragraph_spacing: str = "0.5em",
        **service_kwargs
    ):
        """Initialize the EPUB translator.

        Args:
            service_name: Translation service to use
            source_lang: Source language code (auto-detect if 'auto')
            target_lang: Target language code
            threads: Number of parallel threads for chapter translation
            use_cache: Whether to use translation cache
            bilingual: Generate bilingual output (original + translated)
            font_size: CSS font-size for CJK output (e.g. '0.95em', '14px')
            line_height: CSS line-height for CJK output (e.g. '1.8', '2.0')
            font_family: CSS font-family override (None = auto-detect by language)
            heading_font_family: CSS font-family for headings (None = same as body)
            paragraph_spacing: CSS margin-bottom for paragraphs (e.g. '0.5em')
            **service_kwargs: Additional arguments for translation service
        """
        self.service = get_service(service_name, **service_kwargs)
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.threads = threads
        self.cache = TranslationCache() if use_cache else None
        self.bilingual = bilingual
        self.font_size = font_size
        self.line_height = line_height
        self.font_family = font_family
        self.heading_font_family = heading_font_family
        self.paragraph_spacing = paragraph_spacing
        self.extractor = TextExtractor()
        self.parser = EpubParser()
        self.console = Console()

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

        self.console.print(f"[cyan]Loading EPUB:[/cyan] {input_path}")
        book = self.parser.load(input_path)

        # Get all content documents in spine order
        content_docs = self.parser.get_content_documents(book)
        total_docs = len(content_docs)

        self.console.print(f"[cyan]Found {total_docs} content documents[/cyan]")
        self.console.print(f"[cyan]Translation:[/cyan] {lang_label(self.source_lang)} → {lang_label(self.target_lang)}")
        self.console.print(f"[cyan]Service:[/cyan] {self.service.__class__.__name__}")
        self.console.print(f"[cyan]Threads:[/cyan] {self.threads}")
        self.console.print(f"[cyan]Cache:[/cyan] {'enabled' if self.cache else 'disabled'}")
        if self.bilingual:
            self.console.print("[cyan]Mode:[/cyan] Bilingual")

        # Translate documents with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            main_task = progress.add_task("[green]Translating chapters...", total=total_docs)

            if self.threads > 1:
                # Parallel translation
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = {
                        executor.submit(self._translate_document, item, idx + 1, total_docs): idx
                        for idx, item in enumerate(content_docs)
                    }

                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            self.console.print(f"[red]Error translating document {idx + 1}:[/red] {e}")
                        progress.advance(main_task)
            else:
                # Sequential translation
                for idx, item in enumerate(content_docs):
                    try:
                        self._translate_document(item, idx + 1, total_docs)
                    except Exception as e:
                        self.console.print(f"[red]Error translating document {idx + 1}:[/red] {e}")
                    progress.advance(main_task)

        # Add CJK stylesheet if targeting CJK language
        if self.target_lang.lower() in CJK_LANGS:
            self.console.print("[cyan]Adding CJK font stylesheet...[/cyan]")
            self._add_cjk_stylesheet(book, content_docs)

        # Update metadata language
        self.console.print("[cyan]Updating metadata language...[/cyan]")
        self.parser.update_metadata_language(book, self.target_lang)

        # Translate TOC labels
        self.console.print("[cyan]Translating table of contents...[/cyan]")

        def translate_toc_label(label: str) -> str:
            """Translate a single TOC label."""
            if not label or not label.strip():
                return label

            # Use cache if available
            if self.cache:
                cached = self.cache.get(label, self.source_lang, self.target_lang, self.service.__class__.__name__)
                if cached:
                    return cached

            # Translate
            try:
                translations = self.service.translate([label], self.source_lang, self.target_lang)
                translated = translations[0] if translations else label

                # Store in cache
                if self.cache:
                    self.cache.put(label, translated, self.source_lang, self.target_lang, self.service.__class__.__name__)

                return translated
            except Exception as e:
                self.console.print(f"[yellow]Warning: Failed to translate TOC label '{label}': {e}[/yellow]")
                return label

        self.parser.update_toc_labels(book, translate_toc_label)

        # Save output EPUB
        self.console.print(f"[cyan]Saving translated EPUB to:[/cyan] {output_path}")
        self.parser.save(book, output_path)

        self.console.print(f"[green]✓ Translation complete![/green]")
        return output_path

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

        translations = [None] * len(texts)
        texts_to_translate = []
        indices_to_translate = []

        # Check cache if enabled
        if self.cache:
            cached_translations = self.cache.get_batch(
                texts,
                self.source_lang,
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
                    self.source_lang,
                    self.target_lang
                )

                # Store in cache and fill results
                if self.cache:
                    pairs = list(zip(texts_to_translate, new_translations))
                    self.cache.put_batch(
                        pairs,
                        self.source_lang,
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
