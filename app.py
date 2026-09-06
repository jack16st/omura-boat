"""
ボートレースAI予測・資金配分アプリ（統合版）

streamlit run app.py で起動。
必要パッケージ: streamlit, pandas, beautifulsoup4, curl_cffi (無ければrequestsにフォールバック)

【重要】
- 実際のネットワークアクセスを伴うため、開発環境でのテストが未実施の状態です。
  boatrace.jpのページ構造は今回確認した内容に基づいていますが、変更されている可能性があるため、
  初回実行時にサイドバーの「データ取得」を押して、各タブが正しく表示されるか確認してください。
- スクレイピングが失敗した場合は自動的にモックデータへフォールバックし、
  画面上にエラー内容を表示します。
"""

import streamlit as st
import pandas as pd
from datetime import date

from constants import VENUES, RACE_NUMBERS, BET_TYPES, INPUT_MODES, LANE_MARKERS
import scraper
import scorer
import allocator
import settlement


# ------------------------------------------------------------
# モックデータ（スクレイピング失敗時のフォールバック）
# ------------------------------------------------------------

def _mock_entries() -> list[dict]:
    names = ["山田太郎", "佐藤次郎", "鈴木三郎", "高橋四郎", "田中五郎", "伊藤六郎"]
    return [{
        "枠": i + 1, "選手名": names[i], "登録番号": None, "級別": "A1",
        "全国勝率": [6.8, 5.9, 5.2, 4.8, 5.5, 4.1][i],
        "当地勝率": [7.1, 5.5, 4.9, 5.0, 5.8, 3.9][i],
        "モーター勝率": [42.0, 38.5, 35.0, 33.2, 40.1, 30.5][i],
        "平均ST": [0.14, 0.16, 0.15, 0.18, 0.17, 0.20][i],
    } for i in range(6)]


def _mock_before_info() -> dict:
    return {
        "entries": [{"枠": i + 1, "展示タイム": [6.72, 6.78, 6.81, 6.85, 6.75, 6.90][i]} for i in range(6)],
        "start_courses": {},
        "weather": {"気温": 20.0, "天候": "晴", "風速": 2.0, "水温": 18.0, "波高": 1.0},
    }


def _mock_odds(bet_type: str) -> dict:
    if bet_type == "3連単":
        return {"1-2-3": 3.5, "1-3-2": 5.2, "1-2-4": 8.1, "2-1-3": 12.4, "1-4-2": 15.0, "3-1-2": 22.3}
    return {"1-2": 2.1, "1-3": 3.0, "1-4": 4.5, "2-3": 6.0, "2-4": 7.2, "3-4": 9.0}


# ------------------------------------------------------------
# データ取得（実スクレイピング、失敗時はモックにフォールバック）
# ------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=30)
def load_race_data(d: date, venue: str, rno: int, bet_type: str):
    errors = []

    try:
        entries = scraper.fetch_race_card(d, venue, rno)
    except Exception as e:
        errors.append(f"出走表取得エラー: {e}")
        entries = _mock_entries()

    try:
        before = scraper.fetch_before_info(d, venue, rno)
    except Exception as e:
        errors.append(f"直前情報取得エラー: {e}")
        before = _mock_before_info()

    try:
        odds = scraper.fetch_odds(d, venue, rno, bet_type)
        if not odds:
            raise ValueError("オッズを1件も取得できませんでした")
    except Exception as e:
        errors.append(f"オッズ取得エラー: {e}")
        odds = _mock_odds(bet_type)

    try:
        result = scraper.fetch_race_result(d, venue, rno)
    except Exception as e:
        errors.append(f"確定結果取得エラー: {e}")
        result = None

    return entries, before, odds, result, errors


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------

st.set_page_config(page_title="ボートレースAI予測・資金配分", layout="wide")

st.sidebar.header("レース選択")
race_date = st.sidebar.date_input("開催日", value=date.today())
venue = st.sidebar.selectbox("競走場", VENUES, index=VENUES.index("芦屋") if "芦屋" in VENUES else 0)
race_no = st.sidebar.selectbox("レース番号", RACE_NUMBERS, format_func=lambda n: f"{n}R")

st.sidebar.header("券種・配分設定")
bet_type = st.sidebar.radio("券種", BET_TYPES)
input_mode = st.sidebar.radio("入力モード", INPUT_MODES)

if input_mode == "金額（予算）で指定":
    budget = st.sidebar.number_input("予算（円）", min_value=100, step=100, value=3000)
    points_per_combo = None
