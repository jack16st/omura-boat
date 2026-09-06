"""
ネットワークなしで検証できる範囲のテスト。
- parsing_utils.table_to_grid: rowspan/colspan展開の正しさ
- scorer / allocator / settlement: 純粋ロジックの妥当性
実際のboatrace.jpページ構造そのもの（HTMLソース）は取得できていないため、
racelist/odds3t/raceresultで確認した「セル内容の並び」を模した簡易HTMLで代替検証する。
"""

from bs4 import BeautifulSoup
from parsing_utils import table_to_grid
import scorer
import allocator
import settlement


def test_table_to_grid_rowspan():
    html = """
    <table>
      <tr><td rowspan="2">A</td><td>B1</td></tr>
      <tr><td>B2</td></tr>
    </table>
    """
    grid = table_to_grid(BeautifulSoup(html, "html.parser").find("table"))
    assert grid[0] == ["A", "B1"], grid
    assert grid[1] == ["A", "B2"], grid
    print("test_table_to_grid_rowspan: OK")


def test_racelist_like_grid():
    # racelist実ページで確認した列並び: 枠, 写真, プロフィール, F/L/ST, 全国, 当地, モーター, ボート
    def racer_block(lane, toban, name):
        return f"""
        <tr>
          <td rowspan="4">{lane}</td><td rowspan="4"><img></td>
          <td rowspan="4">{toban} / A1 {name} 三重/三重 36歳/52.5kg</td>
          <td rowspan="4">F0 L0 0.15</td>
          <td rowspan="4">6.16 36.15 60.00</td>
          <td rowspan="4">6.88 49.67 70.59</td>
          <td rowspan="4">53 20.00 20.00</td>
          <td rowspan="4">67 75.00 87.50</td>
        </tr>
        <tr></tr><tr></tr><tr></tr>
        """
    names = ["中嶋 健一郎", "鈴木 秀茉", "岸本 雄貴", "上野 拓馬", "五反田 忍", "西山 育"]
    html = "<table>" + "".join(racer_block(i + 1, 4000 + i, names[i]) for i in range(6)) + "</table>"

    from scraper import _find_main_table
    soup = BeautifulSoup(html, "html.parser")
    _, _, lane_rows = _find_main_table(soup, min_cols=8)
    assert lane_rows is not None and len(lane_rows) == 6, lane_rows
    row = lane_rows[0]
    assert "4000" in row[2] and "中嶋" in row[2], row
    print("test_racelist_like_grid: OK")


def test_fetch_race_card_end_to_end():
    def racer_block(lane, toban, name, klass="A1"):
        return f"""
        <tr>
          <td rowspan="4">{lane}</td><td rowspan="4"><img></td>
          <td rowspan="4">{toban} / {klass} {name} 三重/三重 36歳/52.5kg</td>
          <td rowspan="4">F0 L0 0.15</td>
          <td rowspan="4">6.16 36.15 60.00</td>
          <td rowspan="4">6.88 49.67 70.59</td>
          <td rowspan="4">53 20.00 20.00</td>
          <td rowspan="4">67 75.00 87.50</td>
        </tr>
        <tr></tr><tr></tr><tr></tr>
        """
    names = ["中嶋 健一郎", "鈴木 秀茉", "岸本 雄貴", "上野 拓馬", "五反田 忍", "西山 育"]
    html = "<html><body><table>" + "".join(
        racer_block(i + 1, 4000 + i, names[i]) for i in range(6)
    ) + "</table></body></html>"

    import scraper
    original = scraper._fetch_html
    scraper._fetch_html = lambda path, params: html
    try:
        from datetime import date as _date
        entries = scraper.fetch_race_card(_date(2026, 9, 6), "津", 1)
    finally:
        scraper._fetch_html = original

    assert len(entries) == 6, entries
    assert entries[0]["枠"] == 1
    assert entries[0]["登録番号"] == "4000"
    assert entries[0]["級別"] == "A1"
    assert entries[0]["全国勝率"] == 6.16
    assert entries[0]["モーター勝率"] == 20.00
    print("test_fetch_race_card_end_to_end: OK ->", entries[0])


