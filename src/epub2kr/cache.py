"""Translation cache module using SQLite for persistent storage.

This module provides a thread-safe translation cache that stores translations
keyed by (source_text_hash, source_lang, target_lang, service_name).
"""

import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class TranslationCache:
    """Thread-safe translation cache with SQLite backend.

    The cache stores translations with SHA-256 hashed keys and provides
    both single and batch operations for efficient lookups and storage.
    """

    def __init__(self, cache_dir: str = ".epub2kr_cache"):
        """Initialize the translation cache.

        Args:
            cache_dir: Directory name for cache storage. If relative, uses
                      user's home directory. Defaults to ".epub2kr" in home.
        """
        # Resolve cache directory
        if cache_dir.startswith(('/', '~')):
            cache_path = Path(cache_dir).expanduser()
        else:
            cache_path = Path.home() / ".epub2kr"

        cache_path.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_path / "cache.db"

        # Thread safety
        self._lock = threading.Lock()

        # Statistics tracking
        self._hits = 0
        self._misses = 0

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize or recreate the database with proper schema."""
        try:
            conn = self._get_connection()
            try:
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")

                # Create table if not exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS translations (
                        text_hash TEXT NOT NULL,
                        source_lang TEXT NOT NULL,
                        target_lang TEXT NOT NULL,
                        service TEXT NOT NULL,
                        source_text TEXT NOT NULL,
                        translation TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        PRIMARY KEY (text_hash, source_lang, target_lang, service)
                    )
                """)

                # Create index for faster lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_lookup
                    ON translations(text_hash, source_lang, target_lang, service)
                """)

                conn.commit()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            # Database is corrupted, recreate it
            self._recreate_db()

    def _recreate_db(self):
        """Recreate the database from scratch."""
        if self.db_path.exists():
            self.db_path.unlink()

        # Also remove WAL and SHM files if they exist
        for suffix in ['-wal', '-shm']:
            wal_file = Path(str(self.db_path) + suffix)
            if wal_file.exists():
                wal_file.unlink()

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper settings.

        Returns:
            SQLite connection object
        """
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _hash_text(self, text: str) -> str:
        """Generate SHA-256 hash of text.

        Args:
            text: Text to hash

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def get(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        service: str
    ) -> Optional[str]:
        """Look up a cached translation.

        Args:
            text: Source text to translate
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name

        Returns:
            Cached translation if found, None otherwise
        """
        text_hash = self._hash_text(text)

        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    cursor = conn.execute(
                        """
                        SELECT translation FROM translations
                        WHERE text_hash = ? AND source_lang = ?
                          AND target_lang = ? AND service = ?
                        """,
                        (text_hash, source_lang, target_lang, service)
                    )
                    row = cursor.fetchone()

                    if row:
                        self._hits += 1
                        return row['translation']
                    else:
                        self._misses += 1
                        return None
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                self._misses += 1
                return None

    def put(
        self,
        text: str,
        translation: str,
        source_lang: str,
        target_lang: str,
        service: str
    ):
        """Store a translation in the cache.

        Args:
            text: Source text
            translation: Translated text
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name
        """
        text_hash = self._hash_text(text)
        timestamp = int(datetime.now().timestamp())

        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO translations
                        (text_hash, source_lang, target_lang, service,
                         source_text, translation, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (text_hash, source_lang, target_lang, service,
                         text, translation, timestamp)
                    )
                    conn.commit()
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                # Retry once after recreation
                try:
                    conn = self._get_connection()
                    try:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO translations
                            (text_hash, source_lang, target_lang, service,
                             source_text, translation, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (text_hash, source_lang, target_lang, service,
                             text, translation, timestamp)
                        )
                        conn.commit()
                    finally:
                        conn.close()
                except sqlite3.DatabaseError:
                    # Silent fail on persistent errors
                    pass

    def get_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        service: str
    ) -> Dict[int, str]:
        """Batch lookup of cached translations.

        Args:
            texts: List of source texts to look up
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name

        Returns:
            Dictionary mapping text indices to cached translations
        """
        if not texts:
            return {}

        # Create hash to index mapping
        hash_to_indices = {}
        for i, text in enumerate(texts):
            text_hash = self._hash_text(text)
            if text_hash not in hash_to_indices:
                hash_to_indices[text_hash] = []
            hash_to_indices[text_hash].append(i)

        hashes = list(hash_to_indices.keys())
        results = {}

        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    # Use parameterized query with IN clause
                    placeholders = ','.join('?' * len(hashes))
                    query = f"""
                        SELECT text_hash, translation FROM translations
                        WHERE text_hash IN ({placeholders})
                          AND source_lang = ? AND target_lang = ? AND service = ?
                    """

                    cursor = conn.execute(
                        query,
                        hashes + [source_lang, target_lang, service]
                    )

                    for row in cursor:
                        text_hash = row['text_hash']
                        translation = row['translation']
                        # Map to all indices with this hash
                        for idx in hash_to_indices[text_hash]:
                            results[idx] = translation
                            self._hits += 1

                    # Count misses
                    self._misses += len(texts) - len(results)

                    return results
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                self._misses += len(texts)
                return {}

    def put_batch(
        self,
        pairs: List[Tuple[str, str]],
        source_lang: str,
        target_lang: str,
        service: str
    ):
        """Batch store translations in the cache.

        Args:
            pairs: List of (source_text, translation) tuples
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name
        """
        if not pairs:
            return

        timestamp = int(datetime.now().timestamp())

        # Prepare data for batch insert
        data = [
            (
                self._hash_text(text),
                source_lang,
                target_lang,
                service,
                text,
                translation,
                timestamp
            )
            for text, translation in pairs
        ]

        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO translations
                        (text_hash, source_lang, target_lang, service,
                         source_text, translation, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        data
                    )
                    conn.commit()
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                # Retry once after recreation
                try:
                    conn = self._get_connection()
                    try:
                        conn.executemany(
                            """
                            INSERT OR REPLACE INTO translations
                            (text_hash, source_lang, target_lang, service,
                             source_text, translation, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            data
                        )
                        conn.commit()
                    finally:
                        conn.close()
                except sqlite3.DatabaseError:
                    # Silent fail on persistent errors
                    pass

    def clear(self):
        """Clear all cached translations."""
        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    conn.execute("DELETE FROM translations")
                    conn.commit()
                    # Reset statistics
                    self._hits = 0
                    self._misses = 0
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()

    def prune(self, older_than_days: int) -> int:
        """Delete cached translations older than N days."""
        cutoff = int(datetime.now().timestamp()) - (older_than_days * 86400)
        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    cur = conn.execute("DELETE FROM translations WHERE timestamp < ?", (cutoff,))
                    conn.commit()
                    return cur.rowcount
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                return 0

    def stats(self) -> Dict:
        """Get cache statistics.

        Returns:
            Dictionary containing:
                - total_entries: Number of cached translations
                - db_size_bytes: Database file size in bytes
                - hit_rate: Cache hit rate (0.0 to 1.0)
                - hits: Total cache hits
                - misses: Total cache misses
        """
        with self._lock:
            try:
                conn = self._get_connection()
                try:
                    # Get total entries
                    cursor = conn.execute("SELECT COUNT(*) as count FROM translations")
                    total_entries = cursor.fetchone()['count']

                    # Get database size
                    db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

                    # Calculate hit rate
                    total_requests = self._hits + self._misses
                    hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

                    return {
                        'total_entries': total_entries,
                        'db_size_bytes': db_size,
                        'hit_rate': hit_rate,
                        'hits': self._hits,
                        'misses': self._misses
                    }
                finally:
                    conn.close()
            except sqlite3.DatabaseError:
                self._recreate_db()
                return {
                    'total_entries': 0,
                    'db_size_bytes': 0,
                    'hit_rate': 0.0,
                    'hits': self._hits,
                    'misses': self._misses
                }
