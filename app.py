from __future__ import annotations

import json
import random
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS


# ============================================================
# Chechen Dictionary API with Noxçiy Abat Latin support
#
# Put this file in the same folder as one of these:
#   words_latin.json
#   words.json
#   words_translated.json
#
# Run:
#   pip install flask flask-cors
#   python app.py
#
# Test:
#   http://localhost:27016/stats
#   http://localhost:27016/search?q=ламаз
#   http://localhost:27016/search?q=lamaz
#   http://localhost:27016/search?q=молитва
#   http://localhost:27016/search?q=molitva
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "chechen_dictionary.db"
PORT = 27016

WORD_FILES = [
    BASE_DIR / "words_latin.json",
    BASE_DIR / "words.json",
    BASE_DIR / "words_translated.json",
]

WORD_FIELDS = (
    "chechen_word",
    "chechen_latin",
    "english_translation",
    "russian_translation",
    "russian_latin",
    "part_of_speech",
    "pronunciation",
    "example_chechen",
    "example_chechen_latin",
    "example_english",
    "category",
)

VALID_LANGUAGES = {
    "all",
    "chechen",
    "chechen_latin",
    "latin",
    "english",
    "russian",
    "russian_latin",
}

app = Flask(__name__)
CORS(app)


# ============================================================
# Noxçiy Abat transliteration
# ============================================================

MULTI_MAP: list[tuple[str, str]] = [
    ("Аь", "Ä"), ("аь", "ä"),
    ("Оь", "Ö"), ("оь", "ö"),
    ("Уь", "Ü"), ("уь", "ü"),

    ("ГӀ", "Ġ"), ("гӀ", "ġ"),
    ("Гӏ", "Ġ"), ("гӏ", "ġ"),
    ("ГI", "Ġ"), ("гI", "ġ"),
    ("ГІ", "Ġ"), ("гІ", "ġ"),

    ("КӀ", "K̇"), ("кӀ", "k̇"),
    ("Кӏ", "K̇"), ("кӏ", "k̇"),
    ("КI", "K̇"), ("кI", "k̇"),
    ("КІ", "K̇"), ("кІ", "k̇"),

    ("ПӀ", "Ṗ"), ("пӀ", "ṗ"),
    ("Пӏ", "Ṗ"), ("пӏ", "ṗ"),
    ("ПI", "Ṗ"), ("пI", "ṗ"),
    ("ПІ", "Ṗ"), ("пІ", "ṗ"),

    ("ТӀ", "Ṫ"), ("тӀ", "ṫ"),
    ("Тӏ", "Ṫ"), ("тӏ", "ṫ"),
    ("ТI", "Ṫ"), ("тI", "ṫ"),
    ("ТІ", "Ṫ"), ("тІ", "ṫ"),

    ("ЦӀ", "Ċ"), ("цӀ", "ċ"),
    ("Цӏ", "Ċ"), ("цӏ", "ċ"),
    ("ЦI", "Ċ"), ("цI", "ċ"),
    ("ЦІ", "Ċ"), ("цІ", "ċ"),

    ("ЧӀ", "Ç̇"), ("чӀ", "ç̇"),
    ("Чӏ", "Ç̇"), ("чӏ", "ç̇"),
    ("ЧI", "Ç̇"), ("чI", "ç̇"),
    ("ЧІ", "Ç̇"), ("чІ", "ç̇"),

    ("Хь", "Ẋ"), ("хь", "ẋ"),

    ("ХӀ", "H"), ("хӀ", "h"),
    ("Хӏ", "H"), ("хӏ", "h"),
    ("ХI", "H"), ("хI", "h"),
    ("ХІ", "H"), ("хІ", "h"),

    ("Кх", "Q"), ("кх", "q"),
    ("Къ", "Q̇"), ("къ", "q̇"),
]