else:
    points_per_combo = st.sidebar.number_input("1点あたりの点数", min_value=1, step=1, value=1)
    budget = None

fetch_clicked = st.sidebar.button("🔄 データ取得・更新")

st.title(f"🚤 {venue} {race_no}R 予測・資金配分")

if "loaded" not in st.session_state:
    st.session_state["loaded"] = False

if fetch_clicked:
    st.session_state["loaded"] = True

if not st.session_state["loaded"]:
    st.info("サイドバーの「🔄 データ取得・更新」を押すとレースデータを取得します。")
    st.stop()

entries, before_info, odds, result, errors = load_race_data(race_date, venue, race_no, bet_type)

if errors:
    with st.expander("⚠️ データ取得時のエラー詳細（モックデータで代替表示中の項目があります）"):
        for e in errors:
            st.write("- " + e)

tenji_by_lane = {e["枠"]: e.get("展示タイム") for e in before_info.get("entries", []) if e.get("展示タイム")}
weather = before_info.get("weather", {})

tab_score, tab_alloc, tab_settle = st.tabs(["① 予測・スコア", "② 資金配分", "③ 収支確認"])

# --- タブ1: 予測・スコア ---
with tab_score:
    scored = scorer.score_entries(entries, weather=weather, tenji_by_lane=tenji_by_lane)

    if scored.empty:
        st.warning("出走表データを取得できませんでした。")
        formation = []
    else:
        display_df = scored.copy()
        display_df["枠"] = display_df["枠"].map(lambda n: f"{LANE_MARKERS.get(n, '')} {n}")
        cols = [c for c in ["枠", "選手名", "級別", "全国勝率", "当地勝率", "モーター勝率",
                             "展示タイム", "平均ST", "総合スコア"] if c in display_df.columns]

        st.subheader("スコアランキング")
        st.dataframe(display_df[cols], use_container_width=True, hide_index=True)

        weather_line = f"風速{weather.get('風速', 0)}m / 波高{weather.get('波高', 0)}cm / {weather.get('天候') or '-'}"
        st.caption(f"気象条件: {weather_line}")

        st.subheader("推奨フォーメーション")
        formation = scorer.recommend_formation(scored, bet_type)
        st.write(" / ".join(formation) if formation else "算出できませんでした")

# --- タブ2: 資金配分 ---
with tab_alloc:
    st.subheader("リアルタイムオッズ")
    odds_df = pd.DataFrame([{"買い目": k, "オッズ": v} for k, v in odds.items()])
    st.dataframe(odds_df, use_container_width=True, hide_index=True)

    st.subheader("資金配分結果")
    target_odds = {c: odds[c] for c in formation if c in odds} if formation else {}

    if not target_odds:
        st.info("推奨買い目のオッズが取得できませんでした。")
        alloc_result = {"allocation": {}, "synthetic_odds": 0.0, "torigami": True, "total_stake": 0}
    elif input_mode == "金額（予算）で指定":
        alloc_result = allocator.allocate_by_budget(target_odds, budget)
    else:
        alloc_result = allocator.allocate_by_points(target_odds, points_per_combo=points_per_combo)

    if alloc_result["allocation"]:
        alloc_df = pd.DataFrame([
            {"買い目": k, "オッズ": target_odds[k], "配分金額": v,
             "的中時払戻": alloc_result.get("payout_if_hit", {}).get(k)}
            for k, v in alloc_result["allocation"].items()
        ])
        st.dataframe(alloc_df, use_container_width=True, hide_index=True)

        st.metric("合計投資額", f"{alloc_result['total_stake']}円")
        if alloc_result["torigami"]:
            st.error(f"⚠️ 合成オッズ {alloc_result['synthetic_odds']} 倍 — トリガミの可能性があります")
        else:
            st.success(f"合成オッズ: {alloc_result['synthetic_odds']} 倍")

# --- タブ3: 収支確認 ---
with tab_settle:
    settled = settlement.settle(bet_type, alloc_result.get("allocation", {}), result)

    if settled is None:
        st.info("このレースはまだ確定結果が出ていないか、結果を取得できませんでした。")
    else:
        if settled["的中"]:
            st.success(f"🎯 的中！ 払戻金合計: {settled['払戻金合計']}円 / 利益: {settled['利益額']}円 / 回収率: {settled['回収率']}%")
            st.dataframe(pd.DataFrame(settled["的中詳細"]), use_container_width=True, hide_index=True)
        else:
            st.error(f"✗ ハズレ 投資額: {settled['投資額']}円 / 回収率: {settled['回収率']}%")
