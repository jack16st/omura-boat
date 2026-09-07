import streamlit as st
from curl_cffi import requests
from bs4 import BeautifulSoup
import datetime
import unicodedata

st.set_page_config(page_title="競艇AI予想 デバッグモード2", layout="centered")
st.title("🚤 競艇AI予想 [デバッグ画面2] 出走表/直前情報/オッズ")

TRACKS = {f"{i:02d}": name for i, name in enumerate(
    ["桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
     "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村"], 1)}

PAGES = {
    "出走表 (racelist)": "racelist",
    "直前情報 (beforeinfo)": "beforeinfo",
    "3連単オッズ (odds3t)": "odds3t",
    "本日のレース (index)": "index",
}

col_track, col_race = st.columns(2)
with col_track:
    selected_track_name = st.selectbox("対象のレース場", list(TRACKS.values()), index=20)  # 芦屋
    selected_jcd = [k for k, v in TRACKS.items() if v == selected_track_name][0]
with col_race:
    rno = st.selectbox("レース番号", list(range(1, 13)), index=0)

page_label = st.selectbox("確認するページ", list(PAGES.keys()))
page_path = PAGES[page_label]

hd = st.text_input("開催日 (YYYYMMDD)", value=datetime.date.today().strftime("%Y%m%d"))

if st.button("公式からHTMLを取得して解析する"):
    with st.spinner("データを取得中..."):
        url = f"https://www.boatrace.jp/owpc/pc/race/{page_path}?rno={rno}&jcd={selected_jcd}&hd={hd}"
        st.write(f"**アクセスURL:** `{url}`")

        try:
            res = requests.get(url, impersonate="chrome110", timeout=10)
            res.encoding = "utf-8"
            st.write(f"**ステータスコード:** `{res.status_code}`")

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                tables = soup.find_all("table")
                st.write(f"見つかったテーブルの数: {len(tables)} 個")

                st.markdown("#### ページ冒頭のテキスト（ブロック判定用）")
                st.text(unicodedata.normalize("NFKC", soup.get_text(" ", strip=True))[:300])

                st.markdown("#### 各テーブルの行（tr）ごとのテキスト（先頭6行まで）")
                for i, table in enumerate(tables):
                    rows = table.find_all("tr")
                    st.markdown(f"**--- テーブル [{i}]（行数:{len(rows)}） ---**")
                    for tr in rows[:6]:
                        row_text = unicodedata.normalize("NFKC", tr.get_text(separator=" | ", strip=True))
                        if row_text:
                            st.code(row_text)
            else:
                st.error(f"ページの取得に失敗しました。ステータスコード: {res.status_code}")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
