"""Persistent cache for OCR pre-scan regions."""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


class OCRPrescanCache:
    """Thread-safe OCR pre-scan cache using SQLite backend."""
    CACHE_KEY_VERSION = "v2"

    def __init__(self, cache_dir: str = ".epub2kr_cache"):
        if cache_dir.startswith(("/", "~")):
            cache_path = Path(cache_dir).expanduser()
        else:
            cache_path = Path.home() / ".epub2kr"

        cache_path.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_path / "ocr_cache.db"
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_regions (
                    image_hash TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    confidence_threshold REAL NOT NULL,
                    regions_json TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    PRIMARY KEY (image_hash, source_lang, media_type, confidence_threshold)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ocr_lookup
                ON ocr_regions(image_hash, source_lang, media_type, confidence_threshold)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_translations (
                    image_hash TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    confidence_threshold REAL NOT NULL,
                    regions_hash TEXT NOT NULL,
                    translations_json TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    PRIMARY KEY (
                        image_hash, source_lang, target_lang, service_name,
                        media_type, confidence_threshold, regions_hash
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ocr_translation_lookup
                ON ocr_translations(
                    image_hash, source_lang, target_lang, service_name,
                    media_type, confidence_threshold, regions_hash
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get(
        self,
        image_hash: str,
        source_lang: str,
        media_type: str,
        confidence_threshold: float,
    ) -> Optional[List[Dict[str, Any]]]:
        source_lang = self._namespaced_source_lang(source_lang)
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    """
                    SELECT regions_json FROM ocr_regions
                    WHERE image_hash = ? AND source_lang = ? AND media_type = ?
                      AND confidence_threshold = ?
                    """,
                    (image_hash, source_lang, media_type, confidence_threshold),
                ).fetchone()
                if not row:
                    return None
                return json.loads(row["regions_json"])
            finally:
                conn.close()

    def put(
        self,
        image_hash: str,
        source_lang: str,
        media_type: str,
        confidence_threshold: float,
        regions: List[Dict[str, Any]],
    ) -> None:
        source_lang = self._namespaced_source_lang(source_lang)
        payload = json.dumps(regions, ensure_ascii=False)
        ts = int(datetime.now().timestamp())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ocr_regions
                    (image_hash, source_lang, media_type, confidence_threshold, regions_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (image_hash, source_lang, media_type, confidence_threshold, payload, ts),
                )
                conn.commit()
            finally:
                conn.close()

    def clear(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM ocr_regions")
                conn.execute("DELETE FROM ocr_translations")
                conn.commit()
            finally:
                conn.close()

    def prune(self, older_than_days: int) -> int:
        cutoff = int(datetime.now().timestamp()) - (older_than_days * 86400)
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "DELETE FROM ocr_regions WHERE timestamp < ?",
                    (cutoff,),
                )
                cur_t = conn.execute(
                    "DELETE FROM ocr_translations WHERE timestamp < ?",
                    (cutoff,),
                )
                conn.commit()
                return cur.rowcount + cur_t.rowcount
            finally:
                conn.close()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("SELECT COUNT(*) AS count FROM ocr_regions").fetchone()
                row_t = conn.execute("SELECT COUNT(*) AS count FROM ocr_translations").fetchone()
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                return {
                    "total_entries": int(row["count"]) if row else 0,
                    "translation_entries": int(row_t["count"]) if row_t else 0,
                    "db_size_bytes": db_size,
                }
            finally:
                conn.close()

    def get_translations(
        self,
        image_hash: str,
        source_lang: str,
        target_lang: str,
        service_name: str,
        media_type: str,
        confidence_threshold: float,
        regions_hash: str,
    ) -> Optional[List[str]]:
        source_lang = self._namespaced_source_lang(source_lang)
        service_name = self._namespaced_service_name(service_name)
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    """
                    SELECT translations_json FROM ocr_translations
                    WHERE image_hash = ? AND source_lang = ? AND target_lang = ?
                      AND service_name = ? AND media_type = ? AND confidence_threshold = ?
                      AND regions_hash = ?
                    """,
                    (
                        image_hash,
                        source_lang,
                        target_lang,
                        service_name,
                        media_type,
                        confidence_threshold,
                        regions_hash,
                    ),
                ).fetchone()
                if not row:
                    return None
                payload = json.loads(row["translations_json"])
                if isinstance(payload, list):
                    return [str(x) for x in payload]
                return None
            finally:
                conn.close()

    def put_translations(
        self,
        image_hash: str,
        source_lang: str,
        target_lang: str,
        service_name: str,
        media_type: str,
        confidence_threshold: float,
        regions_hash: str,
        translations: List[str],
    ) -> None:
        source_lang = self._namespaced_source_lang(source_lang)
        service_name = self._namespaced_service_name(service_name)
        payload = json.dumps(list(translations), ensure_ascii=False)
        ts = int(datetime.now().timestamp())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ocr_translations
                    (image_hash, source_lang, target_lang, service_name, media_type,
                     confidence_threshold, regions_hash, translations_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        image_hash,
                        source_lang,
                        target_lang,
                        service_name,
                        media_type,
                        confidence_threshold,
                        regions_hash,
                        payload,
                        ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def _namespaced_source_lang(self, source_lang: str) -> str:
        return f"{source_lang}::{self.CACHE_KEY_VERSION}"

    def _namespaced_service_name(self, service_name: str) -> str:
        return f"{service_name}::{self.CACHE_KEY_VERSION}"
