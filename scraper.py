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
import unicodedata
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


def _throttle():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL_SEC:
        time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
    _last_request_time = time.time()


def _fetch_html(path: str, params: dict) -> str:
    """boatrace.jp から生HTMLを取得する。curl_cffiがあればChrome偽装で取得。"""
    _throttle()
    url = f"{BASE_URL}/{path}"
    if _HAS_CURL_CFFI:
        resp = curl_requests.get(url, params=params, impersonate="chrome110", timeout=15)
    else:
        resp = curl_requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _date_str(d: date) -> str:
    return d.strftime("%Y%m%d")


def _dedupe_lane_rows(rows: list[list[str]]) -> list[list[str]]:
    """rowspanの展開により枠番ごとに複数の物理行へ複製された内容を、枠番ごとに1行へ間引く。"""
    seen = set()
    deduped = []
    for r in rows:
        lane = r[0].strip()
        if lane in seen:
            continue
        seen.add(lane)
        deduped.append(r)
    return deduped


def _norm(text: str) -> str:
    """全角数字・全角スペース等を半角に正規化する。"""
    return unicodedata.normalize("NFKC", text)


def _diagnostic_info(soup: BeautifulSoup, html: str) -> str:
    """パース失敗時に原因の当たりをつけやすくするための簡易診断情報。"""
    table_count = len(soup.find_all("table"))
    snippet = soup.get_text(" ", strip=True)[:150]
    return f"(HTML長:{len(html)} / table数:{table_count} / 冒頭テキスト:「{snippet}」)"


def _find_main_table(soup: BeautifulSoup, min_cols: int = 6):
    """本文中のテーブルのうち、先頭列が枠番(1〜6)で始まる行を複数含むテーブルを探す。"""
    candidates = soup.find_all("table")
    for table in candidates:
        grid = table_to_grid(table)
        raw_lane_rows = [r for r in grid if r and r[0].strip() in {"1", "2", "3", "4", "5", "6"}]
        lane_rows = _dedupe_lane_rows(raw_lane_rows)
        if len(lane_rows) >= 4 and all(len(r) >= min_cols for r in lane_rows):
            return table, grid, lane_rows
    return None, None, None


# ------------------------------------------------------------
# 出走表
# ------------------------------------------------------------

def fetch_race_card(d: date, venue: str, rno: int) -> list[dict]:
    """出走表（選手・全国/当地勝率・モーター/ボート成績）を取得する。"""
    jcd = VENUE_TO_JCD[venue]
    html = _fetch_html("racelist", {"rno": rno, "jcd": jcd, "hd": _date_str(d)})
    soup = BeautifulSoup(html, "html.parser")
    _, _, lane_rows = _find_main_table(soup, min_cols=8)
    if not lane_rows:
        raise ValueError(f"出走表テーブルが見つかりませんでした（サイト構造が変わった可能性）{_diagnostic_info(soup, html)}")

    entries = []
    for row in lane_rows:
        try:
            lane = int(row[0])
            profile_text = row[2]
            toban_m = re.search(r"\d{4}", profile_text)
            class_m = re.search(r"(A1|A2|B1|B2)", profile_text)
            age_m = re.search(r"(\d+)歳", profile_text)
            weight_m = re.search(r"([\d.]+)kg", profile_text)
            name_m = re.search(r"[ぁ-んァ-ヶ一-龠]{1,4}\s*[ぁ-んァ-ヶ一-龠]{1,4}", profile_text)

            fl_st = extract_numbers(row[3])
            zenkoku = extract_numbers(row[4])
            touchi = extract_numbers(row[5])
            motor = extract_numbers(row[6])
            boat = extract_numbers(row[7])

            entries.append({
                "枠": lane,
                "登録番号": toban_m.group(0) if toban_m else None,
                "級別": class_m.group(0) if class_m else None,
                "選手名": name_m.group(0).replace(" ", "") if name_m else profile_text[:8],
                "年齢": int(age_m.group(1)) if age_m else None,
                "体重": float(weight_m.group(1)) if weight_m else None,
                "平均ST": fl_st[2] if len(fl_st) >= 3 else None,
                "全国勝率": zenkoku[0] if zenkoku else None,
                "当地勝率": touchi[0] if touchi else None,
                "モーター勝率": motor[1] if len(motor) >= 2 else None,  # 2連率を目安指標に使用
                "ボート2連率": boat[1] if len(boat) >= 2 else None,
            })
        except Exception:
            continue  # 1行のパース失敗は無視し、他の行は継続処理する

    if not entries:
        raise ValueError("出走表の行を1件もパースできませんでした")
    return entries