def test_odds3t_like_grid():
    # odds3tで確認した構造: 6グループ×3列(2着, 3着, オッズ)の繰り返し
    header_cells = "".join(f"<td>H{i}</td>" for i in range(18))
    row1 = ["2", "3", "5.2", "1", "3", "35.5", "1", "2", "202.6", "1", "2", "86.5", "1", "2", "228.2", "1", "2", "720.6"]
    row1_cells = "".join(f"<td>{v}</td>" for v in row1)
    html = f"<table><tr>{header_cells}</tr><tr>{row1_cells}</tr></table>"
    from scraper import _parse_grouped_triple_odds
    soup = BeautifulSoup(html, "html.parser")
    odds = _parse_grouped_triple_odds(soup, sep="-")
    assert odds.get("1-2-3") == 5.2, odds
    assert odds.get("2-1-3") == 35.5, odds
    assert odds.get("3-1-2") == 202.6, odds
    print("test_odds3t_like_grid: OK")


def test_scorer_basic():
    entries = [
        {"枠": 1, "選手名": "A", "全国勝率": 7.0, "当地勝率": 7.0, "モーター勝率": 45.0, "平均ST": 0.14},
        {"枠": 2, "選手名": "B", "全国勝率": 5.0, "当地勝率": 5.0, "モーター勝率": 35.0, "平均ST": 0.16},
        {"枠": 3, "選手名": "C", "全国勝率": 4.0, "当地勝率": 4.0, "モーター勝率": 30.0, "平均ST": 0.18},
        {"枠": 4, "選手名": "D", "全国勝率": 4.5, "当地勝率": 4.5, "モーター勝率": 32.0, "平均ST": 0.17},
        {"枠": 5, "選手名": "E", "全国勝率": 5.5, "当地勝率": 5.5, "モーター勝率": 38.0, "平均ST": 0.15},
        {"枠": 6, "選手名": "F", "全国勝率": 3.0, "当地勝率": 3.0, "モーター勝率": 25.0, "平均ST": 0.20},
    ]
    scored = scorer.score_entries(entries, weather={"風速": 1.0, "波高": 0.0})
    assert scored.iloc[0]["枠"] == 1, "通常気象下では1号艇が最上位になるはず"
    formation = scorer.recommend_formation(scored, "3連単", top_n=6)
    assert len(formation) == 6
    assert all(f.count("-") == 2 for f in formation)
    print("test_scorer_basic: OK ->", formation)

    # 荒天時はイン(1-2)が沈み、アウトが浮上する補正が効くか
    scored_rough = scorer.score_entries(entries, weather={"風速": 12.0, "波高": 8.0})
    lane1_calm = scored[scored["枠"] == 1]["総合スコア"].iloc[0]
    lane1_rough = scored_rough[scored_rough["枠"] == 1]["総合スコア"].iloc[0]
    assert lane1_rough < lane1_calm, "荒天時は1号艇のスコアが下がるはず"
    print("test_scorer_weather_adjust: OK")


def test_allocator_equal_profit():
    odds = {"1-2-3": 5.0, "1-3-2": 10.0, "1-2-4": 20.0}
    result = allocator.allocate_by_budget(odds, budget=3000)
    assert sum(result["allocation"].values()) in (2900, 3000, 3100)  # 100円丸め誤差込み
    payouts = list(result["payout_if_hit"].values())
    # 均等配分なので払戻額同士のばらつきは小さいはず(丸め誤差以内)
    assert max(payouts) - min(payouts) < max(payouts) * 0.15
    print("test_allocator_equal_profit: OK ->", result)

    torigami_odds = {"1-2-3": 0.9, "1-3-2": 0.8}
    tg = allocator.allocate_by_budget(torigami_odds, budget=1000)
    assert tg["torigami"] is True
    print("test_allocator_torigami: OK")


def test_settlement():
    allocation = {"1-2-4": 1000, "1-3-2": 500}
    result = {"payouts": {"3連単": [{"組番": "1-2-4", "払戻金": 390, "人気": 1}]}}
    settled = settlement.settle("3連単", allocation, result)
    assert settled["的中"] is True
    assert settled["払戻金合計"] == 3900
    assert settled["利益額"] == 3900 - 1500
    print("test_settlement: OK ->", settled)

    miss = settlement.settle("3連単", allocation, {"payouts": {"3連単": [{"組番": "5-6-1", "払戻金": 999, "人気": 1}]}})
    assert miss["的中"] is False
    print("test_settlement_miss: OK")


if __name__ == "__main__":
    test_table_to_grid_rowspan()
    test_racelist_like_grid()
    test_fetch_race_card_end_to_end()
    test_odds3t_like_grid()
    test_scorer_basic()
    test_allocator_equal_profit()
    test_settlement()
    print("\nALL TESTS PASSED")
