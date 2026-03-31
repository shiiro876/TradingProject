# 📦 Module 6 — Learning Engine (Phase 6)

**Status:** ✅ Complete  
**Phase:** 6 of 7  
**Files:** `learning/trainer.py`, `learning/backtester.py`, `learning/optimizer.py`  
**Tests:** `tests/test_module6.py` (48 tests)  

---

## Overview

Module 6 is the **Learning Engine** — the "AI brain" that gets smarter over time. It learns from every trade the system makes, backtests strategies on historical data, and optimizes parameters to find the best configuration.

```
Trade Journal (Module 2)  →  Trainer (ML model)  →  Win/Loss predictions
Historical OHLCV Data     →  Backtester          →  Strategy performance
Parameter Grid            →  Optimizer            →  Best settings
```

---

## Components

### `learning/trainer.py` — ML Trade Quality Predictor

Trains a RandomForest classifier on historical trade outcomes (WIN/LOSS) to predict whether a new signal is likely to be profitable.

**Feature Engineering:**
| Feature | Description |
|---------|-------------|
| `entry_price` | Entry price of the trade |
| `risk_reward` | Risk:Reward ratio of the setup |
| `scanner_score` | Scanner score (0-10) |
| `signal_strength_encoded` | STRONG=3, MEDIUM=2, WEAK=1 |
| `risk_per_share` | Dollar distance from entry to stop |
| `price_to_stop_ratio` | Risk as fraction of entry price |

**Key Methods:**

| Method | Description |
|--------|-------------|
| `train()` | Train model on journal data (needs ≥10 trades) |
| `predict(signal)` | Predict win probability for a new signal |
| `get_feature_importance()` | Show which features matter most |
| `save_model(path)` | Persist model to disk (pickle) |
| `load_model(path)` | Load previously saved model |
| `get_training_summary()` | Model accuracy and stats |
| `print_training_report()` | Formatted console output |

**Prediction Output:**
```python
{
    "symbol": "AAPL",
    "win_probability": 0.72,    # 0-1 scale
    "confidence": "HIGH",       # HIGH (≥65%), MEDIUM (≥45%), LOW (<45%)
    "recommendation": "TAKE",   # TAKE / CONSIDER / SKIP
    "model_used": True,         # True = ML model, False = heuristic fallback
}
```

### `learning/backtester.py` — Historical Strategy Backtester

Replays historical OHLCV data bar-by-bar through the trading pipeline to evaluate strategy performance.

**Simulation Features:**
- Walk-forward chronological processing
- Position sizing with 2% risk rule
- Trailing stop ratcheting on new highs
- TP1 and TP2 exit targets
- Maximum position limits enforced
- Equity curve tracking

**Key Methods:**

| Method | Description |
|--------|-------------|
| `run(symbol_data, min_score)` | Execute the backtest |
| `get_results()` | Comprehensive performance metrics |
| `get_equity_curve()` | Balance at each bar |
| `print_backtest_report()` | Formatted console output |

**Input Format:**
```python
symbol_data = {
    "AAPL": df,  # DataFrame with: open, high, low, close, volume, atr, score
    "XOM": df,
}
```

**Results Output:**
```python
{
    "total_trades": 15,
    "wins": 9, "losses": 6,
    "win_rate": 60.0,
    "total_pnl": 1250.00,
    "total_return": 12.5,
    "profit_factor": 1.85,
    "max_drawdown": 450.00,
    "final_balance": 11250.00,
}
```

### `learning/optimizer.py` — Strategy Parameter Optimizer

Grid-searches over strategy parameter combinations to find the best settings.

**Searchable Parameters:**
| Parameter | Description | Example Values |
|-----------|-------------|----------------|
| `atr_stop_multiplier` | ATR × this = stop distance | [1.5, 2.0, 2.5] |
| `risk_per_trade` | Fraction of account to risk | [0.01, 0.02, 0.03] |
| `max_positions` | Max simultaneous positions | [2, 3, 4] |
| `min_rr_ratio` | Minimum R:R ratio | [1.0, 1.5, 2.0] |
| `min_score` | Minimum scanner score for entry | [4.0, 5.0, 6.0] |