# ------------------------------------------------------------
# 直前情報
# ------------------------------------------------------------

def fetch_before_info(d: date, venue: str, rno: int) -> dict:
    """直前情報（展示タイム・チルト・体重・気象・スタート展示）を取得する。"""
    jcd = VENUE_TO_JCD[venue]
    html = _fetch_html("beforeinfo", {"rno": rno, "jcd": jcd, "hd": _date_str(d)})
    soup = BeautifulSoup(html, "html.parser")
    page_text = _norm(soup.get_text(" ", strip=True))

    _, _, lane_rows = _find_main_table(soup, min_cols=5)
    entries = []
    if lane_rows:
        for row in lane_rows:
            try:
                lane = int(row[0])
                weight_m = re.search(r"([\d.]+)kg", row[3]) if len(row) > 3 else None
                tenji = first_number(row[4]) if len(row) > 4 else None
                tilt = first_number(row[5]) if len(row) > 5 else None
                entries.append({
                    "枠": lane,
                    "体重": float(weight_m.group(1)) if weight_m else None,
                    "展示タイム": tenji,
                    "チルト": tilt,
                })
            except Exception:
                continue

    # スタート展示（コース別ST、F=フライング）
    start_courses = {}
    for m in re.finditer(r"(?<!\d)([1-6])\s*(F?\.\d{2})", page_text):
        lane_no = int(m.group(1))
        if lane_no not in start_courses:
            start_courses[lane_no] = m.group(2)

    # 水面気象情報
    temp_m = re.search(r"気温\s*([\d.]+)℃", page_text)
    wind_m = re.search(r"風速\s*([\d.]+)m", page_text)
    watertemp_m = re.search(r"水温\s*([\d.]+)℃", page_text)
    wave_m = re.search(r"波高\s*([\d.]+)cm", page_text)
    weather_word_m = re.search(r"℃\s*(晴|曇り|雨|雪|曇|小雨)", page_text)

    weather = {
        "気温": float(temp_m.group(1)) if temp_m else None,
        "天候": weather_word_m.group(1) if weather_word_m else None,
        "風速": float(wind_m.group(1)) if wind_m else 0.0,
        "水温": float(watertemp_m.group(1)) if watertemp_m else None,
        "波高": float(wave_m.group(1)) if wave_m else 0.0,
    }

    # 締切予定時刻（このレース単独の締切。JSON保存のためISO文字列で持つ）
    deadline_m = re.search(r"締切予定\s*(\d{1,2}):(\d{2})", page_text)
    deadline_iso = None
    if deadline_m:
        hh, mm = int(deadline_m.group(1)), int(deadline_m.group(2))
        try:
            deadline_iso = datetime(d.year, d.month, d.day, hh, mm).isoformat()
        except ValueError:
            deadline_iso = None

    return {
        "entries": entries, "start_courses": start_courses, "weather": weather,
        "締切予定": deadline_iso,
    }


# ------------------------------------------------------------
# オッズ
# ------------------------------------------------------------

def _parse_grouped_triple_odds(soup: BeautifulSoup, sep: str) -> dict[str, float]:
    """3連単/3連複ページ: 6グループ×(2着艇, 3着艇, オッズ)の3列繰り返し構造を解析する。"""
    tables = soup.find_all("table")
    result: dict[str, float] = {}
    for table in tables:
        grid = table_to_grid(table)
        for row in grid:
            if len(row) < 18:
                continue
            for g in range(6):
                first = g + 1
                base = g * 3
                second_txt, third_txt, odds_txt = row[base], row[base + 1], row[base + 2]
                try:
                    second = int(second_txt)
                    third = int(third_txt)
                    odds = float(odds_txt.replace(",", ""))
                except (ValueError, TypeError):
                    continue
                if second == first or third == first or second == third:
                    continue
                combo = tuple(sorted([first, second, third])) if sep == "=" else (first, second, third)
                key = sep.join(str(x) for x in combo)
                result[key] = odds
    return result


