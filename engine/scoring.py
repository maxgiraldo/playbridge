"""BBO-style MiniBridge scoring from the table prompt.

Each trick is worth 20 (minors), 30 (majors), or 40 (notrump).
Bonuses apply only if the declared goal is high enough and the contract makes:
9/10/11 tricks = 100, 12 = 500, 13 = 1000.
"""

from __future__ import annotations

TRICK_VALUES = {"C": 20, "D": 20, "H": 30, "S": 30, "NT": 40}


def trick_value(trump: str) -> int:
    try:
        return TRICK_VALUES[trump]
    except KeyError as exc:
        raise ValueError(f"invalid trump: {trump}") from exc


def contract_bonus(goal: int) -> int:
    if goal >= 13:
        return 1000
    if goal >= 12:
        return 500
    if goal >= 9:
        return 100
    return 0


def score_duplicate(
    trump: str,
    level: int,
    tricks: int,
    vulnerable: bool = False,
    doubled: int = 0,
) -> dict:
    """Duplicate (Chicago-style per board) contract scoring."""
    if not 1 <= level <= 7:
        raise ValueError(f"level must be 1-7, got {level}")
    if not 0 <= tricks <= 13:
        raise ValueError(f"tricks must be 0-13, got {tricks}")
    if doubled not in (0, 1, 2):
        raise ValueError(f"doubled must be 0, 1, or 2, got {doubled}")

    goal = level + 6
    made = tricks >= goal
    over = tricks - goal
    if trump in {"C", "D"}:
        undoubled_trick = 20 * level
        over_undoubled = 20
    elif trump in {"H", "S"}:
        undoubled_trick = 30 * level
        over_undoubled = 30
    elif trump == "NT":
        undoubled_trick = 40 + 30 * (level - 1)
        over_undoubled = 30
    else:
        raise ValueError(f"invalid trump: {trump}")

    multiplier = {0: 1, 1: 2, 2: 4}[doubled]
    if made:
        trick_points = undoubled_trick * multiplier
        game = trick_points >= 100
        bonus = 500 if game and vulnerable else 300 if game else 50
        if level == 6:
            bonus += 750 if vulnerable else 500
        elif level == 7:
            bonus += 1500 if vulnerable else 1000
        if doubled == 1:
            bonus += 50
        elif doubled == 2:
            bonus += 100
        if over:
            if doubled == 0:
                bonus += over * over_undoubled
            elif doubled == 1:
                bonus += over * (200 if vulnerable else 100)
            else:
                bonus += over * (400 if vulnerable else 200)
        points = trick_points + bonus
    else:
        under = goal - tricks
        if doubled == 0:
            trick_points = -under * (100 if vulnerable else 50)
        else:
            first = 200 if vulnerable else 100
            extra = 300 if vulnerable else 200
            raw = first + extra * (under - 1)
            trick_points = -raw * (2 if doubled == 2 else 1)
        bonus = 0
        points = trick_points

    return {
        "made": made,
        "tricks": tricks,
        "goal": goal,
        "level": level,
        "trump": trump,
        "vulnerable": vulnerable,
        "doubled": doubled,
        "trick_value": trick_value(trump),
        "trick_points": trick_points,
        "bonus": bonus,
        "points": points,
    }


def score_contract(trump: str, goal: int, tricks: int) -> dict:
    """Score one completed deal from the declaring side's point of view."""
    if not 7 <= goal <= 13:
        raise ValueError(f"goal must be 7-13, got {goal}")
    if not 0 <= tricks <= 13:
        raise ValueError(f"tricks must be 0-13, got {tricks}")

    value = trick_value(trump)
    made = tricks >= goal
    if made:
        trick_points = tricks * value
        bonus = contract_bonus(goal)
        points = trick_points + bonus
    else:
        undertricks = goal - tricks
        trick_points = -undertricks * value
        bonus = 0
        points = trick_points

    return {
        "made": made,
        "tricks": tricks,
        "goal": goal,
        "trump": trump,
        "trick_value": value,
        "trick_points": trick_points,
        "bonus": bonus,
        "points": points,
    }