**Key Methods:**

| Method | Description |
|--------|-------------|
| `optimize(param_grid, metric)` | Run grid search |
| `get_best_params()` | Top-performing parameter set |
| `get_optimization_results()` | All results sorted by metric |
| `get_optimization_summary()` | Run count and top/bottom |
| `print_optimization_report()` | Formatted console output |

---

## Usage

### Train & Predict

```python
from learning.trainer import TradeTrainer
from learning.journal import TradeJournal

journal = TradeJournal()
trainer = TradeTrainer(journal=journal)

# Train on historical trades
result = trainer.train()
print(f"Accuracy: {result['accuracy']:.1%}")

# Predict on new signal
prediction = trainer.predict(signal)
if prediction["recommendation"] == "TAKE":
    print(f"✅ High confidence: {prediction['win_probability']:.1%}")
```

### Backtest

```python
from learning.backtester import Backtester

bt = Backtester(account_balance=10000)
bt.run({"AAPL": df_aapl, "XOM": df_xom}, min_score=5.0)
bt.print_backtest_report()
```

### Optimize

```python
from learning.optimizer import StrategyOptimizer

optimizer = StrategyOptimizer(symbol_data=data, account_balance=10000)
results = optimizer.optimize(
    param_grid={
        "atr_stop_multiplier": [1.5, 2.0, 2.5],
        "min_score": [4.0, 5.0, 6.0],
    },
    metric="total_return",
)
print(f"Best params: {optimizer.get_best_params()}")
```

---

## Configuration (config/settings.py)

```python
# Module 6 settings
MIN_TRADES_FOR_TRAINING = 10          # Min trades to train ML model
MODEL_SAVE_PATH = "data/trade_model.pkl"  # Model persistence path
BACKTEST_DEFAULT_MIN_SCORE = 5.0      # Default scanner score threshold
OPTIMIZER_MAX_COMBINATIONS = 500      # Max grid search combinations
```

---

## Tests

48 unit tests in `tests/test_module6.py`, organized into 15 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestTrainerInit` | 2 | Initialization, custom journal |
| `TestTrainerFeatureExtraction` | 3 | Feature columns, empty data, encoding |
| `TestTrainerTraining` | 3 | Insufficient data, success, empty journal |
| `TestTrainerPrediction` | 4 | Heuristic, ML, strong vs weak, classification |
| `TestTrainerFeatureImportance` | 2 | Trained, untrained |
| `TestTrainerPersistence` | 3 | Save/load, nonexistent, directory creation |
| `TestTrainerSummary` | 3 | Structure, report, untrained |
| `TestBacktesterInit` | 2 | Defaults, custom params |
| `TestBacktesterRun` | 6 | Empty, uptrend, downtrend, multi-symbol, max positions, state reset |
| `TestBacktesterResults` | 6 | Structure, empty, equity curve, trade records, report, empty report |
| `TestOptimizerInit` | 1 | Initialization |
| `TestOptimizerOptimize` | 4 | Basic, empty grid, multi-params, sorted |
| `TestOptimizerResults` | 6 | Best params, before optimize, summary, empty, report, empty report |
| `TestTrainerBacktesterIntegration` | 2 | Train→predict, backtest→train |
| `TestModule6Settings` | 1 | Config values |

```bash
python -m pytest tests/test_module6.py -v
```

---

## How Module 6 Connects to Other Modules

| Module | Connection | Direction |
|--------|-----------|-----------|
| Module 2 (Journal) | `TradeJournal.get_all_trades()` → training data | Input |
| Module 2 (Signals) | Signal dict → `trainer.predict()` | Input |
| Module 1 (Scanner) | Scanner scores used as features | Input |
| Module 4 (Risk) | Risk parameters used in backtester | Config |
| Module 5 (Execution) | Backtester simulates execution flow | Simulation |
| Module 7 (Dashboard) | Training summary, backtest results, predictions | Output |