def _parse_matrix_odds(soup: BeautifulSoup, sep: str) -> dict[str, float]:
    """2連単・2連複/拡連複ページ用の暫定パーサ（実機構造未検証・要調整）。

    行=1着（軸）艇、列=相手艇 という一般的なマトリクス形式を仮定し、
    数値2つ以上を含むセルからオッズ（レンジの場合は下限値）を拾う。
    """
    result: dict[str, float] = {}
    tables = soup.find_all("table")
    for table in tables:
        grid = table_to_grid(table)
        for r_idx, row in enumerate(grid):
            if not row or not row[0].strip().isdigit():
                continue
            axis = int(row[0])
            if not (1 <= axis <= 6):
                continue
            for c_idx, cell in enumerate(row[1:], start=1):
                nums = extract_numbers(cell)
                if not nums:
                    continue
                partner = c_idx if c_idx < axis else c_idx + 1
                if partner == axis or not (1 <= partner <= 6):
                    continue
                combo = tuple(sorted([axis, partner])) if sep == "=" else (axis, partner)
                key = sep.join(str(x) for x in combo)
                result.setdefault(key, nums[0])
    return result


def _parse_single_odds(soup: BeautifulSoup) -> dict[str, float]:
    """単勝・複勝ページ用の暫定パーサ（実機構造未検証・要調整）。"""
    page_text = _norm(soup.get_text(" ", strip=True))
    result: dict[str, float] = {}
    for m in re.finditer(r"(?<!\d)([1-6])\s+([\d.]+)(?:\s*[-~〜]\s*([\d.]+))?", page_text):
        lane = m.group(1)
        odds = float(m.group(2))
        result.setdefault(lane, odds)
    return result


def fetch_odds(d: date, venue: str, rno: int, bet_type: str) -> dict[str, float]:
    """指定券種のオッズを {買い目文字列: オッズ} の形で取得する。"""
    jcd = VENUE_TO_JCD[venue]
    path = ODDS_PATH[bet_type]
    html = _fetch_html(path, {"rno": rno, "jcd": jcd, "hd": _date_str(d)})
    soup = BeautifulSoup(html, "html.parser")

    if bet_type == "3連単":
        result = _parse_grouped_triple_odds(soup, sep="-")
    elif bet_type == "3連複":
        result = _parse_grouped_triple_odds(soup, sep="=")
    elif bet_type == "2連単":
        result = _parse_matrix_odds(soup, sep="-")
    elif bet_type in ("2連複", "拡連複"):
        result = _parse_matrix_odds(soup, sep="=")
    elif bet_type in ("単勝", "複勝"):
        result = _parse_single_odds(soup)
    else:
        raise ValueError(f"未対応の券種: {bet_type}")

    if not result:
        raise ValueError(f"{bet_type}オッズを1件も取得できませんでした {_diagnostic_info(soup, html)}")
    return result


# ------------------------------------------------------------
# 確定結果
# ------------------------------------------------------------

BET_TYPE_LABELS = ["3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"]


