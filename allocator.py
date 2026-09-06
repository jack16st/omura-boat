"""
③資金配分・オッズ最適化ロジック

- 合成オッズの算出、1.0倍未満（トリガミ）の警告
- 的中時の利益が均等になるよう購入金額を自動配分（100円単位で丸め）
- 「金額（予算）で指定」「点数で指定」の2モードに対応
"""

from __future__ import annotations


def synthetic_odds(odds_list: list[float]) -> float:
    """合成オッズ（どれか1点が的中した場合の実質倍率）を算出する。"""
    valid = [o for o in odds_list if o and o > 0]
    if not valid:
        return 0.0
    return 1.0 / sum(1.0 / o for o in valid)


def allocate_by_budget(odds_dict: dict[str, float], budget: int, unit: int = 100) -> dict:
    """予算指定モード: 的中時の払戻金が均等になるよう、オッズの逆数比で配分する。"""
    combos = [c for c, o in odds_dict.items() if o and o > 0]
    if not combos:
        return {"allocation": {}, "synthetic_odds": 0.0, "torigami": True, "total_stake": 0}

    odds = [odds_dict[c] for c in combos]
    inv = [1.0 / o for o in odds]
    total_inv = sum(inv)
    raw = [budget * (w / total_inv) for w in inv]

    # unit円単位に丸め（最低1unit）
    rounded = [max(unit, round(a / unit) * unit) for a in raw]

    # 丸め誤差の調整: 予算との差分を、配分額が最大の買い目に反映する
    diff = budget - sum(rounded)
    if diff != 0 and rounded:
        idx = max(range(len(rounded)), key=lambda i: rounded[i])
        candidate = rounded[idx] + diff
        if candidate >= unit:
            rounded[idx] = candidate

    payout_if_hit = {combos[i]: round(rounded[i] * odds[i], 1) for i in range(len(combos))}
    synth = synthetic_odds(odds)

    return {
        "allocation": dict(zip(combos, rounded)),
        "payout_if_hit": payout_if_hit,
        "synthetic_odds": round(synth, 3),
        "torigami": synth < 1.0,
        "total_stake": sum(rounded),
    }


def allocate_by_points(odds_dict: dict[str, float], point_value: int = 100, points_per_combo: int = 1) -> dict:
    """点数指定モード: 各買い目に同一点数（point_value円 × points_per_combo）を均等購入する。"""
    combos = [c for c, o in odds_dict.items() if o and o > 0]
    amount = point_value * points_per_combo
    allocation = {c: amount for c in combos}
    odds = [odds_dict[c] for c in combos]
    synth = synthetic_odds(odds)
    payout_if_hit = {c: round(amount * odds_dict[c], 1) for c in combos}

    return {
        "allocation": allocation,
        "payout_if_hit": payout_if_hit,
        "synthetic_odds": round(synth, 3),
        "torigami": synth < 1.0,
        "total_stake": amount * len(combos),
    }
