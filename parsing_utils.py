"""
テーブル解析共通ユーティリティ。

boatrace.jp の各ページは rowspan / colspan を多用したテーブルレイアウトのため、
特定のクラス名に依存せず「テーブル構造そのもの」から値を取り出せるよう、
rowspan/colspan を展開した2次元グリッドに変換するヘルパーを用意する。
これにより、サイト側のクラス名変更（スタイル変更）には影響を受けにくくなる一方、
列の並び順が変わった場合は影響を受けるため、定期的な動作確認は必要。
"""

from __future__ import annotations
import re


def table_to_grid(table_tag) -> list[list[str]]:
    """BeautifulSoupのtableタグをrowspan/colspan展開済みの2次元テキストグリッドに変換する。"""
    rows = table_tag.find_all("tr")
    grid: list[list[str]] = []
    span_tracker: dict[int, tuple[int, str]] = {}  # col_index -> (残り行数, テキスト)

    for tr in rows:
        row: list[str] = []
        col_idx = 0
        cells = iter(tr.find_all(["td", "th"]))
        next_cell = next(cells, None)

        while next_cell is not None or col_idx in span_tracker or any(
            c >= col_idx for c in span_tracker
        ):
            if col_idx in span_tracker:
                remaining, text = span_tracker[col_idx]
                row.append(text)
                if remaining - 1 <= 0:
                    del span_tracker[col_idx]
                else:
                    span_tracker[col_idx] = (remaining - 1, text)
                col_idx += 1
                continue

            if next_cell is None:
                break

            text = next_cell.get_text(" ", strip=True)
            colspan = int(next_cell.get("colspan", 1) or 1)
            rowspan = int(next_cell.get("rowspan", 1) or 1)
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    span_tracker[col_idx] = (rowspan - 1, text)
                col_idx += 1

            next_cell = next(cells, None)

        grid.append(row)

    return grid


def extract_numbers(text: str) -> list[float]:
    """文字列中の数値（小数含む）をすべて抽出する。"""
    return [float(x) for x in re.findall(r"-?\d+\.?\d*", text or "")]


def first_number(text: str) -> float | None:
    nums = extract_numbers(text)
    return nums[0] if nums else None
