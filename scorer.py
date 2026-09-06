"""
②AIスコアリング・予測ロジック

評価ファクター:
  - 枠番ごとのコース基礎信頼度
  - 選手の地力(全国勝率)とモーター勝率の相乗効果(シナジーボーナス)
  - 展示タイム・平均STの評価
  - 気象条件(風速・波高)によるイン/アウト信頼度の動的補正
"""

from __future__ import annotations
import pandas as pd

from constants import COURSE_BASE_WIN_RATE


def score_entries(
    entries: list[dict],
    weather: dict | None = None,
    tenji_by_lane: dict[int, float] | None = None,
) -> pd.DataFrame:
    """出走表データ（＋任意で直前情報・気象）から総合スコアを算出する。"""
    df = pd.DataFrame(entries)
    if df.empty:
        return df

    df["全国勝率"] = df["全国勝率"].fillna(df["全国勝率"].mean())
    df["モーター勝率"] = df["モーター勝率"].fillna(df["モーター勝率"].mean())

    # ① コース基礎信頼度
    df["コース基礎点"] = df["枠"].map(COURSE_BASE_WIN_RATE)

    # ② 地力×機力のシナジーボーナス（単純な平均より相乗効果を重視するため掛け算＋対数緩和）
    df["シナジー"] = (df["全国勝率"] * df["モーター勝率"]) / 100.0

    # ③ 展示タイム・ST評価（直前情報がある場合のみ加点、平均より速いほど加点）
