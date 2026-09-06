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


def generate_lane_diagnosis(scored: pd.DataFrame) -> list[dict]:
    """全舟診断: 艇ごとの簡易診断コメントを生成する（ルールベース）。"""
    if scored.empty:
        return []

    synergy_med = scored["シナジー"].median() if "シナジー" in scored.columns else 0
    diagnoses = []
    for _, row in scored.iterrows():
        lane = int(row["枠"])
        parts = []

        if lane == 1:
            parts.append("イン逃げが軸になりやすいコース" if row["総合スコア"] == scored["総合スコア"].max()
                          else "インだが信頼度はやや低め")
        elif lane in (2, 3):
            parts.append("差し・まくり差しでの浮上に注目")
        else:
            parts.append("まくり一発が決まれば台頭の目")

        if row.get("シナジー", 0) >= synergy_med:
            parts.append("地力・機力ともに水準以上")
        else:
            parts.append("機力面はやや見劣り")

        if row.get("展示評価", 0) > 1:
            parts.append("展示タイムは好調")
        elif row.get("展示評価", 0) < -1:
            parts.append("展示タイムはやや不安")

        if row.get("ST評価", 0) > 1:
            parts.append("スタートは安定傾向")
        elif row.get("ST評価", 0) < -1:
            parts.append("スタートに不安あり")

        weather_adj = row.get("気象補正", 0)
        if weather_adj <= -1:
            parts.append("荒天でやや割引材料")
        elif weather_adj >= 1:
            parts.append("荒天でチャンス拡大")

        diagnoses.append({
            "枠": lane,
            "選手名": row.get("選手名"),
            "総合スコア": row["総合スコア"],
            "診断": "、".join(parts) + "。",
        })
    return diagnoses


def generate_race_comment(scored: pd.DataFrame, weather: dict | None = None) -> str:
    """展開予測: レース全体の簡易展開コメントを生成する（ルールベース）。"""
    if scored.empty:
        return "出走表データが不足しているため展開予測を生成できませんでした。"

    top = scored.iloc[0]
    second = scored.iloc[1] if len(scored) > 1 else None
    wind = (weather or {}).get("風速") or 0
    wave = (weather or {}).get("波高") or 0

    lines = []
    top_name = top.get("選手名") or ""
    if top["枠"] == 1:
        lines.append(f"{top['枠']}号艇{top_name}のイン逃げが中心の展開。")
    else:
        lines.append(f"{top['枠']}号艇{top_name}が中心も、イン以外からの決着に警戒したい一戦。")

    if wind >= 5 or wave >= 5:
        lines.append(f"風速{wind}m・波高{wave}cmとやや荒れ模様で、アウトコース勢にもチャンスがある水面状況。")
    else:
        lines.append("水面は比較的穏やかで、地力通りの決着になりやすい条件。")

    if second is not None:
        second_name = second.get("選手名") or ""
        lines.append(f"対抗は{second['枠']}号艇{second_name}で、軸・相手の中心に据えたい。")

    return "".join(lines)
