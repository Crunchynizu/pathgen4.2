# BKT fit

Skill level: fine_skill. Limits: p_l0 0.0001 to 0.9999, p_t 0.0001 to 0.3, p_g 0.0001 to 0.3, p_s 0.0001 to 0.1.
Check: on validation students, BKT must beat always predicting the training correct rate (lower log loss, Brier not higher).

| Skill | P(L0) | P(T) | P(G) | P(S) | At a limit | Starts agree | Fit answers | Log loss vs constant | Brier vs constant | Check |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| INT_ABS_COMPARE | 0.941 | 0.053 | 0.300 | 0.100 | p_g, p_s | 6/6 | 52,406 | 0.3849 vs 0.3951 | 0.1137 vs 0.1164 | pass |
| INT_ADD_NEG | 0.859 | 0.026 | 0.300 | 0.100 | p_g, p_s | 6/6 | 157,012 | 0.4150 vs 0.4489 | 0.1259 vs 0.1382 | pass |
| INT_CONTEXT | 0.322 | 0.101 | 0.300 | 0.100 | p_g, p_s | 6/6 | 54,751 | 0.5292 vs 0.5761 | 0.1728 vs 0.1938 | pass |
| INT_DIV_NEG | 0.854 | 0.177 | 0.300 | 0.100 | p_g, p_s | 6/6 | 29,048 | 0.4136 vs 0.4224 | 0.1248 vs 0.1274 | pass |
| INT_EXPR_NEG | 0.157 | 0.030 | 0.290 | 0.100 | p_s | 6/6 | 17,995 | 0.5692 vs 0.6799 | 0.1904 vs 0.2434 | pass |
| INT_MULT_NEG | 0.899 | 0.201 | 0.300 | 0.081 | p_g | 6/6 | 28,940 | 0.3261 vs 0.3352 | 0.0916 vs 0.0937 | pass |
| INT_NUMBER_LINE | 0.316 | 0.101 | 0.300 | 0.100 | p_g, p_s | 6/6 | 154,965 | 0.5273 vs 0.5654 | 0.1721 vs 0.1889 | pass |
| INT_OPPOSITE_POS4 | 0.356 | 0.300 | 0.300 | 0.080 | p_t, p_g | 6/6 | 13,231 | 0.4853 vs 0.5379 | 0.1579 vs 0.1764 | pass |
| INT_ORDER_NEG | 0.699 | 0.300 | 0.300 | 0.058 | p_t, p_g | 6/6 | 100,819 | 0.2705 vs 0.2850 | 0.0735 vs 0.0757 | pass |
| INT_SUB_NEG | 0.667 | 0.024 | 0.300 | 0.100 | p_g, p_s | 6/6 | 64,735 | 0.5761 vs 0.6408 | 0.1947 vs 0.2243 | pass |

Mastery after one 6-question part (PathGen levels: below 0.50 not proficient, 0.50 to 0.79 developing, 0.80 and up strong):

| Skill | 0 of 6 right | 2 of 6 right | 4 of 6, last two wrong | 4 of 6, first two wrong | 6 of 6 right |
|---|---|---|---|---|---|
| INT_ABS_COMPARE | 0.06 not proficient | 0.13 not proficient | 0.97 strong | 0.98 strong | 1.00 strong |
| INT_ADD_NEG | 0.03 not proficient | 0.06 not proficient | 0.92 strong | 0.94 strong | 1.00 strong |
| INT_CONTEXT | 0.12 not proficient | 0.13 not proficient | 0.64 developing | 0.96 strong | 1.00 strong |
| INT_DIV_NEG | 0.21 not proficient | 0.26 not proficient | 0.97 strong | 0.99 strong | 1.00 strong |
| INT_EXPR_NEG | 0.04 not proficient | 0.04 not proficient | 0.32 not proficient | 0.85 strong | 1.00 strong |
| INT_MULT_NEG | 0.23 not proficient | 0.27 not proficient | 0.98 strong | 0.99 strong | 1.00 strong |
| INT_NUMBER_LINE | 0.12 not proficient | 0.13 not proficient | 0.63 developing | 0.96 strong | 1.00 strong |
| INT_OPPOSITE_POS4 | 0.34 not proficient | 0.37 not proficient | 0.88 strong | 1.00 strong | 1.00 strong |
| INT_ORDER_NEG | 0.33 not proficient | 0.34 not proficient | 0.94 strong | 1.00 strong | 1.00 strong |
| INT_SUB_NEG | 0.03 not proficient | 0.04 not proficient | 0.80 developing | 0.88 strong | 1.00 strong |
