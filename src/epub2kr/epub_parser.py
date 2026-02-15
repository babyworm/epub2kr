"""EPUB parsing and reconstruction with layout preservation."""

from typing import List
from pathlib import Path
import ebooklib
from ebooklib import epub


class EpubParser:
    """Handle EPUB file reading, writing, and manipulation."""

    @staticmethod
    def load(path: str) -> epub.EpubBook:
        """
        Load an EPUB file.

        Args:
            path: Path to the EPUB file

        Returns:
            EpubBook object

        Raises:
            FileNotFoundError: If the EPUB file doesn't exist
            Exception: If the EPUB file is corrupted or invalid
        """
        epub_path = Path(path)
        if not epub_path.exists():
            raise FileNotFoundError(f"EPUB file not found: {path}")

        try:
            book = epub.read_epub(str(epub_path))
            return book
        except Exception as e:
            raise Exception(f"Failed to load EPUB file: {e}") from e

    @staticmethod
    def _fix_toc_uids(book: epub.EpubBook) -> None:
        """Fix None UIDs in TOC items (ebooklib loses them on read)."""
        import uuid

        def fix_item(item, index=0):
            if isinstance(item, tuple) or isinstance(item, list):
                section, children = item[0], item[1]
                if hasattr(section, 'uid') and not section.uid:
                    section.uid = f"toc_fix_{index}_{uuid.uuid4().hex[:8]}"
                for i, child in enumerate(children):
                    fix_item(child, i)
            elif isinstance(item, epub.Link):
                if not item.uid:
                    item.uid = f"toc_fix_{index}_{uuid.uuid4().hex[:8]}"
            elif isinstance(item, epub.Section):
                if hasattr(item, 'uid') and not item.uid:
                    item.uid = f"toc_fix_{index}_{uuid.uuid4().hex[:8]}"

        for i, item in enumerate(book.toc):
            fix_item(item, i)

    @staticmethod
    def save(book: epub.EpubBook, path: str) -> None:
        """
        Save an EPUB file.

        Args:
            book: EpubBook object to save
            path: Destination path for the EPUB file

        Raises:
            Exception: If saving fails
        """
        try:
            EpubParser._fix_toc_uids(book)
            epub.write_epub(path, book)
        except Exception as e:
            raise Exception(f"Failed to save EPUB file: {e}") from e

    @staticmethod
    def get_content_documents(book: epub.EpubBook) -> List[epub.EpubHtml]:
        """
        Get all XHTML content documents in spine order.

        Args:
            book: EpubBook object

        Returns:
            List of EpubHtml items in reading order
        """
        content_docs = []

        # Get spine items (defines reading order)
        spine = book.spine

        for item_id, linear in spine:
            # Get the item by ID
            item = book.get_item_with_id(item_id)

            # Only include XHTML/HTML documents
            if item and isinstance(item, epub.EpubHtml):
                content_docs.append(item)

        return content_docs

    @staticmethod
    def update_metadata_language(book: epub.EpubBook, target_lang: str) -> None:
        """
        Update the book's language metadata.

        Args:
            book: EpubBook object to modify
            target_lang: Target language code (e.g., 'en', 'zh', 'ja')
        """
        # Clear existing language metadata
        if 'http://purl.org/dc/elements/1.1/' in book.metadata:
            if 'language' in book.metadata['http://purl.org/dc/elements/1.1/']:
                book.metadata['http://purl.org/dc/elements/1.1/']['language'] = []

        # Set new language
        book.set_language(target_lang)

    @staticmethod
    def translate_metadata(book: epub.EpubBook, translator_func, fields=None) -> dict:
        """Translate book metadata fields (title, description, subject).

        Args:
            book: EpubBook object to modify
            translator_func: Function that takes text and returns translation
                           Signature: translator_func(text: str) -> str
            fields: List of DC fields to translate
                    (default: ['title', 'description', 'subject'])

        Returns:
            Dict of field -> list of (original, translated) pairs
        """
        if fields is None:
            fields = ['title', 'description', 'subject']

        DC_NS = 'http://purl.org/dc/elements/1.1/'
        translated = {}

        for field in fields:
            metadata = book.get_metadata('DC', field)
            if not metadata:
                continue

            pairs = []
            new_entries = []
            for value, attrs in metadata:
                if value and value.strip():
                    new_value = translator_func(value)
                    pairs.append((value, new_value))
                    new_entries.append((new_value, attrs))
                else:
                    new_entries.append((value, attrs))

            if pairs and DC_NS in book.metadata and field in book.metadata[DC_NS]:
                book.metadata[DC_NS][field] = new_entries
                translated[field] = pairs

        return translated

    @staticmethod
    def update_toc_labels(book: epub.EpubBook, translator_func) -> None:
        """
        Translate Table of Contents labels.

        Args:
            book: EpubBook object to modify
            translator_func: Function that takes text and returns translation
                           Signature: translator_func(text: str) -> str
        """
        import uuid

        def translate_toc_item(item, index=0):
            """Recursively translate TOC item and its children, returning new item."""
            if isinstance(item, tuple):
                # item is (Section, [children])
                section, children = item
                # Create new section with translated title
                if hasattr(section, 'title') and section.title:
                    translated_title = translator_func(section.title)
                    new_section = epub.Section(translated_title)
                    # Preserve or generate uid
                    if hasattr(section, 'uid') and section.uid:
                        new_section.uid = section.uid
                    else:
                        new_section.uid = f"toc_section_{index}"
                else:
                    new_section = section
                # Recursively translate children
                new_children = []
                if children:
                    for i, child in enumerate(children):
                        new_children.append(translate_toc_item(child, i))
                return (new_section, new_children)
            elif isinstance(item, epub.Link):
                # Create new Link with translated title
                if item.title:
                    translated_title = translator_func(item.title)
                    # Generate uid if missing (ebooklib loses UIDs when reading EPUBs)
                    uid = item.uid if item.uid else f"toc_link_{index}_{uuid.uuid4().hex[:8]}"
                    new_link = epub.Link(item.href, translated_title, uid=uid)
                    return new_link
                return item
            elif isinstance(item, epub.Section):
                # Create new Section with translated title
                if item.title:
                    translated_title = translator_func(item.title)
                    new_section = epub.Section(translated_title)
                    # Preserve or generate uid
                    if hasattr(item, 'uid') and item.uid:
                        new_section.uid = item.uid
                    else:
                        new_section.uid = f"toc_section_{index}"
                    return new_section
                return item
            else:
                return item

        # Get TOC and translate each item
        toc = book.toc
        new_toc = []
        for i, item in enumerate(toc):
            new_toc.append(translate_toc_item(item, i))

        # Update the TOC with new items
        book.toc = new_toc
