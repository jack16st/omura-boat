"""
④収支自動集計・的中判定ロジック

公式の確定結果と、アプリの推奨買い目（資金配分結果）を突合し、
的中判定・払戻金合計・利益額・回収率を算出する。
"""

from __future__ import annotations


def settle(bet_type: str, allocation: dict[str, int], result: dict | None) -> dict | None:
    """allocation: {買い目文字列: 購入金額}、result: fetch_race_result() の返り値。"""
    if result is None:
        return None

    total_stake = sum(allocation.values())
    payouts_for_type = result.get("payouts", {}).get(bet_type, [])

    hit_combos = {p["組番"] for p in payouts_for_type}
    total_return = 0
    hits = []

    for combo, stake in allocation.items():
        if combo in hit_combos:
            payout_per_100 = next(p["払戻金"] for p in payouts_for_type if p["組番"] == combo)
            ret = stake / 100 * payout_per_100
            total_return += ret
            hits.append({"組番": combo, "購入金額": stake, "払戻金": round(ret)})

    profit = total_return - total_stake
    recovery_rate = (total_return / total_stake * 100) if total_stake > 0 else 0.0

    return {
        "的中": len(hits) > 0,
        "的中詳細": hits,
        "投資額": total_stake,
        "払戻金合計": round(total_return),
        "利益額": round(profit),
        "回収率": round(recovery_rate, 1),
    }
