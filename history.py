"""
④予測データの保存・読み込み（SQLite）

一度取得した出走表・直前情報・オッズ・フォーメーションはレース単位でSQLiteに保存し、
同じレースを再度開いたときはサイトへ再アクセスせずDBから読み込む。
確定結果だけは未確定の間は毎回取りに行き、確定した時点でDBに書き込んで以後は再取得しない。

【重要・永続化の注意】
Streamlit Community Cloudなどのホスティング環境ではファイルシステムが一時的な場合があり、
アプリの再デプロイ・再起動でこのSQLiteファイルごと消える可能性がある。
稼働中は保存され続けるが、長期的な記録を厳密に残したい場合は
外部DB（Supabase/PostgreSQL、Google Sheets等）への切り替えを検討すること。
"""

from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent / "history.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            race_date TEXT NOT NULL,
            venue TEXT NOT NULL,
            race_no INTEGER NOT NULL,
            bet_type_choice TEXT,
            entries_json TEXT,
            before_json TEXT,
            odds_3t_json TEXT,
            odds_custom_json TEXT,
            odds_locked INTEGER DEFAULT 0,
            result_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (race_date, venue, race_no)
        )
    """)
    return conn


def save_prediction(
    race_date: date, venue: str, race_no: int, *,
    bet_type_choice: str, entries: list[dict], before_info: dict,
    odds_3t: dict, odds_custom: dict | None, result: dict | None = None,
    odds_locked: bool = False,
) -> None:
    """出走表〜オッズ一式をレース単位で保存（新規作成 or 上書き更新）する。"""
    now = datetime.now().isoformat()
    conn = _connect()
    with conn:
        conn.execute("""
            INSERT INTO predictions
                (race_date, venue, race_no, bet_type_choice, entries_json, before_json,
                 odds_3t_json, odds_custom_json, odds_locked, result_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(race_date, venue, race_no) DO UPDATE SET
                bet_type_choice=excluded.bet_type_choice,
                entries_json=excluded.entries_json,
                before_json=excluded.before_json,
                odds_3t_json=excluded.odds_3t_json,
                odds_custom_json=excluded.odds_custom_json,
                odds_locked=excluded.odds_locked,
                updated_at=excluded.updated_at
        """, (
            race_date.isoformat(), venue, race_no, bet_type_choice,
            json.dumps(entries, ensure_ascii=False),
            json.dumps(before_info, ensure_ascii=False),
            json.dumps(odds_3t, ensure_ascii=False),
            json.dumps(odds_custom, ensure_ascii=False) if odds_custom is not None else None,
            int(odds_locked),
            json.dumps(result, ensure_ascii=False) if result is not None else None,
            now, now,
        ))
    conn.close()


def load_prediction(race_date: date, venue: str, race_no: int) -> dict | None:
    """保存済みのレースデータを読み込む。無ければNone。"""
    conn = _connect()
    row = conn.execute(
        "SELECT entries_json, before_json, odds_3t_json, odds_custom_json, "
        "odds_locked, result_json, bet_type_choice FROM predictions "
        "WHERE race_date=? AND venue=? AND race_no=?",
        (race_date.isoformat(), venue, race_no),
    ).fetchone()
    conn.close()
    if row is None:
        return None

    (entries_json, before_json, odds_3t_json, odds_custom_json,
     odds_locked, result_json, bet_type_choice) = row
    return {
        "entries": json.loads(entries_json) if entries_json else [],
        "before_info": json.loads(before_json) if before_json else {},
        "odds_3t": json.loads(odds_3t_json) if odds_3t_json else {},
        "odds_custom": json.loads(odds_custom_json) if odds_custom_json else None,
        "odds_locked": bool(odds_locked),
        "result": json.loads(result_json) if result_json else None,
        "bet_type_choice": bet_type_choice,
    }


def update_odds(race_date: date, venue: str, race_no: int,
                 odds_3t: dict, odds_custom: dict | None, odds_locked: bool) -> None:
    """締切通過などでオッズが固定値になったタイミングで、オッズだけを更新・ロックする。"""
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE predictions SET odds_3t_json=?, odds_custom_json=?, odds_locked=?, updated_at=? "
            "WHERE race_date=? AND venue=? AND race_no=?",
            (json.dumps(odds_3t, ensure_ascii=False),
             json.dumps(odds_custom, ensure_ascii=False) if odds_custom is not None else None,
             int(odds_locked), datetime.now().isoformat(),
             race_date.isoformat(), venue, race_no),
        )
    conn.close()


def update_result(race_date: date, venue: str, race_no: int, result: dict) -> None:
    """確定結果だけを追記する（結果判明後、以後は再取得不要にするため）。"""
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE predictions SET result_json=?, updated_at=? "
            "WHERE race_date=? AND venue=? AND race_no=?",
            (json.dumps(result, ensure_ascii=False), datetime.now().isoformat(),
             race_date.isoformat(), venue, race_no),
        )
    conn.close()


def list_predictions(limit: int = 50) -> list[dict]:
    """保存済みレースの一覧（新しい順）を返す。"""
    conn = _connect()
    rows = conn.execute(
        "SELECT race_date, venue, race_no, result_json, updated_at FROM predictions "
        "ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {"race_date": r[0], "venue": r[1], "race_no": r[2],
         "result": json.loads(r[3]) if r[3] else None, "updated_at": r[4]}
        for r in rows
    ]
