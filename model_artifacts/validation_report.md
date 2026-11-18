# Struggle model: validation

Skill level: fine_skill. Training rows: 656,895 from 14,741 students. Validation rows: 90,966 from 2,090 students.
Struggle = the answer was wrong or used a hint. Lower log loss and Brier are better; skills count equally in the means.

| Model | Mean log loss over skills | Mean Brier over skills | AUC, all rows | Accuracy at 0.5 | Struggles caught at 0.5 |
|---|---:|---:|---:|---:|---:|
| struggle model (logistic) | 0.4248 | 0.1326 | 0.7521 | 82.4% | 25.5% |
| BKT only | 0.4421 | 0.1384 | 0.7185 | 81.9% | 31.3% |
| skill base rate | 0.4724 | 0.1511 | 0.6515 | 80.7% | 0.0% |
| boosted trees (comparison) | 0.4085 | 0.1269 | 0.7726 | 83.0% | 24.9% |

## Per skill

| Skill | Rows | Struggle rate | struggle model (logistic): log loss | BKT only: log loss | skill base rate: log loss | boosted trees (comparison): log loss |
|---|---:|---:|---:|---:|---:|---:|
| INT_ABS_COMPARE | 7,268 | 13.5% | 0.3738 | 0.3855 | 0.3959 | 0.3551 |
| INT_ADD_NEG | 20,965 | 16.4% | 0.3947 | 0.4129 | 0.4470 | 0.3795 |
| INT_CONTEXT | 7,840 | 25.9% | 0.4968 | 0.5270 | 0.5717 | 0.4825 |
| INT_DIV_NEG | 3,926 | 14.8% | 0.3974 | 0.4102 | 0.4188 | 0.3900 |
| INT_EXPR_NEG | 2,372 | 40.9% | 0.5340 | 0.5688 | 0.6788 | 0.5040 |
| INT_MULT_NEG | 3,952 | 10.1% | 0.3127 | 0.3203 | 0.3284 | 0.3073 |
| INT_NUMBER_LINE | 20,541 | 24.1% | 0.5056 | 0.5206 | 0.5518 | 0.4899 |
| INT_OPPOSITE_POS4 | 1,545 | 15.4% | 0.4230 | 0.4458 | 0.4304 | 0.3867 |
| INT_ORDER_NEG | 13,965 | 7.3% | 0.2511 | 0.2553 | 0.2611 | 0.2445 |
| INT_SUB_NEG | 8,592 | 33.9% | 0.5589 | 0.5748 | 0.6404 | 0.5459 |

## Does the predicted chance match what happened?

| Group (by prediction) | Rows | Mean predicted | Observed |
|---:|---:|---:|---:|
| 1 | 9,097 | 6.1% | 5.2% |
| 2 | 9,097 | 8.5% | 7.4% |
| 3 | 9,097 | 10.2% | 7.1% |
| 4 | 9,097 | 11.8% | 12.1% |
| 5 | 9,097 | 13.4% | 10.5% |
| 6 | 9,097 | 14.9% | 14.6% |
| 7 | 9,096 | 16.8% | 18.7% |
| 8 | 9,096 | 21.0% | 26.1% |
| 9 | 9,096 | 32.5% | 34.0% |
| 10 | 9,096 | 59.6% | 56.9% |

## Weights of the exported model

Inputs are standardised first, so the sizes are comparable. Positive = more likely to struggle.

| Input | Weight |
|---|---:|
| candidate_difficulty | +0.531 |
| last_correct | +0.000 |
| last_hint_used | +0.063 |
| recent_correct_rate | -0.216 |
| recent_hint_rate | +0.044 |
| candidate_skill_prior_encounters | +0.025 |
| candidate_skill_bkt_mastery | -0.496 |
| skill INT_ABS_COMPARE | +0.270 |
| skill INT_ADD_NEG | +0.183 |
| skill INT_CONTEXT | -0.102 |
| skill INT_DIV_NEG | +0.271 |
| skill INT_EXPR_NEG | -0.919 |
| skill INT_MULT_NEG | +0.176 |
| skill INT_NUMBER_LINE | -0.138 |
| skill INT_OPPOSITE_POS4 | -0.757 |
| skill INT_ORDER_NEG | -0.052 |
| skill INT_SUB_NEG | -0.485 |
| intercept | -1.556 |
