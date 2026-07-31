# pandas / numpy / scipy / statsmodels

**Role:** the modelling and backtesting layer. Not yet used by the recorder — these arrive with `/goal:features` onward.

## The division of labour

| Library | Used for |
|---|---|
| **numpy** | array math underneath everything |
| **pandas** | time-indexed joins, rolling windows, groupby |
| **scipy** | `stats.norm` for probabilities; `optimize` for the ladder fit |
| **statsmodels** | regression with confidence intervals and diagnostics |

## scipy.stats.norm

Converting a projected total into a market probability:

```python
from scipy.stats import norm
p_over = 1 - norm.cdf(line, loc=projected_total, scale=sigma)
```

See [../math/fair-value.md](../math/fair-value.md).

## scipy.optimize

Recovering the market's implied mean and σ from a ladder of prices:

```python
from scipy.optimize import minimize

def objective(params, lines, probs):
    mu, sigma = params
    implied = 1 - norm.cdf(lines, loc=mu, scale=sigma)
    return ((probs - implied) ** 2).sum()
```

See [../math/ladder-curve-fit.md](../math/ladder-curve-fit.md).

## statsmodels over scikit-learn

This is a deliberate choice.

scikit-learn gives you `.predict()`. statsmodels gives you `.summary()` — coefficients, standard errors, confidence intervals, p-values.

For this project the *uncertainty* is the point. The central question about the record modifier is "is β distinguishable from zero?", which is a confidence interval question. A point estimate can't answer it.

```python
import statsmodels.api as sm
model = sm.OLS(y, sm.add_constant(X)).fit()
print(model.summary())   # coefficients WITH confidence intervals
```

## No ML in v1

No XGBoost, no neural networks, no scikit-learn ensembles. Not yet.

A WNBA season is ~250–300 games league-wide. Gradient boosting on 250 rows with 7 features memorises the training set and produces a backtest that looks superb and generalises to nothing.

The rule: **the linear baseline is what any complex model must beat out-of-sample before it's adopted.** Most won't.

If complexity is ever justified, the order is: (1) add a genuinely new feature such as pace, (2) fit non-linear terms on a feature already known to matter, (3) only then consider ML — and with walk-forward validation, never a random train/test split, which leaks time.

## pandas caution

pandas makes time-series manipulation easy, including easy to get subtly wrong.

**Avoid `.shift()` for point-in-time alignment.** It's concise and it's how lookahead bugs get written. Filter explicitly in SQL:

```sql
WHERE game_date < :as_of
```

Explicit beats clever when the failure mode is a silently optimistic backtest. See [../math/point-in-time.md](../math/point-in-time.md).
