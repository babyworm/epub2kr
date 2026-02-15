"""Restyle an existing EPUB's CJK font and line-height without re-translating."""

import click
from rich.console import Console
from pathlib import Path
from ebooklib import epub

from .translator import CJK_LANGS, CJK_FONT_STACKS
from .epub_parser import EpubParser


def restyle_epub(
    input_path: str,
    output_path: str,
    font_size: str = "0.95em",
    line_height: str = "1.8",
    font_family: str | None = None,
    lang: str | None = None,
) -> str:
    """Restyle an EPUB's CJK stylesheet.

    Args:
        input_path: Path to input EPUB file
        output_path: Path to save restyled EPUB
        font_size: CSS font-size value
        line_height: CSS line-height value
        font_family: CSS font-family override (None = auto-detect)
        lang: Language code override (None = read from EPUB metadata)

    Returns:
        The output path where the file was saved
    """
    book = EpubParser.load(input_path)

    # Detect language from metadata if not provided
    if not lang:
        lang_meta = book.get_metadata('DC', 'language')
        lang = lang_meta[0][0] if lang_meta else 'ko'
    lang = lang.lower()

    # Resolve font stack
    if font_family:
        font_stack = font_family
    else:
        font_stack = CJK_FONT_STACKS.get(lang, CJK_FONT_STACKS.get('ko'))

    css_content = (
        f'body {{\n'
        f'  font-family: {font_stack};\n'
        f'  font-size: {font_size};\n'
        f'  line-height: {line_height};\n'
        f'}}\n'
    )

    # Find existing cjk.css and replace, or create new
    existing_css = None
    for item in book.get_items():
        if item.get_name() == 'style/cjk.css':
            existing_css = item
            break

    if existing_css:
        existing_css.set_content(css_content.encode('utf-8'))
    else:
        css_item = epub.EpubItem(
            uid='style_cjk',
            file_name='style/cjk.css',
            media_type='text/css',
            content=css_content.encode('utf-8'),
        )
        book.add_item(css_item)

        # Link to all content documents
        content_docs = EpubParser.get_content_documents(book)
        for item in content_docs:
            item.add_link(href='style/cjk.css', rel='stylesheet', type='text/css')

    EpubParser.save(book, output_path)
    return output_path


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('input_file', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), default=None, help='Output file path')
@click.option('--inplace', is_flag=True, help='Overwrite input file in place')
@click.option('--font-size', default='0.95em', help='CSS font size (e.g. 0.95em, 14px, 90%)')
@click.option('--line-height', default='1.8', help='CSS line height (e.g. 1.8, 2.0)')
@click.option('--font-family', default=None, help='CSS font family (auto-detect if not set)')
@click.option('--lang', default=None, help='Language code override (auto-detect from EPUB if not set)')
@click.option('--gui', is_flag=True, help='Open browser GUI for interactive preview')
def main(input_file, output, inplace, font_size, line_height, font_family, lang, gui):
    """epub2kr-restyle - Adjust font and line-height of an existing EPUB.

    \b
    Examples:
      epub2kr-restyle book.ko.epub --font-size 1em --line-height 2.0
      epub2kr-restyle book.ko.epub --inplace --font-family "Nanum Gothic"
      epub2kr-restyle book.ko.epub -o book.restyled.epub --line-height 1.6
      epub2kr-restyle book.ko.epub --gui
    """
    console = Console()

    if gui:
        from .gui import run_gui
        console.print("[cyan]Opening restyle preview in browser...[/cyan]")
        settings = run_gui(input_file)
        if settings is None:
            console.print("[yellow]Cancelled.[/yellow]")
            return

        # Apply GUI-selected settings
        font_size = settings.get('font_size', font_size)
        line_height = settings.get('line_height', line_height)
        font_family = settings.get('font_family') or font_family

    if inplace and output:
        console.print("[bold red]Error:[/bold red] Cannot use both --inplace and --output")
        raise click.Abort()

    if inplace:
        output_path = input_file
    elif output:
        output_path = output
    else:
        # Default: input_stem.restyled.epub
        p = Path(input_file)
        output_path = str(p.parent / f"{p.stem}.restyled{p.suffix}")

    try:
        result = restyle_epub(
            input_path=input_file,
            output_path=output_path,
            font_size=font_size,
            line_height=line_height,
            font_family=font_family,
            lang=lang,
        )

        # Resolve font for display
        if not lang:
            book = EpubParser.load(input_file)
            lang_meta = book.get_metadata('DC', 'language')
            lang = lang_meta[0][0].lower() if lang_meta else 'ko'
        resolved_font = font_family or CJK_FONT_STACKS.get(lang, CJK_FONT_STACKS.get('ko'))

        console.print()
        console.print("[bold green]Restyle Summary:[/bold green]")
        console.print(f"  Input:  {input_file}")
        console.print(f"  Output: {result}")
        console.print(f"  Style:  font={font_size}, line-height={line_height}")
        console.print(f"  Family: {resolved_font}")
        console.print()
        console.print("[bold green]✓ Done![/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise click.Abort()


if __name__ == '__main__':
    main()