def _parse_payouts(soup: BeautifulSoup) -> dict[str, list[dict]]:
    """払戻金テーブルを行ごとに正規表現で解析する。

    実機確認済みの構造: 組番は「2」「-」「4」「-」「5」のように数字と区切り記号が
    個別のセル（またはノード）に分かれており、勝式ラベルは拡連複(3行)・複勝(2行)では
    rowspanで先頭行にしか出ないため、行をなめながらラベルを引き継ぐ方式で解析する。
    """
    payouts: dict[str, list[dict]] = {}
    label_pattern = "|".join(BET_TYPE_LABELS)

    for table in soup.find_all("table"):
        table_text = _norm(table.get_text(" ", strip=True))
        if not any(bt in table_text for bt in BET_TYPE_LABELS):
            continue

        current_label = None
        for tr in table.find_all("tr"):
            text = _norm(tr.get_text(" ", strip=True))
            if not text:
                continue

            label_m = re.match(rf"^({label_pattern})", text)
            if label_m:
                current_label = label_m.group(1)
                rest = text[label_m.end():].strip()
            else:
                rest = text

            if current_label is None:
                continue

            combo_m = re.match(r"^(\d+(?:\s*[-=]\s*\d+)*)", rest)
            if not combo_m:
                continue
            combo = re.sub(r"\s+", "", combo_m.group(1))

            remainder = rest[combo_m.end():].strip()
            payout_m = re.search(r"¥?\s*([\d,]+)", remainder)
            if not payout_m:
                continue
            payout = int(payout_m.group(1).replace(",", ""))

            after_payout = remainder[payout_m.end():].strip()
            pop_m = re.match(r"^(\d+)$", after_payout)
            popularity = int(pop_m.group(1)) if pop_m else None

            payouts.setdefault(current_label, []).append({
                "組番": combo, "払戻金": payout, "人気": popularity,
            })

    return payouts


def fetch_race_result(d: date, venue: str, rno: int) -> dict | None:
    """確定結果（着順・払戻金・決まり手）を取得する。未確定の場合はNoneを返す。"""
    jcd = VENUE_TO_JCD[venue]
    html = _fetch_html("raceresult", {"rno": rno, "jcd": jcd, "hd": _date_str(d)})
    soup = BeautifulSoup(html, "html.parser")
    page_text = _norm(soup.get_text(" ", strip=True))

    if "まだ確定" in page_text or "発売中" in page_text:
        return None

    # 着順テーブル: 着 / 枠 / 選手 / タイム
    finish_order = []
    for table in soup.find_all("table"):
        grid = table_to_grid(table)
        rows = [r for r in grid if len(r) >= 3 and r[1].strip().isdigit()]
        if len(rows) >= 4:
            for r in rows:
                finish_order.append({"着": r[0], "枠": int(r[1]), "選手": r[2]})
            break

    payouts = _parse_payouts(soup)

    kimarite_m = re.search(r"決まり手\s*([^\s]+)", page_text)

    return {
        "finish_order": finish_order,
        "payouts": payouts,
        "決まり手": kimarite_m.group(1) if kimarite_m else None,
    }


# ------------------------------------------------------------
# 締切スケジュール（トップ画面用）
# ------------------------------------------------------------

def fetch_upcoming_deadlines(d, now: datetime, limit: int = 5) -> list[dict]:
    """「本日のレース」一覧ページから、まだ締切前の（会場, R, 締切時刻）を締切が近い順に取得する。

    注意: /race/raceindex は robots.txt でアクセス不可のため、
    全会場の状況が一覧できる /race/index (本日のレース) を利用する。
    このページは「進行状況/締切予定時刻」列に次に締切を迎えるレースのR番号と時刻が
    表示される想定で正規表現抽出している（実機の稼働中表示は未確認・要検証）。
    """
    html = _fetch_html("index", {"hd": _date_str(d)})
    soup = BeautifulSoup(html, "html.parser")

    results = []
    for tr in soup.find_all("tr"):
        link = tr.find("a", href=re.compile(r"raceindex\?jcd=\d+"))
        if not link:
            continue
        jcd_m = re.search(r"jcd=(\d+)", link.get("href", ""))
        if not jcd_m:
            continue
        venue = JCD_TO_VENUE.get(jcd_m.group(1))
        if not venue:
            continue

        row_text = _norm(tr.get_text(" ", strip=True))
        m = re.search(r"(\d{1,2})R\D{0,6}(\d{1,2}:\d{2})", row_text)
        if not m:
            continue  # 本日は開催終了・開催なし等

        rno = int(m.group(1))
        hh, mm = map(int, m.group(2).split(":"))
        try:
            deadline_dt = datetime(d.year, d.month, d.day, hh, mm)
        except ValueError:
            continue

        results.append({"開催日": d, "競走場": venue, "R": rno, "締切時刻": deadline_dt})

    upcoming = [r for r in results if r["締切時刻"] >= now]
    upcoming.sort(key=lambda r: r["締切時刻"])
    return upcoming[:limit]
