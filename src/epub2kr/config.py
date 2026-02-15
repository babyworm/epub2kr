"""Configuration management for epub2kr."""
import json
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_PATH = Path.home() / ".epub2kr" / "config.json"

DEFAULTS = {
    "service": "google",
    "source_lang": "auto",
    "target_lang": "en",
    "threads": 4,
    "model": None,
    "bilingual": False,
    "font_size": "0.95em",
    "line_height": "1.8",
    "font_family": None,  # None = auto-detect by target language
}


def load_config() -> Dict[str, Any]:
    """Load saved configuration, merged with defaults."""
    config = DEFAULTS.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config: Dict[str, Any]):
    """Save configuration to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def run_setup():
    """Interactive setup wizard."""
    from rich.console import Console
    from rich.prompt import Prompt, Confirm

    console = Console()
    current = load_config()

    console.print("\n[bold cyan]epub2kr Setup[/bold cyan]\n")
    console.print("Current values shown as defaults. Press Enter to keep them.\n")

    # Service
    service = Prompt.ask(
        "Translation service",
        choices=["google", "deepl", "openai", "ollama"],
        default=current["service"],
    )

    # Source language
    source_lang = Prompt.ask(
        "Source language (auto=auto-detect)",
        default=current["source_lang"],
    )

    # Target language
    target_lang = Prompt.ask(
        "Target language",
        default=current["target_lang"],
    )

    # Threads
    threads = int(Prompt.ask(
        "Number of threads",
        default=str(current["threads"]),
    ))

    # Model (for OpenAI/Ollama)
    model = None
    if service in ("openai", "ollama"):
        default_model = current.get("model") or ""
        model_input = Prompt.ask(
            f"Model (for {service})",
            default=default_model,
        )
        if model_input:
            model = model_input

    # Bilingual
    bilingual = Confirm.ask(
        "Bilingual mode (original + translation)",
        default=current["bilingual"],
    )

    # CJK font settings
    console.print("\n[bold cyan]CJK Font Settings[/bold cyan]")
    console.print("Applied when translating to ko, ja, zh, zh-cn, zh-tw.\n")

    font_size = Prompt.ask(
        "Font size (e.g. 0.95em, 14px, 90%)",
        default=current.get("font_size", "0.95em"),
    )

    line_height = Prompt.ask(
        "Line height (e.g. 1.8, 2.0)",
        default=current.get("line_height", "1.8"),
    )

    font_family_default = current.get("font_family") or ""
    font_family_input = Prompt.ask(
        "Font family (leave empty for auto-detect by language)",
        default=font_family_default,
    )
    font_family = font_family_input if font_family_input else None

    # Save
    new_config = {
        "service": service,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "threads": threads,
        "model": model,
        "bilingual": bilingual,
        "font_size": font_size,
        "line_height": line_height,
        "font_family": font_family,
    }
    save_config(new_config)

    console.print(f"\n[green]Configuration saved:[/green] {CONFIG_PATH}")
    console.print()
    for k, v in new_config.items():
        console.print(f"  {k}: {v}")
    console.print()


