"""
日本時間(JST)固定の日時ユーティリティ。

Streamlit Cloud等のホスティング環境はサーバーがUTCで動いていることが多く、
date.today() / datetime.now() をそのまま使うと、日本時間の深夜〜早朝
（UTC換算ではまだ前日）にサーバー側の日付が1日ずれる問題が起きる。
ボートレースの開催日・締切時刻はすべて日本時間基準のため、常にJSTで統一する。
"""

from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    """現在時刻をJSTのnaive datetime（tzinfoなし）で返す。"""
    return datetime.now(JST).replace(tzinfo=None)


def today_jst() -> date:
    """今日の日付をJST基準で返す。"""
    return now_jst().date()