SINGLE_MAP: dict[str, str] = {
    "А": "A", "а": "a",
    "Б": "B", "б": "b",
    "В": "V", "в": "v",
    "Г": "G", "г": "g",
    "Д": "D", "д": "d",
    "Е": "E", "е": "e",
    "Ё": "Yo", "ё": "yo",
    "Ж": "Ż", "ж": "ż",
    "З": "Z", "з": "z",
    "И": "I", "и": "i",
    "Й": "Y", "й": "y",
    "К": "K", "к": "k",
    "Л": "L", "л": "l",
    "М": "M", "м": "m",
    "Н": "N", "н": "n",
    "О": "O", "о": "o",
    "П": "P", "п": "p",
    "Р": "R", "р": "r",
    "С": "S", "с": "s",
    "Т": "T", "т": "t",
    "У": "U", "у": "u",
    "Ф": "F", "ф": "f",
    "Х": "X", "х": "x",
    "Ц": "C", "ц": "c",
    "Ч": "Ç", "ч": "ç",
    "Ш": "Ş", "ш": "ş",
    "Щ": "Şç", "щ": "şç",
    "Ъ": "", "ъ": "",
    "Ь": "", "ь": "",
    "Ы": "Y", "ы": "y",
    "Э": "E", "э": "e",
    "Ю": "Yu", "ю": "yu",
    "Я": "Ya", "я": "ya",
    "Ӏ": "", "ӏ": "",
    "І": "", "і": "",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm(value: Any) -> str:
    return clean_text(value).casefold()


def norm_latin(value: Any) -> str:
    """
    Normalize Latin search text.

    This keeps diacritics, but also makes common search easier:
    - q̇ / q can still be searched as typed if exact diacritic exists
    - Unicode composed/decomposed characters become consistent
    """
    text = clean_text(value)
    return unicodedata.normalize("NFC", text).casefold()


def transliterate_noxciy(text: Any) -> str:
    """Transliterate Cyrillic Chechen/Russian to the Noxçiy Abat Latin style."""
    text = clean_text(text)

    text = (
        text.replace("’", "I")
        .replace("ʼ", "I")
        .replace("`", "I")
        .replace("´", "I")
    )

    for cyr, lat in sorted(MULTI_MAP, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(cyr, lat)

    result = []
    for char in text:
        result.append(SINGLE_MAP.get(char, char))

    return unicodedata.normalize("NFC", "".join(result))


def make_latin_ascii_fallback(text: Any) -> str:
    """
    Make a loose ASCII fallback for easier typing.

    Examples:
      żiżig -> zizig
      q̇amel -> qamel
      ẋo -> xo
      şiyla -> siyla
      ç̇enig -> cenig
    """
    text = clean_text(text).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    replacements = {
        "ç": "c",
        "ş": "s",
        "ġ": "g",
        "ż": "z",
        "ẋ": "x",
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ṗ": "p",
        "ṫ": "t",
        "ċ": "c",
        "ḳ": "k",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ============================================================
# Database helpers
# ============================================================

def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def find_words_file() -> Path | None:
    for path in WORD_FILES:
        if path.exists():
            return path
    return None


def migrate_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(dictionary)").fetchall()
    }

    missing_columns = {
        "chechen_latin": "TEXT DEFAULT ''",
        "russian_latin": "TEXT DEFAULT ''",
        "example_chechen_latin": "TEXT DEFAULT ''",
        "chechen_latin_norm": "TEXT DEFAULT ''",
        "russian_latin_norm": "TEXT DEFAULT ''",
        "latin_ascii_norm": "TEXT DEFAULT ''",
    }

    for column, sql_type in missing_columns.items():
        if column not in columns:
            print(f"Adding missing DB column: {column}")
            conn.execute(f"ALTER TABLE dictionary ADD COLUMN {column} {sql_type}")


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chechen_word TEXT NOT NULL,
            chechen_latin TEXT DEFAULT '',
            english_translation TEXT DEFAULT '',
            russian_translation TEXT DEFAULT '',
            russian_latin TEXT DEFAULT '',
            part_of_speech TEXT DEFAULT '',
            pronunciation TEXT DEFAULT '',
            example_chechen TEXT DEFAULT '',
            example_chechen_latin TEXT DEFAULT '',
            example_english TEXT DEFAULT '',
            category TEXT DEFAULT 'imported',

            chechen_norm TEXT DEFAULT '',
            chechen_latin_norm TEXT DEFAULT '',
            english_norm TEXT DEFAULT '',
            russian_norm TEXT DEFAULT '',
            russian_latin_norm TEXT DEFAULT '',
            latin_ascii_norm TEXT DEFAULT '',
            search_norm TEXT DEFAULT '',

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    migrate_schema(conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_chechen_norm ON dictionary(chechen_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chechen_latin_norm ON dictionary(chechen_latin_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_english_norm ON dictionary(english_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_russian_norm ON dictionary(russian_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_russian_latin_norm ON dictionary(russian_latin_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_latin_ascii_norm ON dictionary(latin_ascii_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON dictionary(category)")


def make_search_norm(word: dict[str, str]) -> str:
    latin_ascii = " ".join(
        [
            make_latin_ascii_fallback(word.get("chechen_latin", "")),
            make_latin_ascii_fallback(word.get("russian_latin", "")),
        ]
    )

    return norm(
        " ".join(
            [
                word.get("chechen_word", ""),
                word.get("chechen_latin", ""),
                word.get("english_translation", ""),
                word.get("russian_translation", ""),
                word.get("russian_latin", ""),
                word.get("part_of_speech", ""),
                word.get("pronunciation", ""),
                word.get("category", ""),
                latin_ascii,
            ]
        )
    )


def make_latin_ascii_norm(word: dict[str, str]) -> str:
    return norm(
        " ".join(
            [
                make_latin_ascii_fallback(word.get("chechen_latin", "")),
                make_latin_ascii_fallback(word.get("russian_latin", "")),
            ]
        )
    )


def clean_word(raw: dict[str, Any]) -> dict[str, str]:
    word = {field: clean_text(raw.get(field, "")) for field in WORD_FIELDS}

    if not word["chechen_word"]:
        raise ValueError("Missing chechen_word")

    if not word["chechen_latin"]:
        word["chechen_latin"] = transliterate_noxciy(word["chechen_word"])

    if not word["russian_latin"]:
        word["russian_latin"] = transliterate_noxciy(word["russian_translation"])

    if not word["example_chechen_latin"] and word["example_chechen"]:
        word["example_chechen_latin"] = transliterate_noxciy(word["example_chechen"])

    # Keep old API compatible.
    if not word["english_translation"]:
        word["english_translation"] = word["russian_translation"]

    if not word["category"]:
        word["category"] = "imported"

    return word


def row_to_word(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "chechen_word": row["chechen_word"],
        "chechen_latin": row["chechen_latin"] or "",
        "english_translation": row["english_translation"] or "",
        "russian_translation": row["russian_translation"] or "",
        "russian_latin": row["russian_latin"] or "",
        "part_of_speech": row["part_of_speech"] or "",
        "pronunciation": row["pronunciation"] or "",
        "example_chechen": row["example_chechen"] or "",
        "example_chechen_latin": row["example_chechen_latin"] or "",
        "example_english": row["example_english"] or "",
        "category": row["category"] or "imported",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def load_words_from_json(path: Path) -> list[dict[str, str]]:
    print(f"Loading {path.name} ...")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise RuntimeError(f"{path.name} must contain a JSON list.")

    words: list[dict[str, str]] = []
    skipped = 0

    for item in data:
        try:
            if isinstance(item, dict):
                words.append(clean_word(item))
            else:
                skipped += 1
        except ValueError:
            skipped += 1

    print(f"Loaded {len(words)} valid words")
    if skipped:
        print(f"Skipped {skipped} invalid entries")

    return words


def database_has_words(conn: sqlite3.Connection) -> bool:
    count = conn.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]
    return count > 0


def insert_words_bulk(conn: sqlite3.Connection, words: list[dict[str, str]]) -> int:
    now = utc_now()
    inserted = 0
    seen: set[tuple[str, str, str]] = set()
    batch: list[tuple[str, ...]] = []

    for word in words:
        key = (
            norm(word["chechen_word"]),
            norm(word["russian_translation"]),
            norm(word["english_translation"]),
        )

        if key in seen:
            continue

        seen.add(key)

        batch.append(
            (
                word["chechen_word"],
                word["chechen_latin"],
                word["english_translation"],
                word["russian_translation"],
                word["russian_latin"],
                word["part_of_speech"],
                word["pronunciation"],
                word["example_chechen"],
                word["example_chechen_latin"],
                word["example_english"],
                word["category"],
                norm(word["chechen_word"]),
                norm_latin(word["chechen_latin"]),
                norm(word["english_translation"]),
                norm(word["russian_translation"]),
                norm_latin(word["russian_latin"]),
                make_latin_ascii_norm(word),
                make_search_norm(word),
                now,
                now,
            )
        )

        if len(batch) >= 5000:
            conn.executemany(
                """
                INSERT INTO dictionary (
                    chechen_word,
                    chechen_latin,
                    english_translation,
                    russian_translation,
                    russian_latin,
                    part_of_speech,
                    pronunciation,
                    example_chechen,
                    example_chechen_latin,
                    example_english,
                    category,
                    chechen_norm,
                    chechen_latin_norm,
                    english_norm,
                    russian_norm,
                    russian_latin_norm,
                    latin_ascii_norm,
                    search_norm,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            inserted += len(batch)
            print(f"Imported {inserted} words ...")
            batch.clear()

    if batch:
        conn.executemany(
            """
            INSERT INTO dictionary (
                chechen_word,
                chechen_latin,
                english_translation,
                russian_translation,
                russian_latin,
                part_of_speech,
                pronunciation,
                example_chechen,
                example_chechen_latin,
                example_english,
                category,
                chechen_norm,
                chechen_latin_norm,
                english_norm,
                russian_norm,
                russian_latin_norm,
                latin_ascii_norm,
                search_norm,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
        inserted += len(batch)

    return inserted


def backfill_latin_columns(conn: sqlite3.Connection) -> int:
    """
    If you already have chechen_dictionary.db from the old app.py,
    this fills the new Latin columns automatically.
    """
    rows = conn.execute(
        """
        SELECT id,
               chechen_word,
               chechen_latin,
               english_translation,
               russian_translation,
               russian_latin,
               part_of_speech,
               pronunciation,
               example_chechen,
               example_chechen_latin,
               example_english,
               category
        FROM dictionary
        WHERE chechen_latin = ''
           OR russian_latin = ''
           OR chechen_latin_norm = ''
           OR russian_latin_norm = ''
           OR latin_ascii_norm = ''
        """
    ).fetchall()

    if not rows:
        return 0

    print(f"Backfilling Latin columns for {len(rows)} rows ...")
    updated = 0
    batch: list[tuple[str, ...]] = []
    now = utc_now()

    for row in rows:
        word = {
            "chechen_word": clean_text(row["chechen_word"]),
            "chechen_latin": clean_text(row["chechen_latin"]),
            "english_translation": clean_text(row["english_translation"]),
            "russian_translation": clean_text(row["russian_translation"]),
            "russian_latin": clean_text(row["russian_latin"]),
            "part_of_speech": clean_text(row["part_of_speech"]),
            "pronunciation": clean_text(row["pronunciation"]),
            "example_chechen": clean_text(row["example_chechen"]),
            "example_chechen_latin": clean_text(row["example_chechen_latin"]),
            "example_english": clean_text(row["example_english"]),
            "category": clean_text(row["category"]) or "imported",
        }

        word = clean_word(word)

        batch.append(
            (
                word["chechen_latin"],
                word["russian_latin"],
                word["example_chechen_latin"],
                norm_latin(word["chechen_latin"]),
                norm_latin(word["russian_latin"]),
                make_latin_ascii_norm(word),
                make_search_norm(word),
                now,
                str(row["id"]),
            )
        )

        if len(batch) >= 5000:
            conn.executemany(
                """
                UPDATE dictionary
                SET chechen_latin = ?,
                    russian_latin = ?,
                    example_chechen_latin = ?,
                    chechen_latin_norm = ?,
                    russian_latin_norm = ?,
                    latin_ascii_norm = ?,
                    search_norm = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                batch,
            )
            updated += len(batch)
            print(f"Backfilled {updated} rows ...")
            batch.clear()

    if batch:
        conn.executemany(
            """
            UPDATE dictionary
            SET chechen_latin = ?,
                russian_latin = ?,
                example_chechen_latin = ?,
                chechen_latin_norm = ?,
                russian_latin_norm = ?,
                latin_ascii_norm = ?,
                search_norm = ?,
                updated_at = ?
            WHERE id = ?
            """,
            batch,
        )
        updated += len(batch)

    return updated


def init_db() -> None:
    with connect_db() as conn:
        create_schema(conn)

        if database_has_words(conn):
            count = conn.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]
            print(f"Database already has {count} words")
            updated = backfill_latin_columns(conn)
            if updated:
                conn.commit()
                print(f"Latin support added to {updated} rows")
            return

        words_file = find_words_file()

        if not words_file:
            print("No words_latin.json, words.json, or words_translated.json found.")
            print("Put your JSON file next to app.py, then restart.")
            return

        words = load_words_from_json(words_file)
        inserted = insert_words_bulk(conn, words)
        conn.commit()
        print(f"Imported {inserted} words into {DATABASE.name}")


def parse_limit_offset(default_limit: int = 20, max_limit: int = 100) -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", default_limit))
    except ValueError:
        limit = default_limit

    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


# ============================================================
# Routes
# ============================================================

@app.route("/")
def home():
    return jsonify(
        {
            "message": "Chechen Dictionary API is running",
            "version": "2.0-noxciy-latin",
            "usage": {
                "stats": "/stats",
                "search_all_cyrillic": "/search?q=ламаз",
                "search_all_latin": "/search?q=lamaz",
                "search_chechen": "/search?q=ламаз&lang=chechen",
                "search_chechen_latin": "/search?q=lamaz&lang=chechen_latin",
                "search_russian": "/search?q=молитва&lang=russian",
                "search_russian_latin": "/search?q=molitva&lang=russian_latin",
                "search_english": "/search?q=prayer&lang=english",
                "random": "/random",
            },
            "supported_lang_values": sorted(VALID_LANGUAGES),
            "files": {
                "database": DATABASE.name,
                "accepted_word_files": [p.name for p in WORD_FILES],
            },
        }
    )


@app.route("/stats")
def stats():
    with connect_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]
        latin_count = conn.execute(
            "SELECT COUNT(*) FROM dictionary WHERE chechen_latin != ''"
        ).fetchone()[0]
        categories = conn.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM dictionary
            GROUP BY category
            ORDER BY count DESC
            LIMIT 30
            """
        ).fetchall()

    return jsonify(
        {
            "total_words": total,
            "words_with_chechen_latin": latin_count,
            "top_categories": {row["category"]: row["count"] for row in categories},
            "time": utc_now(),
        }
    )


@app.route("/search")
def search():
    query = clean_text(request.args.get("q", ""))
    language = norm(request.args.get("lang", "all")) or "all"
    limit, offset = parse_limit_offset(default_limit=20, max_limit=100)

    if not query:
        return jsonify({"error": "Missing query. Use /search?q=word"}), 400

    if language not in VALID_LANGUAGES:
        return jsonify({"error": "Invalid lang.", "valid": sorted(VALID_LANGUAGES)}), 400

    q = norm(query)
    q_latin = norm_latin(query)
    q_ascii = make_latin_ascii_fallback(query)

    like = f"%{q}%"
    latin_like = f"%{q_latin}%"
    ascii_like = f"%{q_ascii}%"

    prefix = f"{q}%"
    latin_prefix = f"{q_latin}%"
    ascii_prefix = f"{q_ascii}%"

    if language == "chechen":
        where = "chechen_norm LIKE ?"
        where_params = [like]
        order_sql = "CASE WHEN chechen_norm = ? THEN 0 WHEN chechen_norm LIKE ? THEN 1 ELSE 2 END"
        order_params = [q, prefix]

    elif language in {"chechen_latin", "latin"}:
        where = "(chechen_latin_norm LIKE ? OR latin_ascii_norm LIKE ?)"
        where_params = [latin_like, ascii_like]
        order_sql = """
            CASE
                WHEN chechen_latin_norm = ? THEN 0
                WHEN latin_ascii_norm = ? THEN 1
                WHEN chechen_latin_norm LIKE ? THEN 2
                WHEN latin_ascii_norm LIKE ? THEN 3
                ELSE 4
            END
        """
        order_params = [q_latin, q_ascii, latin_prefix, ascii_prefix]

    elif language == "english":
        where = "english_norm LIKE ?"
        where_params = [like]
        order_sql = "CASE WHEN english_norm = ? THEN 0 WHEN english_norm LIKE ? THEN 1 ELSE 2 END"
        order_params = [q, prefix]

    elif language == "russian":
        where = "russian_norm LIKE ?"
        where_params = [like]
        order_sql = "CASE WHEN russian_norm = ? THEN 0 WHEN russian_norm LIKE ? THEN 1 ELSE 2 END"
        order_params = [q, prefix]

    elif language == "russian_latin":
        where = "(russian_latin_norm LIKE ? OR latin_ascii_norm LIKE ?)"
        where_params = [latin_like, ascii_like]
        order_sql = """
            CASE
                WHEN russian_latin_norm = ? THEN 0
                WHEN latin_ascii_norm = ? THEN 1
                WHEN russian_latin_norm LIKE ? THEN 2
                WHEN latin_ascii_norm LIKE ? THEN 3
                ELSE 4
            END
        """
        order_params = [q_latin, q_ascii, latin_prefix, ascii_prefix]

    else:
        where = "(search_norm LIKE ? OR latin_ascii_norm LIKE ?)"
        where_params = [like, ascii_like]
        order_sql = """
            CASE
                WHEN chechen_norm = ? THEN 0
                WHEN chechen_latin_norm = ? THEN 1
                WHEN english_norm = ? THEN 2
                WHEN russian_norm = ? THEN 3
                WHEN russian_latin_norm = ? THEN 4
                WHEN latin_ascii_norm = ? THEN 5
                WHEN chechen_norm LIKE ? THEN 6
                WHEN chechen_latin_norm LIKE ? THEN 7
                WHEN english_norm LIKE ? THEN 8
                WHEN russian_norm LIKE ? THEN 9
                WHEN russian_latin_norm LIKE ? THEN 10
                WHEN latin_ascii_norm LIKE ? THEN 11
                ELSE 99
            END
        """
        order_params = [
            q,
            q_latin,
            q,
            q,
            q_latin,
            q_ascii,
            prefix,
            latin_prefix,
            prefix,
            prefix,
            latin_prefix,
            ascii_prefix,
        ]

    with connect_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM dictionary WHERE {where}",
            where_params,
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT *
            FROM dictionary
            WHERE {where}
            ORDER BY {order_sql}, chechen_word COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            where_params + order_params + [limit, offset],
        ).fetchall()

    results = [row_to_word(row) for row in rows]

    return jsonify(
        {
            "query": query,
            "language": language,
            "count": len(results),
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(results) < total,
            "results": results,
        }
    )


@app.route("/word/<int:word_id>")
def get_word(word_id: int):
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM dictionary WHERE id = ?", (word_id,)).fetchone()

    if not row:
        return jsonify({"error": "Word not found"}), 404

    return jsonify(row_to_word(row))


@app.route("/random")
def random_word():
    with connect_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]

        if total == 0:
            return jsonify({"error": "No words imported yet"}), 404

        offset = random.randrange(total)
        row = conn.execute(
            "SELECT * FROM dictionary ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()

    return jsonify(row_to_word(row))


@app.route("/reload", methods=["POST"])
def reload_words():
    words_file = find_words_file()
    if not words_file:
        return jsonify({"error": "No words_latin.json, words.json, or words_translated.json found"}), 400

    with connect_db() as conn:
        create_schema(conn)
        conn.execute("DELETE FROM dictionary")
        words = load_words_from_json(words_file)
        inserted = insert_words_bulk(conn, words)
        conn.commit()

    return jsonify({"message": "Reload complete", "inserted": inserted})


@app.route("/transliterate")
def transliterate_endpoint():
    text = clean_text(request.args.get("text", ""))
    if not text:
        return jsonify({"error": "Missing text. Use /transliterate?text=ламаз"}), 400

    latin = transliterate_noxciy(text)
    return jsonify(
        {
            "text": text,
            "latin": latin,
            "latin_ascii_fallback": make_latin_ascii_fallback(latin),
        }
    )


if __name__ == "__main__":
    init_db()
    print(f"API: http://localhost:{PORT}")
    print(f"Stats: http://localhost:{PORT}/stats")
    print(f"Search Cyrillic: http://localhost:{PORT}/search?q=ламаз")
    print(f"Search Latin: http://localhost:{PORT}/search?q=lamaz")
    app.run(debug=True, host="0.0.0.0", port=PORT)
