import sqlite3
import os
import re
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def _row(row) -> dict | None:
    return dict(row) if row is not None else None


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id          INTEGER PRIMARY KEY,
                slug        TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sources (
                id            INTEGER PRIMARY KEY,
                topic_id      INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                source_ref    TEXT NOT NULL,
                source_title  TEXT DEFAULT '',
                source_type   TEXT DEFAULT '',
                ingest_status TEXT DEFAULT 'pending',
                error_message TEXT DEFAULT '',
                ingested_at   TEXT,
                chunk_count   INTEGER DEFAULT 0,
                UNIQUE(topic_id, source_ref)
            );

            CREATE TABLE IF NOT EXISTS tags (
                id       INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                name     TEXT NOT NULL,
                UNIQUE(topic_id, name)
            );

            CREATE TABLE IF NOT EXISTS source_tags (
                source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (source_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id          INTEGER PRIMARY KEY,
                topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                source_id   INTEGER REFERENCES sources(id) ON DELETE SET NULL,
                body        TEXT NOT NULL,
                chroma_id   TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
        """)
    conn.close()


# ── Topics ────────────────────────────────────────────────────────────────────

def create_topic(name: str, description: str = "", db_path: str = DB_PATH) -> dict:
    slug = _slugify(name)
    if not slug:
        raise ValueError(
            f"Topic name '{name}' has no alphanumeric characters — pick a real name"
        )
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "INSERT INTO topics (slug, name, description, created_at) VALUES (?, ?, ?, ?)",
            (slug, name, description, _now()),
        )
    row = conn.execute("SELECT * FROM topics WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return _row(row)


def get_topic_by_id(topic_id: int, db_path: str = DB_PATH) -> dict | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    conn.close()
    return _row(row)


def get_topic(slug: str, db_path: str = DB_PATH) -> dict | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM topics WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return _row(row)


def list_topics(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT t.*,
               COUNT(DISTINCT s.id)          AS source_count,
               COALESCE(SUM(s.chunk_count), 0) AS total_chunks
        FROM topics t
        LEFT JOIN sources s ON s.topic_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at DESC
    """).fetchall()
    conn.close()
    return _rows(rows)


def delete_topic(slug: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM topics WHERE slug = ?", (slug,))
    conn.close()


# ── Sources ───────────────────────────────────────────────────────────────────

def register_source(topic_id: int, source_ref: str, source_type: str = "", db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """INSERT INTO sources (topic_id, source_ref, source_type, ingest_status)
               VALUES (?, ?, ?, 'pending')
               ON CONFLICT(topic_id, source_ref) DO UPDATE SET
                   ingest_status = 'pending',
                   error_message = '',
                   source_type   = excluded.source_type""",
            (topic_id, source_ref, source_type),
        )
    row = conn.execute(
        "SELECT * FROM sources WHERE topic_id = ? AND source_ref = ?",
        (topic_id, source_ref),
    ).fetchone()
    conn.close()
    return _row(row)


def update_source_done(source_id: int, title: str, source_type: str, chunk_count: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """UPDATE sources
               SET source_title = ?, source_type = ?, chunk_count = ?,
                   ingest_status = 'done', error_message = '', ingested_at = ?
               WHERE id = ?""",
            (title, source_type, chunk_count, _now(), source_id),
        )
    conn.close()


def update_source_error(source_id: int, error_message: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "UPDATE sources SET ingest_status = 'error', error_message = ? WHERE id = ?",
            (error_message, source_id),
        )
    conn.close()


def get_source(topic_id: int, source_ref: str, db_path: str = DB_PATH) -> dict | None:
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM sources WHERE topic_id = ? AND source_ref = ?",
        (topic_id, source_ref),
    ).fetchone()
    conn.close()
    return _row(row)


def list_sources(topic_id: int, tag_name: str = "", db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    if tag_name:
        rows = conn.execute("""
            SELECT DISTINCT s.*
            FROM sources s
            JOIN source_tags st ON st.source_id = s.id
            JOIN tags tg        ON tg.id = st.tag_id
            WHERE s.topic_id = ? AND tg.name = ?
            ORDER BY s.id
        """, (topic_id, tag_name)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sources WHERE topic_id = ? ORDER BY id",
            (topic_id,),
        ).fetchall()

    sources = _rows(rows)

    if sources:
        ids = [s["id"] for s in sources]
        placeholders = ",".join("?" * len(ids))
        tag_rows = conn.execute(f"""
            SELECT st.source_id, tg.name
            FROM source_tags st
            JOIN tags tg ON tg.id = st.tag_id
            WHERE st.source_id IN ({placeholders})
            ORDER BY tg.name
        """, ids).fetchall()

        by_source: dict[int, list[str]] = {}
        for tr in tag_rows:
            by_source.setdefault(tr["source_id"], []).append(tr["name"])
        for s in sources:
            s["tags"] = by_source.get(s["id"], [])

    conn.close()
    return sources


def delete_source_record(source_id: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.close()


# ── Tags ──────────────────────────────────────────────────────────────────────

def get_or_create_tag(topic_id: int, name: str, db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO tags (topic_id, name) VALUES (?, ?)",
            (topic_id, name),
        )
    row = conn.execute(
        "SELECT * FROM tags WHERE topic_id = ? AND name = ?",
        (topic_id, name),
    ).fetchone()
    conn.close()
    return _row(row)


def add_source_tags(source_id: int, topic_id: int, tag_names: list[str], db_path: str = DB_PATH) -> None:
    if not tag_names:
        return
    conn = get_connection(db_path)
    with conn:
        for name in tag_names:
            conn.execute(
                "INSERT OR IGNORE INTO tags (topic_id, name) VALUES (?, ?)",
                (topic_id, name),
            )
            tag = conn.execute(
                "SELECT id FROM tags WHERE topic_id = ? AND name = ?",
                (topic_id, name),
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO source_tags (source_id, tag_id) VALUES (?, ?)",
                (source_id, tag["id"]),
            )
    conn.close()


def remove_source_tags(source_id: int, topic_id: int, tag_names: list[str], db_path: str = DB_PATH) -> None:
    if not tag_names:
        return
    conn = get_connection(db_path)
    with conn:
        for name in tag_names:
            tag = conn.execute(
                "SELECT id FROM tags WHERE topic_id = ? AND name = ?",
                (topic_id, name),
            ).fetchone()
            if tag:
                conn.execute(
                    "DELETE FROM source_tags WHERE source_id = ? AND tag_id = ?",
                    (source_id, tag["id"]),
                )
    conn.close()


def list_tags(topic_id: int, db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT tg.*, COUNT(st.source_id) AS source_count
        FROM tags tg
        LEFT JOIN source_tags st ON st.tag_id = tg.id
        WHERE tg.topic_id = ?
        GROUP BY tg.id
        ORDER BY tg.name
    """, (topic_id,)).fetchall()
    conn.close()
    return _rows(rows)


def rename_tag(topic_id: int, old_name: str, new_name: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "UPDATE tags SET name = ? WHERE topic_id = ? AND name = ?",
            (new_name, topic_id, old_name),
        )
    conn.close()


def merge_tags(topic_id: int, source_tag_name: str, target_tag_name: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO tags (topic_id, name) VALUES (?, ?)",
            (topic_id, target_tag_name),
        )
        target = conn.execute(
            "SELECT id FROM tags WHERE topic_id = ? AND name = ?",
            (topic_id, target_tag_name),
        ).fetchone()
        source = conn.execute(
            "SELECT id FROM tags WHERE topic_id = ? AND name = ?",
            (topic_id, source_tag_name),
        ).fetchone()
        if source:
            conn.execute("""
                INSERT OR IGNORE INTO source_tags (source_id, tag_id)
                SELECT source_id, ? FROM source_tags WHERE tag_id = ?
            """, (target["id"], source["id"]))
            conn.execute("DELETE FROM tags WHERE id = ?", (source["id"],))
    conn.close()


def delete_tag(topic_id: int, name: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM tags WHERE topic_id = ? AND name = ?", (topic_id, name))
    conn.close()


# ── Notes ─────────────────────────────────────────────────────────────────────

def create_note(topic_id: int, body: str, source_id: int | None = None, db_path: str = DB_PATH) -> dict:
    now = _now()
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute(
            "INSERT INTO notes (topic_id, source_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (topic_id, source_id, body, now, now),
        )
        note_id = cur.lastrowid
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return _row(row)


def update_note(note_id: int, body: str, db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "UPDATE notes SET body = ?, updated_at = ? WHERE id = ?",
            (body, _now(), note_id),
        )
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return _row(row)


def set_note_chroma_id(note_id: int, chroma_id: str, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("UPDATE notes SET chroma_id = ? WHERE id = ?", (chroma_id, note_id))
    conn.close()


def list_notes(topic_id: int, db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM notes WHERE topic_id = ? ORDER BY created_at DESC",
        (topic_id,),
    ).fetchall()
    conn.close()
    return _rows(rows)


def get_note(note_id: int, db_path: str = DB_PATH) -> dict | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return _row(row)


def delete_note(note_id: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.close()
