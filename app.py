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
import history
from timeutils import now_jst, today_jst

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
        "締切予定": None,
    }


def _mock_odds(bet_type: str) -> dict:
    if bet_type == "3連単":
        return {"1-2-3": 3.5, "1-3-2": 5.2, "1-2-4": 8.1, "2-1-3": 12.4, "1-4-2": 15.0, "3-1-2": 22.3}
    return {"1-2": 2.1, "1-3": 3.0, "1-4": 4.5, "2-3": 6.0, "2-4": 7.2, "3-4": 9.0}


def _mock_deadlines(today: date) -> list[dict]:
    return [
        {"開催日": today, "競走場": "芦屋", "R": 7, "締切時刻": datetime(today.year, today.month, today.day, 18, 20)},
        {"開催日": today, "競走場": "丸亀", "R": 6, "締切時刻": datetime(today.year, today.month, today.day, 18, 25)},
        {"開催日": today, "競走場": "大村", "R": 8, "締切時刻": datetime(today.year, today.month, today.day, 18, 32)},
        {"開催日": today, "競走場": "若松", "R": 5, "締切時刻": datetime(today.year, today.month, today.day, 18, 40)},
        {"開催日": today, "競走場": "福岡", "R": 9, "締切時刻": datetime(today.year, today.month, today.day, 18, 48)},
    ]


# ------------------------------------------------------------
# データ取得（実スクレイピング、失敗時はモックにフォールバック）
# ------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=60)
def load_top5(today: date):
    try:
        rows = scraper.fetch_upcoming_deadlines(today, now_jst())
        if not rows:
            raise ValueError("本日の締切前レースが見つかりませんでした")
        return rows, None
    except Exception as e:
        return _mock_deadlines(today), str(e)


@st.cache_data(show_spinner=False, ttl=30)
def _fetch_odds_live(d: date, venue: str, rno: int, bet_type: str, fallback: dict | None):
    try:
        odds = scraper.fetch_odds(d, venue, rno, bet_type)
        if not odds:
            raise ValueError(f"{bet_type}オッズを1件も取得できませんでした")
        return odds, None
    except Exception as e:
        return (fallback or _mock_odds(bet_type)), f"{bet_type}オッズ取得エラー: {e}"


def get_race_data(d: date, venue: str, rno: int, extra_bet_type: str | None, force_refresh: bool):
    """出走表・直前情報は保存済みなら再利用。オッズは締切前は毎回最新を取得し、
    締切通過後または結果確定後は固定値として以後は再取得しない。
    スクレイピングに失敗してモックデータで代替した場合はDBに保存しない（次回また本物を取りに行く）。"""
    errors: list[str] = []
    cached = None if force_refresh else history.load_prediction(d, venue, rno)
    from_cache = cached is not None

    entries_is_real = True
    before_is_real = True

    if cached:
        entries = cached["entries"]
        before_info = cached["before_info"]
    else:
        try:
            entries = scraper.fetch_race_card(d, venue, rno)
        except Exception as e:
            errors.append(f"出走表取得エラー: {e}")
            entries = _mock_entries()
            entries_is_real = False
        try:
            before_info = scraper.fetch_before_info(d, venue, rno)
        except Exception as e:
            errors.append(f"直前情報取得エラー: {e}")
            before_info = _mock_before_info()
            before_is_real = False

    # 締切判定（このレース固有の締切予定時刻と現在時刻を比較）
    deadline_dt = None
    deadline_str = before_info.get("締切予定") if isinstance(before_info, dict) else None
    if deadline_str:
        try:
            deadline_dt = datetime.fromisoformat(deadline_str)
        except ValueError:
            deadline_dt = None
    deadline_passed = bool(deadline_dt and now_jst() >= deadline_dt)

    # 確定結果（保存済みならそれ以上は再取得しない）
    if cached and cached.get("result"):
        result = cached["result"]
    else:
        try:
            result = scraper.fetch_race_result(d, venue, rno)
        except Exception as e:
            errors.append(f"確定結果取得エラー: {e}")
            result = None
    settled = result is not None

    # オッズ: 確定済み、または締切通過後にロック済みキャッシュがあれば再取得しない
    odds_locked_cached = bool(cached and cached.get("odds_locked"))
    odds_3t_is_real = True
    if (settled or odds_locked_cached) and cached and cached.get("odds_3t"):
        odds_3t = cached["odds_3t"]
    else:
        odds_3t, err = _fetch_odds_live(d, venue, rno, RECOMMEND_BET_TYPE, cached.get("odds_3t") if cached else None)
        if err:
            errors.append(err)
            odds_3t_is_real = False

    odds_custom = None
    odds_custom_is_real = True
    if extra_bet_type and extra_bet_type != RECOMMEND_BET_TYPE:
        cached_custom = cached.get("odds_custom") if (cached and cached.get("bet_type_choice") == extra_bet_type) else None
        if (settled or odds_locked_cached) and cached_custom:
            odds_custom = cached_custom
        else:
            odds_custom, err = _fetch_odds_live(d, venue, rno, extra_bet_type, cached_custom)
            if err:
                errors.append(err)
                odds_custom_is_real = False

    should_lock_now = (settled or deadline_passed) and not odds_locked_cached

    if not cached:
        # 出走表・直前情報が両方とも本物のスクレイピング結果のときだけ保存する。
        # モックで代替した場合は保存せず、次回アクセス時に再度スクレイピングを試みる。
        if entries_is_real and before_is_real:
            history.save_prediction(
                d, venue, rno,
                bet_type_choice=extra_bet_type or RECOMMEND_BET_TYPE,
                entries=entries, before_info=before_info,
                odds_3t=odds_3t if odds_3t_is_real else {},
                odds_custom=(odds_custom if odds_custom_is_real else None),
                result=result,
                odds_locked=bool((settled or deadline_passed) and odds_3t_is_real),
            )
    else:
        if result and not cached.get("result"):
            history.update_result(d, venue, rno, result)
        if should_lock_now and odds_3t_is_real and odds_custom_is_real:
            history.update_odds(d, venue, rno, odds_3t, odds_custom, True)

    return entries, before_info, odds_3t, odds_custom, result, errors, from_cache, deadline_passed


