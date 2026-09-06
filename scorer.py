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
    if tenji_by_lane:
        df["展示タイム"] = df["枠"].map(tenji_by_lane)
        valid = df["展示タイム"].dropna()
        if len(valid) >= 2:
            mean_tenji = valid.mean()
            df["展示評価"] = (mean_tenji - df["展示タイム"].fillna(mean_tenji)) * 20
        else:
            df["展示評価"] = 0.0
    else:
        df["展示評価"] = 0.0

    if "平均ST" in df.columns and df["平均ST"].notna().any():
        mean_st = df["平均ST"].dropna().mean()
        df["ST評価"] = (mean_st - df["平均ST"].fillna(mean_st)) * 50
    else:
        df["ST評価"] = 0.0

    # ④ 気象補正: 風速・波高が高いほど「荒れ」やすくイン(1-2号艇)の信頼度が下がり、
    #    アウト(5-6号艇)が浮上しやすくなる傾向を反映
    wind = (weather or {}).get("風速") or 0.0
    wave = (weather or {}).get("波高") or 0.0
    rough_index = wind + wave * 2.0

    def weather_adjust(lane: int) -> float:
        if lane <= 2:
            return -rough_index * 1.5
        if lane >= 5:
            return rough_index * 1.0
        return -rough_index * 0.2  # 3-4号艇はやや中立寄りにわずかにマイナス

    df["気象補正"] = df["枠"].map(weather_adjust)

    df["総合スコア"] = (
        df["コース基礎点"] * 0.6
        + df["シナジー"] * 3.0
        + df["展示評価"]
        + df["ST評価"]
        + df["気象補正"]
    ).round(1)

    return df.sort_values("総合スコア", ascending=False).reset_index(drop=True)


def recommend_formation(scored: pd.DataFrame, bet_type: str, top_n: int = 6) -> list[str]:
    """スコア順位から券種別の推奨買い目を選定する（上位艇を中心に絞り込む）。"""
    if scored.empty:
        return []
    lanes = scored["枠"].tolist()
    formations: list[str] = []
    seen = set()

    def add(key: str):
        if key not in seen:
            seen.add(key)
            formations.append(key)

    if bet_type in ("3連単", "3連複"):
        sep = "-" if bet_type == "3連単" else "="
        axis = lanes[0]
        partners = lanes[1:4]
        thirds = lanes[1:5]
        for s in partners:
            for t in thirds:
                if len({axis, s, t}) < 3:
                    continue
                combo = (axis, s, t) if bet_type == "3連単" else tuple(sorted([axis, s, t]))
                add(sep.join(map(str, combo)))
                if len(formations) >= top_n:
                    return formations

    elif bet_type in ("2連単", "2連複"):
        sep = "-" if bet_type == "2連単" else "="
        axis = lanes[0]
        for s in lanes[1:]:
            combo = (axis, s) if bet_type == "2連単" else tuple(sorted([axis, s]))
            add(sep.join(map(str, combo)))
            if len(formations) >= top_n:
                break

    elif bet_type == "拡連複":
        axis = lanes[0]
        for s in lanes[1:]:
            add("=".join(map(str, sorted([axis, s]))))
            if len(formations) >= top_n:
                break

    elif bet_type == "単勝":
        formations = [str(lanes[0])]

    elif bet_type == "複勝":
        formations = [str(x) for x in lanes[:2]]

    return formations
