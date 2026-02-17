"""CLI interface for epub2kr."""
import click
from rich.console import Console
from pathlib import Path

from .translator import EpubTranslator, lang_label, validate_lang_code, CJK_LANGS, CJK_FONT_STACKS
from .config import load_config


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('input_file', type=click.Path(exists=True), required=False, default=None)
@click.option('-o', '--output', type=click.Path(), default=None, help='Output file path')
@click.option('-s', '--service', type=click.Choice(['google', 'deepl', 'openai', 'ollama']), default=None, help='Translation service')
@click.option('-li', '--source-lang', default=None, help='Source language code')
@click.option('-lo', '--target-lang', default=None, help='Target language code')
@click.option('-t', '--threads', default=None, type=int, help='Number of threads')
@click.option('-j', '--image-threads', default=None, type=int, help='Number of threads for image OCR/translation')
@click.option('--no-cache', is_flag=True, help='Disable translation cache')
@click.option('--bilingual', is_flag=True, default=None, help='Generate bilingual output')
@click.option('--api-key', default=None, help='API key for translation service')
@click.option('--model', default=None, help='Model name (for OpenAI/Ollama)')
@click.option('--base-url', default=None, help='Custom API base URL')
@click.option('--font-size', default=None, help='CJK font size (e.g. 0.95em, 14px)')
@click.option('--line-height', default=None, help='CJK line height (e.g. 1.8, 2.0)')
@click.option('--font-family', default=None, help='CJK font family (auto-detect if not set)')
@click.option('--heading-font', default=None, help='Heading font family (defaults to body font)')
@click.option('--paragraph-spacing', default=None, help='Paragraph spacing (e.g. 0.5em, 1em)')
@click.option('--no-translate-images', is_flag=True, help='Skip OCR translation of image text')
@click.option('--setup', is_flag=True, help='Run interactive setup wizard')
def main(input_file, output, service, source_lang, target_lang, threads, image_threads, no_cache, bilingual, api_key, model, base_url, font_size, line_height, font_family, heading_font, paragraph_spacing, no_translate_images, setup):
    """epub2kr - Translate EPUB files while preserving layout.

    \b
    Language codes:
      ko: Korean,  en: English, zh: Chinese, ja: Japanese,
      es: Spanish, fr: French,  de: German,  ru: Russian,
      pt: Portuguese, it: Italian, vi: Vietnamese, th: Thai

    \b
    Example usage:
        epub2kr book.epub -lo zh
        epub2kr book.epub -s deepl -lo ja --api-key YOUR_KEY
        epub2kr book.epub -s ollama --model llama2 -lo ko
        epub2kr book.epub -s openai --model gpt-4 --api-key sk-xxx -lo es
        epub2kr book.epub -j 4 -lo ko
        epub2kr book.epub --bilingual -lo zh
        epub2kr --setup
    """
    console = Console()

    # --setup: run interactive wizard and exit
    if setup:
        from .config import run_setup
        run_setup()
        return

    # Normal translation mode requires input file
    if input_file is None:
        console.print("[bold red]Error:[/bold red] Please specify an EPUB file.")
        console.print("Usage: epub2kr book.epub -lo ko")
        console.print("Setup: epub2kr --setup")
        console.print("Help:  epub2kr --help")
        raise click.Abort()

    try:
        # Load saved config as defaults
        cfg = load_config()

        # Apply saved config for unset options
        service = service or cfg["service"]
        source_lang = source_lang or cfg["source_lang"]
        target_lang = target_lang or cfg["target_lang"]
        threads = threads or cfg["threads"]
        if image_threads is None:
            image_threads = cfg.get("image_threads")

        # Validate language codes
        source_lang = validate_lang_code(source_lang)
        target_lang = validate_lang_code(target_lang)
        if bilingual is None:
            bilingual = cfg["bilingual"]

        # Build service kwargs from options
        service_kwargs = {}
        if api_key:
            service_kwargs['api_key'] = api_key
        if model or cfg.get("model"):
            service_kwargs['model'] = model or cfg["model"]
        if base_url:
            service_kwargs['base_url'] = base_url
        # CJK font settings from CLI or config
        effective_font_size = font_size or cfg.get("font_size", "0.95em")
        effective_line_height = line_height or cfg.get("line_height", "1.8")
        effective_font_family = font_family or cfg.get("font_family")
        effective_heading_font = heading_font or cfg.get("heading_font_family")
        effective_paragraph_spacing = paragraph_spacing or cfg.get("paragraph_spacing", "0.5em")

        # Create translator
        translator = EpubTranslator(
            service_name=service,
            source_lang=source_lang,
            target_lang=target_lang,
            threads=threads,
            image_threads=image_threads,
            use_cache=not no_cache,
            bilingual=bilingual,
            font_size=effective_font_size,
            line_height=effective_line_height,
            font_family=effective_font_family,
            heading_font_family=effective_heading_font,
            paragraph_spacing=effective_paragraph_spacing,
            translate_images=not no_translate_images,
            **service_kwargs
        )

        # Translate the EPUB
        output_path = translator.translate_epub(input_file, output)

        # Print summary
        console.print()
        console.print("[bold green]Translation Summary:[/bold green]")
        console.print(f"  Input:  {input_file}")
        console.print(f"  Output: {output_path}")
        console.print(f"  Service: {service}")
        if source_lang == 'auto' and translator.effective_source_lang != 'auto':
            source_display = f"auto (detected: {translator.effective_source_lang})"
        else:
            source_display = lang_label(source_lang)
        console.print(f"  Language: {source_display} → {lang_label(target_lang)}")
        console.print(f"  Threads: chapters={threads}, images={image_threads if image_threads is not None else threads}")
        console.print(f"  Cache: {'disabled' if no_cache else 'enabled'}")
        if bilingual:
            console.print(f"  Mode: Bilingual")
        if target_lang.lower() in CJK_LANGS:
            resolved_font = effective_font_family or CJK_FONT_STACKS.get(target_lang.lower(), CJK_FONT_STACKS.get('ko'))
            console.print(f"  Body:  font={effective_font_size}, line-height={effective_line_height}, spacing={effective_paragraph_spacing}")
            console.print(f"  Font:  {resolved_font}")
            if effective_heading_font:
                console.print(f"  Heading: {effective_heading_font}")
        console.print()
        console.print("[bold green]✓ Done![/bold green]")

    except KeyboardInterrupt:
        console.print("[yellow]Cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise click.Abort()


if __name__ == '__main__':
    main()