# ------------------------------------------------------------
# UI: 共通設定
# ------------------------------------------------------------

st.set_page_config(page_title="おむらんAI予想", layout="wide")
today = today_jst()

st.markdown("""
<style>
    .omuran-title {
        font-size: clamp(1.4rem, 5vw, 2.2rem);
        font-weight: 800;
        color: #12263f;
        letter-spacing: 0.03em;
        margin-bottom: 0.1rem;
        line-height: 1.3;
    }
    .omuran-subtitle {
        color: #4a6fa1;
        font-size: 0.85rem;
        margin-top: 0;
        margin-bottom: 1rem;
    }
    h2, h3 {
        color: #16324f !important;
        font-size: clamp(1.1rem, 4.2vw, 1.7rem) !important;
        font-weight: 700 !important;
        border-left: none !important;
        padding-left: 0 !important;
    }
    [data-testid="stMetricValue"] { color: #16324f; }
    section[data-testid="stSidebar"] {
        background-color: #eef2f7;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="omuran-title">🌸 おむらんAI予想 🌸</div>', unsafe_allow_html=True)
st.markdown('<div class="omuran-subtitle">ボートレースAI予測・資金配分</div>', unsafe_allow_html=True)

# --- サイドバー: HOME・レース選択 ---
if st.sidebar.button("🏠 HOME"):
    st.session_state["loaded"] = False

st.sidebar.header("レース選択")
race_date = st.sidebar.date_input("開催日", value=today)
venue = st.sidebar.selectbox("競走場", VENUES, index=VENUES.index("芦屋") if "芦屋" in VENUES else 0)
race_no = st.sidebar.selectbox("レース番号", RACE_NUMBERS, format_func=lambda n: f"{n}R")

st.sidebar.header("券種")
bet_type_choice = st.sidebar.selectbox("券種", BET_TYPE_OPTIONS, index=0)
is_custom_bet = bet_type_choice != "おすすめ"

st.sidebar.header("予算")
budget_choice = st.sidebar.radio("予算設定", [f"おすすめ（{RECOMMEND_BUDGET}円）", "カスタム"], index=0)
if budget_choice == "カスタム":
    budget = st.sidebar.number_input("予算（円）", min_value=100, step=100, value=3000)
else:
    budget = RECOMMEND_BUDGET

fetch_clicked = st.sidebar.button("🔄 データ取得・更新")
force_refresh = st.sidebar.checkbox("出走表・直前情報も強制的に再取得する", value=False)

if "loaded" not in st.session_state:
    st.session_state["loaded"] = False
if fetch_clicked:
    st.session_state["loaded"] = True

# --- HOME画面: 直近締切レース（予測データ未取得のときだけ表示） ---
if not st.session_state["loaded"]:
    st.subheader("直近締切レース")
    st.caption(f"対象日: {today.strftime('%Y-%m-%d')}")

    top5, top5_error = load_top5(today)
    if top5_error:
        st.caption(f"⚠️ 締切情報の取得に失敗したためサンプル表示中: {top5_error}")

    top5_df = pd.DataFrame([{
        "競走場": r["競走場"],
        "R": f"{r['R']}R",
        "締切時刻": r["締切時刻"].strftime("%H:%M"),
    } for r in top5])
    st.dataframe(top5_df[["競走場", "R", "締切時刻"]], use_container_width=True, hide_index=True)

    st.info("サイドバーの「🔄 データ取得・更新」を押すとレースデータを取得します。")
    st.stop()

st.header(f"{venue} {race_no}R 予測・資金配分")

extra_bet_type = bet_type_choice if is_custom_bet else None
entries, before_info, odds_3t, odds_custom, result, errors, from_cache, deadline_passed = get_race_data(
    race_date, venue, race_no, extra_bet_type, force_refresh
)

status_bits = []
if from_cache:
    status_bits.append("📦 出走表・直前情報は保存済みデータを使用中")
if result is not None:
    status_bits.append("✅ 結果確定済み（オッズは再取得しません）")
elif deadline_passed:
    status_bits.append("⏰ 締切通過（オッズは固定値としてキャッシュしました）")
if status_bits:
    st.caption(" ／ ".join(status_bits))

if errors:
    with st.expander("⚠️ データ取得時のエラー詳細（モックデータで代替表示中の項目があります）"):
        for e in errors:
            st.write("- " + e)

tenji_by_lane = {e["枠"]: e.get("展示タイム") for e in before_info.get("entries", []) if e.get("展示タイム")}
weather = before_info.get("weather", {})

scored = scorer.score_entries(entries, weather=weather, tenji_by_lane=tenji_by_lane)
recommend_formation = scorer.recommend_formation(scored, RECOMMEND_BET_TYPE) if not scored.empty else []
custom_formation = (
    scorer.recommend_formation(scored, bet_type_choice) if (is_custom_bet and not scored.empty) else []
)

tab_score, tab_detail, tab_money = st.tabs(["① 予測・スコア", "② 詳細データ", "③ 資金配分・結果"])

# ------------------------------------------------------------
# タブ1: 予測・スコア
# ------------------------------------------------------------
with tab_score:
    if scored.empty:
        st.warning("出走表データを取得できませんでした。")
    else:
        st.subheader("🎯 おすすめフォーメーション（3連単）")
        st.write(scorer.format_formation(recommend_formation, RECOMMEND_BET_TYPE) or "算出できませんでした")

        if is_custom_bet:
            st.subheader(f"🔧 カスタムフォーメーション（{bet_type_choice}）")
            st.write(scorer.format_formation(custom_formation, bet_type_choice) or "算出できませんでした")

        st.subheader("スコアランキング")
        display_df = scored.copy()
        display_df["枠"] = display_df["枠"].map(lambda n: f"{LANE_MARKERS.get(n, '')} {n}")
        st.dataframe(display_df[["枠", "選手名", "総合スコア"]], use_container_width=True, hide_index=True)

        st.subheader("展開予測")
        st.write(scorer.generate_race_comment(scored, weather))

        st.subheader("全舟診断")
        diag = scorer.generate_lane_diagnosis(scored)
        diag_df = pd.DataFrame(diag)
        if diag_df.empty:
            st.info("診断データを生成できませんでした。")
        else:
            diag_df["枠"] = diag_df["枠"].map(lambda n: f"{LANE_MARKERS.get(n, '')} {n}")
            st.dataframe(diag_df[["枠", "選手名", "総合スコア", "診断"]], use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# タブ2: 詳細データ
# ------------------------------------------------------------
with tab_detail:
    st.subheader("出走表詳細")
    detail_df = pd.DataFrame(entries)
    if detail_df.empty:
        st.warning("出走表データを取得できませんでした。")
    else:
        show_df = detail_df[["枠", "選手名", "級別", "全国勝率", "当地勝率", "モーター勝率", "平均ST"]].copy()
        show_df["枠"] = show_df["枠"].map(lambda n: f"{LANE_MARKERS.get(n, '')} {n}")
        st.dataframe(show_df, use_container_width=True, hide_index=True)

    st.subheader("気象情報")
    weather_df = pd.DataFrame([weather])
    st.dataframe(weather_df[["気温", "天候", "風速", "水温", "波高"]], use_container_width=True, hide_index=True)

    st.subheader("リアルタイムオッズ（3連単・全件）")
    odds_df = pd.DataFrame([{"買い目": k, "オッズ": v} for k, v in odds_3t.items()]).sort_values("買い目")
    st.dataframe(odds_df[["買い目", "オッズ"]], use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# タブ3: 資金配分・結果
# ------------------------------------------------------------
with tab_money:
    official_combo = None
    payout_amount = None
    recovery_rate = None
    hit = None

    if result is not None:
        result_entries = result.get("payouts", {}).get(RECOMMEND_BET_TYPE, [])
        if result_entries:
            official_combo = result_entries[0]["組番"]
            settled = settlement.settle(
                RECOMMEND_BET_TYPE,
                {c: 100 for c in recommend_formation} if recommend_formation else {},
                result,
            )
            if settled:
                hit = settled["的中"]
                recovery_rate = settled["回収率"]
                payout_amount = settled["払戻金合計"] if hit else None

    if official_combo:
        if hit:
            st.success(
                f"🎯 当たり　{RECOMMEND_BET_TYPE}:{official_combo} ／ "
                f"金額:{payout_amount:,}円 ／ 回収率:{recovery_rate}%"
            )
        else:
            st.error(
                f"❌ ハズレ　{RECOMMEND_BET_TYPE}:{official_combo} ／ "
                f"金額:− ／ 回収率:{recovery_rate if recovery_rate is not None else 0.0}%"
            )
    else:
        st.info("このレースはまだ確定結果が出ていないか、結果を取得できませんでした。")

    st.divider()
    st.subheader("🎯 おすすめ資金配分（3連単）")
    target_odds = {c: odds_3t[c] for c in recommend_formation if c in odds_3t} if recommend_formation else {}
    if not target_odds:
        st.info("推奨買い目のオッズが取得できませんでした。")
    else:
        alloc = allocator.allocate_by_budget(target_odds, budget)
        alloc_df = pd.DataFrame([
            {"買い目": k, "オッズ": target_odds[k], "配分金額": v,
             "的中時払戻": alloc.get("payout_if_hit", {}).get(k)}
            for k, v in alloc["allocation"].items()
        ])
        st.dataframe(alloc_df, use_container_width=True, hide_index=True)
        if alloc["torigami"]:
            st.error(f"⚠️ 合成オッズ {alloc['synthetic_odds']} 倍 — トリガミの可能性があります")
        else:
            st.success(f"合成オッズ: {alloc['synthetic_odds']} 倍")

    if is_custom_bet:
        st.divider()
        st.subheader(f"🔧 カスタム資金配分（{bet_type_choice}）")
        custom_odds = odds_custom or {}
        target_custom_odds = (
            {c: custom_odds[c] for c in custom_formation if c in custom_odds} if custom_formation else {}
        )
        if not target_custom_odds:
            st.info("カスタム買い目のオッズが取得できませんでした。")
        else:
            alloc_c = allocator.allocate_by_budget(target_custom_odds, budget)
            alloc_c_df = pd.DataFrame([
                {"買い目": k, "オッズ": target_custom_odds[k], "配分金額": v,
                 "的中時払戻": alloc_c.get("payout_if_hit", {}).get(k)}
                for k, v in alloc_c["allocation"].items()
            ])
            st.dataframe(alloc_c_df, use_container_width=True, hide_index=True)
            if alloc_c["torigami"]:
                st.error(f"⚠️ 合成オッズ {alloc_c['synthetic_odds']} 倍 — トリガミの可能性があります")
            else:
                st.success(f"合成オッズ: {alloc_c['synthetic_odds']} 倍")
