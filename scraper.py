"""
①スクレイピングモジュール

boatrace.jp の公式ページから出走表・直前情報・オッズ・確定結果を取得する。

【重要な注意】
- 本モジュールはページの列構成（実際に確認した表示順）に基づいて位置ベースで値を取り出す設計。
  クラス名の変更には強いが、列の並び順が変わった場合は影響を受けるため、
  リリース前に必ず実際のレスポンスで動作確認すること。
- 2連単・2連複/ 拡連複 / 単勝・複勝 のオッズページは構造を実機で未確認のため、
  テキストベースの緩めのパターンマッチで実装している（要検証・要調整の暫定実装）。
- アクセス過多はサイト規約・負荷の観点から避けること。呼び出し側でリクエスト間隔を
  空ける（例: 1リクエストあたり1〜2秒のsleep）運用を強く推奨する。
"""

from __future__ import annotations
import re
import time
from datetime import date

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    import requests as curl_requests  # フォールバック（ブロック回避なし）
    _HAS_CURL_CFFI = False

from datetime import datetime
from constants import BASE_URL, ODDS_PATH, VENUE_TO_JCD, JCD_TO_VENUE
from parsing_utils import table_to_grid, extract_numbers, first_number

MIN_REQUEST_INTERVAL_SEC = 1.5
_last_request_time = 0.0
