"""Small statistics for the pre/post analysis, in plain Python (no SciPy on the server).

Paired t-test with the Student t distribution via the regularized incomplete beta function
(Numerical Recipes' continued fraction), Cohen's dz, Hake's normalized gain, Brier score and AUC.
"""
from __future__ import annotations

import math
from statistics import mean, stdev


def _beta_cf(a, b, x, iterations=300, eps=3e-14):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _beta_cf(a, b, x) / a
    return 1.0 - front * _beta_cf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def t_critical(df, alpha=0.05):
    """t such that the two-sided p is alpha (bisection)."""
    low, high = 0.0, 1000.0
    for _ in range(200):
        middle = (low + high) / 2
        if t_two_sided_p(middle, df) > alpha:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def paired(before, after):
    """Paired comparison of two lists of the same students' scores (same order)."""
    n = len(before)
    if n != len(after):
        raise ValueError("Both lists need the same students.")
    result = {"n": n, "mean_before": mean(before) if n else None, "mean_after": mean(after) if n else None}
    if n < 2:
        return {**result, "mean_change": None, "sd_change": None, "t": None, "df": None, "p": None,
                "ci95": None, "cohens_dz": None}
    changes = [b - a for a, b in zip(before, after)]
    mean_change, sd_change = mean(changes), stdev(changes)
    df = n - 1
    if sd_change == 0:
        return {**result, "mean_change": mean_change, "sd_change": 0.0, "t": None, "df": df, "p": None,
                "ci95": (mean_change, mean_change), "cohens_dz": None}
    se = sd_change / math.sqrt(n)
    t = mean_change / se
    margin = t_critical(df) * se
    return {**result, "mean_change": mean_change, "sd_change": sd_change, "t": t, "df": df,
            "p": t_two_sided_p(abs(t), df), "ci95": (mean_change - margin, mean_change + margin),
            "cohens_dz": mean_change / sd_change}


def normalized_gain(pre_percent, post_percent):
    """Hake's gain (post - pre) / (100 - pre); None when the pretest was already 100%."""
    if pre_percent >= 100:
        return None
    return (post_percent - pre_percent) / (100 - pre_percent)


def brier(predictions, outcomes):
    return mean((p - y) ** 2 for p, y in zip(predictions, outcomes)) if predictions else None


def auc(predictions, outcomes):
    """Chance a random struggle got a higher prediction than a random non-struggle (ties count half)."""
    positives = [p for p, y in zip(predictions, outcomes) if y]
    negatives = [p for p, y in zip(predictions, outcomes) if not y]
    if not positives or not negatives:
        return None
    ranked = sorted((p, i) for i, p in enumerate(predictions))
    ranks = [0.0] * len(predictions)
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[ranked[k][1]] = (i + j) / 2 + 1
        i = j + 1
    positive_rank_sum = sum(r for r, y in zip(ranks, outcomes) if y)
    n_pos, n_neg = len(positives), len(negatives)
    return (positive_rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
