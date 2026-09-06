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
