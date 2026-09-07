import streamlit as st
from curl_cffi import requests
import datetime

st.set_page_config(page_title="競艇AI予想 デバッグモード3", layout="centered")
st.title("🚤 競艇AI予想 [デバッグ画面3] 生HTML構造確認")

TRACKS = {f"{i:02d}": name for i, name in enumerate(
    ["桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
     "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村"], 1)}

col_track, col_race = st.columns(2)
with col_track:
    selected_track_name = st.selectbox("対象のレース場", list(TRACKS.values()), index=20)
    selected_jcd = [k for k, v in TRACKS.items() if v == selected_track_name][0]
with col_race:
    rno = st.selectbox("レース番号", list(range(1, 13)), index=0)

hd = st.text_input("開催日 (YYYYMMDD)", value=datetime.date.today().strftime("%Y%m%d"))
keyword = st.text_input("周辺HTMLを見たいキーワード", value="全国")

if st.button("出走表ページを取得して生HTMLを確認する"):
    with st.spinner("データを取得中..."):
        url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={selected_jcd}&hd={hd}"
        st.write(f"**アクセスURL:** `{url}`")

        try:
            res = requests.get(url, impersonate="chrome110", timeout=10)
            res.encoding = "utf-8"
            st.write(f"**ステータスコード:** `{res.status_code}` / **HTML長:** `{len(res.text)}`")

            if res.status_code == 200:
                html = res.text
                idx = html.find(keyword)
                if idx == -1:
                    st.warning(f"キーワード「{keyword}」がHTML中に見つかりませんでした。")
                else:
                    st.markdown(f"#### 「{keyword}」周辺の生HTML（前後800文字）")
                    st.code(html[max(0, idx - 800):idx + 800], language="html")

                st.markdown("#### <table>タグの周辺（存在する場合）先頭2件")
                import re
                for m in list(re.finditer(r"<table", html))[:2]:
                    p = m.start()
                    st.code(html[p:p + 1000], language="html")

                st.markdown("#### <tbody>タグ以降（実データ行）先頭2件・各2000文字")
                for m in list(re.finditer(r"<tbody", html))[:2]:
                    p = m.start()
                    st.code(html[p:p + 2000], language="html")

                st.markdown("#### class属性の出現頻度トップ30（構造推定用）")
                classes = re.findall(r'class="([^"]+)"', html)
                from collections import Counter
                counter = Counter()
                for c in classes:
                    for token in c.split():
                        counter[token] += 1
                for name, count in counter.most_common(30):
                    st.write(f"`{name}` : {count}回")
            else:
                st.error(f"ページの取得に失敗しました。ステータスコード: {res.status_code}")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
