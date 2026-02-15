"""Extract translatable text from XHTML while preserving document structure."""

from typing import List, Tuple
from lxml import etree


class TextExtractor:
    """
    Extract and replace text from XHTML documents while preserving structure.

    This class handles the critical task of:
    1. Parsing XHTML content with proper namespace handling
    2. Extracting all text nodes in document order
    3. Filtering out non-translatable content (code, pre, etc.)
    4. Replacing text nodes with translations while preserving HTML structure
    """

    # XHTML namespace
    XHTML_NS = "http://www.w3.org/1999/xhtml"
    NSMAP = {None: XHTML_NS}

    # Elements whose content should NOT be translated
    NO_TRANSLATE_TAGS = {'code', 'pre', 'script', 'style'}

    def __init__(self):
        """Initialize the text extractor."""
        self.parser = etree.HTMLParser(encoding='utf-8')

    def extract_texts(self, xhtml_content: bytes) -> Tuple[List[str], etree._ElementTree]:
        """
        Extract translatable text segments from XHTML content.

        Args:
            xhtml_content: XHTML content as bytes

        Returns:
            Tuple of (list of translatable text segments, parsed element tree)
            The tree is needed for later text replacement.
        """
        # Parse the XHTML content
        tree = etree.fromstring(xhtml_content, self.parser)

        # Collect all translatable text nodes
        texts = []

        def should_translate(element) -> bool:
            """Check if element's text should be translated."""
            # Get tag name without namespace
            tag = etree.QName(element).localname if isinstance(element.tag, str) else element.tag
            return tag not in self.NO_TRANSLATE_TAGS

        def walk_tree(element, in_no_translate=False):
            """Recursively walk the tree and collect text nodes."""
            # Check if this element should not be translated
            tag = etree.QName(element).localname if isinstance(element.tag, str) else element.tag
            current_no_translate = in_no_translate or (tag in self.NO_TRANSLATE_TAGS)

            # Extract element.text (text before first child)
            if element.text and not current_no_translate:
                text = element.text.strip()
                if text:  # Skip empty/whitespace-only text
                    texts.append(text)

            # Process children
            for child in element:
                walk_tree(child, current_no_translate)

                # Extract child.tail (text after child element)
                if child.tail and not current_no_translate:
                    text = child.tail.strip()
                    if text:
                        texts.append(text)

        # Start walking from root
        walk_tree(tree)

        # Return both texts and tree (tree needed for replacement)
        return texts, tree

    def replace_texts(self, tree: etree._Element, translations: List[str]) -> bytes:
        """
        Replace text nodes in the tree with translations.

        Args:
            tree: Parsed element tree (from extract_texts)
            translations: List of translated text segments (same order as extracted)

        Returns:
            Modified XHTML content as bytes

        Raises:
            ValueError: If number of translations doesn't match extracted texts
        """
        # Use an iterator for translations
        trans_iter = iter(translations)

        def should_translate(element) -> bool:
            """Check if element's text should be translated."""
            tag = etree.QName(element).localname if isinstance(element.tag, str) else element.tag
            return tag not in self.NO_TRANSLATE_TAGS

        def walk_and_replace(element, in_no_translate=False):
            """Recursively walk the tree and replace text nodes."""
            # Check if this element should not be translated
            tag = etree.QName(element).localname if isinstance(element.tag, str) else element.tag
            current_no_translate = in_no_translate or (tag in self.NO_TRANSLATE_TAGS)

            # Replace element.text
            if element.text and not current_no_translate:
                text = element.text.strip()
                if text:
                    try:
                        # Get next translation and preserve surrounding whitespace
                        translated = next(trans_iter)
                        # Preserve leading/trailing whitespace from original
                        leading_ws = element.text[:len(element.text) - len(element.text.lstrip())]
                        trailing_ws = element.text[len(element.text.rstrip()):]
                        element.text = leading_ws + translated + trailing_ws
                    except StopIteration:
                        raise ValueError("Not enough translations provided")

            # Process children
            for child in element:
                walk_and_replace(child, current_no_translate)

                # Replace child.tail
                if child.tail and not current_no_translate:
                    text = child.tail.strip()
                    if text:
                        try:
                            translated = next(trans_iter)
                            # Preserve whitespace
                            leading_ws = child.tail[:len(child.tail) - len(child.tail.lstrip())]
                            trailing_ws = child.tail[len(child.tail.rstrip()):]
                            child.tail = leading_ws + translated + trailing_ws
                        except StopIteration:
                            raise ValueError("Not enough translations provided")

        # Replace all texts
        walk_and_replace(tree)

        # Check if all translations were used
        try:
            next(trans_iter)
            raise ValueError("Too many translations provided")
        except StopIteration:
            pass  # Expected - all translations were used

        # Serialize back to bytes
        result = etree.tostring(
            tree,
            encoding='utf-8',
            method='html',
            pretty_print=False
        )

        return result

    def extract_with_metadata(self, xhtml_content: bytes) -> Tuple[List[dict], etree._ElementTree]:
        """
        Extract text with metadata about each segment.

        Args:
            xhtml_content: XHTML content as bytes

        Returns:
            Tuple of (list of text metadata dicts, parsed element tree)
            Each dict contains: {'text': str, 'tag': str, 'attrs': dict}
        """
        tree = etree.fromstring(xhtml_content, self.parser)
        segments = []

        def walk_tree(element, in_no_translate=False):
            """Recursively walk and collect text with metadata."""
            tag = etree.QName(element).localname if isinstance(element.tag, str) else element.tag
            current_no_translate = in_no_translate or (tag in self.NO_TRANSLATE_TAGS)

            if element.text and not current_no_translate:
                text = element.text.strip()
                if text:
                    segments.append({
                        'text': text,
                        'tag': tag,
                        'attrs': dict(element.attrib)
                    })

            for child in element:
                walk_tree(child, current_no_translate)

                if child.tail and not current_no_translate:
                    text = child.tail.strip()
                    if text:
                        child_tag = etree.QName(child).localname if isinstance(child.tag, str) else child.tag
                        segments.append({
                            'text': text,
                            'tag': f'{tag}_tail',  # Parent tag + tail marker
                            'attrs': {}
                        })

        walk_tree(tree)
        return segments, tree
