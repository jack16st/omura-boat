"""共通定数モジュール"""

# jcd（会場コード）順に24会場。インデックス+1 が boatrace.jp の jcd パラメータに対応。
VENUES = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
    "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
    "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
    "下関", "若松", "芦屋", "福岡", "唐津", "大村",
]

VENUE_TO_JCD = {name: f"{i+1:02d}" for i, name in enumerate(VENUES)}
JCD_TO_VENUE = {v: k for k, v in VENUE_TO_JCD.items()}

RACE_NUMBERS = list(range(1, 13))

LANE_MARKERS = {1: "⚪", 2: "⚫", 3: "🔴", 4: "🔵", 5: "🟡", 6: "🟢"}

BET_TYPES = ["3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"]
INPUT_MODES = ["金額（予算）で指定", "点数で指定"]

# オッズページのURLパス（券種ごと）
ODDS_PATH = {
    "3連単": "odds3t",
    "3連複": "odds3f",
    "2連単": "odds2tf",
    "2連複": "odds2tf",
    "拡連複": "oddsk",
    "単勝": "oddstf",
    "複勝": "oddstf",
}

# コース別の全国平均1着率(%) の目安値（公知の統計傾向に基づく概算値。会場により変動するため参考値）
COURSE_BASE_WIN_RATE = {1: 55.0, 2: 14.0, 3: 12.0, 4: 10.0, 5: 6.0, 6: 3.0}

BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
