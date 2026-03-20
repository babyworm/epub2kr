"""Codex CLI translation service."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from .base import BaseTranslationService


class CodexCLIService(BaseTranslationService):
    """Translate text by invoking `codex exec` in non-interactive mode."""

    VALID_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-5.4",
        reasoning_effort: str = "low",
        cli_path: str = None,
        profile: str = None,
        timeout: int = 180,
        max_retries: int = 1,
        retry_backoff_base: float = 0.5,
        retry_backoff_max: float = 2.0,
        base_url: str = None,
    ):
        """Initialize Codex CLI service.

        Args:
            api_key: Optional Codex API key (sets `CODEX_API_KEY` for the subprocess)
            model: Codex model name
            reasoning_effort: Codex reasoning effort
            cli_path: Path to the `codex` executable (default: resolve from PATH)
            profile: Optional Codex config profile to use
            timeout: Subprocess timeout in seconds
            base_url: Accepted for CLI compatibility; unused by Codex CLI
        """
        super().__init__(
            max_retries=max_retries,
            retry_backoff_base=retry_backoff_base,
            retry_backoff_max=retry_backoff_max,
        )
        self.api_key = api_key or os.getenv("CODEX_API_KEY")
        self.model = model
        self.reasoning_effort = reasoning_effort.lower()
        if self.reasoning_effort not in self.VALID_REASONING_EFFORTS:
            allowed = ", ".join(sorted(self.VALID_REASONING_EFFORTS))
            raise ValueError(
                f"Invalid Codex reasoning effort '{reasoning_effort}'. "
                f"Expected one of: {allowed}"
            )

        self.profile = profile or os.getenv("CODEX_PROFILE")
        self.timeout = int(timeout)
        self.base_url = base_url
        resolved = cli_path or os.getenv("CODEX_CLI_PATH") or "codex"
        self.cli_path = self._resolve_cli_path(resolved)

    def name(self) -> str:
        """Return service name."""
        return "codex"

    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments through Codex CLI."""
        if not texts:
            return []

        results = list(texts)
        indices_to_translate = []
        texts_to_translate = []
        for idx, text in enumerate(texts):
            if not text or text.isspace():
                continue
            indices_to_translate.append(idx)
            texts_to_translate.append(text)

        if not texts_to_translate:
            return results

        try:
            translated_batch = self._with_retries(
                lambda: self._translate_batch(texts_to_translate, source_lang, target_lang)
            )
            for idx, translated in zip(indices_to_translate, translated_batch):
                results[idx] = translated
        except Exception as exc:
            print(f"Codex translation error: {exc}")

        return results

    def _translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate one batch with a single `codex exec` invocation."""
        prompt = self._build_prompt(texts, source_lang, target_lang)
        schema = self._build_schema(len(texts))

        with tempfile.TemporaryDirectory(prefix="epub2kr-codex-") as temp_dir:
            temp_root = Path(temp_dir)
            workspace_dir = temp_root / "workspace"
            workspace_dir.mkdir()
            schema_path = temp_root / "translation-schema.json"
            output_path = temp_root / "translation-result.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")

            command = [
                self.cli_path,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--color",
                "never",
                "-C",
                str(workspace_dir),
                "-s",
                "read-only",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-m",
                self.model,
                "-c",
                'approval_policy="never"',
                "-c",
                f'model_reasoning_effort="{self.reasoning_effort}"',
                "-c",
                'model_reasoning_summary="none"',
                "-",
            ]
            if self.profile:
                command[2:2] = ["-p", self.profile]

            env = os.environ.copy()
            if self.api_key:
                env["CODEX_API_KEY"] = self.api_key

            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                env=env,
            )

            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                detail = stderr or stdout or "unknown codex exec failure"
                raise RuntimeError(f"codex exec failed: {detail}")

            if not output_path.exists():
                raise RuntimeError("codex exec did not produce an output payload")

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            translations = payload.get("translations")
            if not isinstance(translations, list) or len(translations) != len(texts):
                raise RuntimeError("codex exec returned an unexpected translation payload")

            normalized = []
            for original, translated in zip(texts, translations):
                if not isinstance(translated, str):
                    raise RuntimeError("codex exec returned a non-string translation")
                normalized.append(translated if translated.strip() else original)
            return normalized

    def _resolve_cli_path(self, cli_path: str) -> str:
        """Resolve the Codex executable from PATH or an explicit location."""
        cli_candidate = Path(cli_path).expanduser()
        if cli_candidate.is_file():
            return str(cli_candidate)

        resolved = shutil.which(cli_path)
        if resolved:
            return resolved

        raise ValueError(
            "Codex CLI not found. Install `@openai/codex`, add `codex` to PATH, "
            "or set `CODEX_CLI_PATH`."
        )

    def _build_prompt(self, texts: List[str], source_lang: str, target_lang: str) -> str:
        """Build the prompt sent to Codex."""
        source_name = self._format_language_name(source_lang)
        target_name = self._format_language_name(target_lang)
        payload = {
            "source_language": source_name,
            "target_language": target_name,
            "items": [{"index": idx, "text": text} for idx, text in enumerate(texts)],
        }
        return (
            f"You are a professional translator. Translate every item from {source_name} "
            f"to {target_name}.\n"
            "Return JSON that matches the provided schema.\n"
            "Rules:\n"
            "- Preserve the input order exactly.\n"
            "- Do not merge, split, omit, or renumber items.\n"
            "- Output only the translation for each item, with no explanations.\n"
            "- Preserve paragraph breaks, punctuation, numbering, and inline markup when natural.\n"
            "- If a term should remain untranslated, keep it as-is.\n\n"
            f"Input JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        )

    def _build_schema(self, item_count: int) -> dict:
        """Build a JSON schema for the expected structured response."""
        return {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": item_count,
                    "maxItems": item_count,
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }

    def _format_language_name(self, lang_code: str) -> str:
        """Format language code to human-readable name."""
        lang_code = lang_code.lower()
        mapping = {
            "auto": "the detected source language",
            "en": "English",
            "zh": "Chinese",
            "zh-cn": "Simplified Chinese",
            "zh-tw": "Traditional Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "ru": "Russian",
            "pt": "Portuguese",
            "it": "Italian",
            "nl": "Dutch",
            "pl": "Polish",
            "ar": "Arabic",
            "hi": "Hindi",
        }
        return mapping.get(lang_code, lang_code.upper())
