"""
ボートレースAI予測・資金配分アプリ（統合版 v2）

streamlit run app.py で起動。
必要パッケージ: streamlit, pandas, beautifulsoup4, curl_cffi (requirements.txt参照)

主な構成:
  トップ: 本日の締切間近レース Top5
  ①予測・スコア: おすすめフォーメーション(必須) → カスタムフォーメーション(券種指定時) →
                 スコアランキング(簡易) → 展開予測 → 全舟診断
  ②詳細データ: 出走表詳細 → 気象情報 → リアルタイムオッズ(3連単・全件)
  ③資金配分・結果: 結果(判明時に先頭表示) → おすすめ資金配分(必須) → カスタム資金配分(券種指定時)
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime

from constants import VENUES, RACE_NUMBERS, BET_TYPES, LANE_MARKERS
import scraper
import scorer
import allocator
import settlement

RECOMMEND_BET_TYPE = "3連単"
BET_TYPE_OPTIONS = ["おすすめ"] + BET_TYPES
RECOMMEND_BUDGET = 1000


# ------------------------------------------------------------
# モックデータ（スクレイピング失敗時のフォールバック）
# ------------------------------------------------------------

def _mock_entries() -> list[dict]:
    names = ["山田太郎", "佐藤次郎", "鈴木三郎", "高橋四郎", "田中五郎", "伊藤六郎"]
    return [{
        "枠": i + 1, "選手名": names[i], "登録番号": None, "級別": "A1",
