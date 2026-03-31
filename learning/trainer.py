# =============================================================================
# learning/trainer.py — ML Trade Quality Predictor
# =============================================================================
#
# PURPOSE:
#   Learns from the trade journal (historical trade outcomes) to predict
#   whether a new trade signal is likely to be a winner or a loser. This is
#   the "AI brain" that gets smarter over time — every trade the system makes
#   feeds back into the model so it can refine its predictions.
#
#   The trainer extracts features from completed trades (scanner score,
#   signal strength, R:R ratio, exit reason patterns) and trains a
#   scikit-learn classifier to predict trade outcome (WIN vs LOSS).
#
# HOW IT WORKS:
#   1. Load historical trades from the TradeJournal CSV.
#   2. Extract numerical features from each trade (feature engineering).
#   3. Train a RandomForest classifier on WIN/LOSS labels.
#   4. Expose a predict() method for new signals.
#   5. Save/load the trained model to disk for persistence.
#
# KEY FUNCTIONS:
#   - TradeTrainer(journal_path)
#       Class that manages model training and prediction.
#
#   - extract_features(df)         → Convert trade DataFrame to feature matrix.
#   - train()                      → Train the model on journal data.
#   - predict(signal)              → Predict WIN/LOSS probability for a signal.
#   - get_feature_importance()     → Show which features matter most.
#   - save_model(path)             → Persist model to disk.
#   - load_model(path)             → Load a previously saved model.
#   - get_training_summary()       → Model accuracy and stats.
#
# USAGE:
#   from learning.trainer import TradeTrainer
#   trainer = TradeTrainer()
#   trainer.train()
#   prediction = trainer.predict(signal_dict)
#   print(f"Win probability: {prediction['win_probability']:.1%}")
#
# =============================================================================

import os
import logging
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder

from config.settings import DATA_DIR
from learning.journal import TradeJournal

logger = logging.getLogger(__name__)

# Minimum number of trades required before we can train a meaningful model.
# With fewer trades, the model is unreliable and we fall back to heuristics.
MIN_TRADES_FOR_TRAINING = 10

# Features extracted from each trade for ML training
FEATURE_COLUMNS = [
    "entry_price",
    "risk_reward",
    "profit_loss_percent",
    "scanner_score",
    "signal_strength_encoded",
    "exit_reason_encoded",
    "risk_per_share",
    "price_to_stop_ratio",
]


class TradeTrainer:
    """
    ML-powered trade quality predictor that learns from the trade journal.

    Trains a RandomForest classifier on historical trade outcomes (WIN/LOSS)
    using features extracted from each trade record. Once trained, it can
    predict the probability of a new signal being profitable.

    Attributes:
        journal       (TradeJournal): Source of historical trade data.
        model         (RandomForestClassifier | None): Trained ML model.
        label_encoder (LabelEncoder): Encodes WIN/LOSS to 0/1.
        strength_map  (dict): Maps signal strength strings to integers.
        exit_map      (dict): Maps exit reason strings to integers.
        is_trained    (bool): Whether the model has been trained.
        training_stats (dict): Accuracy and stats from last training run.
    """

    def __init__(self, journal: TradeJournal | None = None):
        """
        Initialize the trade trainer.

        Args:
            journal: TradeJournal instance. If None, creates a default one.
        """
        self.journal = journal if journal is not None else TradeJournal()
        self.model: RandomForestClassifier | None = None
        self.label_encoder = LabelEncoder()
        self.is_trained = False
        self.training_stats: dict = {}

        # Encode categorical features as integers
        self.strength_map = {"STRONG": 3, "MEDIUM": 2, "WEAK": 1}
        self.exit_map = {
            "tp2": 4,      # Best outcome — hit second target
            "tp1": 3,      # Good — hit first target
            "manual": 2,   # Neutral — manual close
            "trailing_stop": 1,  # Neutral/protective close
            "stop": 0,     # Worst — hit initial stop loss
        }

        logger.info("TradeTrainer initialized.")

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert a trade journal DataFrame into a numerical feature matrix.

        Extracts and engineers features that are predictive of trade outcomes:
          - Entry price (normalized)
          - Risk:reward ratio
          - Scanner score (if available)
          - Signal strength (encoded as integer)
          - Exit reason (encoded as integer)
          - Risk per share (entry - stop)
          - Price-to-stop ratio (how far stop is from entry)

        Args:
            df: DataFrame from TradeJournal.get_all_trades().

        Returns:
            DataFrame with numerical features suitable for ML training.
        """
        features = pd.DataFrame()

        # Numerical columns — use directly (fill NaN with 0)
        features["entry_price"] = pd.to_numeric(
            df["entry_price"] if "entry_price" in df.columns else pd.Series(0, index=df.index),
            errors="coerce",
        ).fillna(0)
        features["risk_reward"] = pd.to_numeric(
            df["risk_reward"] if "risk_reward" in df.columns else pd.Series(0, index=df.index),
            errors="coerce",
        ).fillna(0)

        # Risk per share = entry - stop_loss
        stop_loss = pd.to_numeric(
            df["stop_loss"] if "stop_loss" in df.columns else pd.Series(0, index=df.index),
            errors="coerce",
        ).fillna(0)
        features["risk_per_share"] = (features["entry_price"] - stop_loss).clip(lower=0)

        # Price-to-stop ratio = (entry - stop) / entry
        features["price_to_stop_ratio"] = np.where(
            features["entry_price"] > 0,
            features["risk_per_share"] / features["entry_price"],
            0,
        )

        # Profit/loss percent (for completed trades only — not used for prediction)
        features["profit_loss_percent"] = pd.to_numeric(
            df["profit_loss_percent"] if "profit_loss_percent" in df.columns else pd.Series(0, index=df.index),
            errors="coerce",
        ).fillna(0)

        # Scanner score — if journal has a 'notes' column that might contain score info,
        # we try to extract it; otherwise default to 5.0 (neutral)
        if "scanner_score" in df.columns:
            features["scanner_score"] = pd.to_numeric(df["scanner_score"], errors="coerce").fillna(5.0)
        else:
            features["scanner_score"] = 5.0

        # Signal strength — encode categorical to integer
        if "signal_strength" in df.columns:
            features["signal_strength_encoded"] = df["signal_strength"].map(
                self.strength_map
            ).fillna(1)
        else:
            features["signal_strength_encoded"] = 2  # Default to MEDIUM

        # Exit reason — encode categorical to integer
        if "exit_reason" in df.columns:
            features["exit_reason_encoded"] = df["exit_reason"].map(
                self.exit_map
            ).fillna(2)
        else:
            features["exit_reason_encoded"] = 2  # Default to manual

        return features

    def train(self) -> dict:
        """
        Train the ML model on historical trade journal data.

        Loads all trades from the journal, extracts features, and trains a
        RandomForest classifier to predict WIN vs LOSS. Uses 5-fold cross
        validation to estimate out-of-sample accuracy.

        Returns:
            Dictionary containing training results:
                trained     (bool): Whether training succeeded.
                total_trades (int): Number of trades used.
                accuracy    (float): Cross-validated accuracy (0-1).
                win_rate    (float): Historical win rate (0-1).
                message     (str): Human-readable status.
        """
        df = self.journal.get_all_trades()

        if df.empty or len(df) < MIN_TRADES_FOR_TRAINING:
            msg = (
                f"Not enough trades to train ({len(df)} available, "
                f"need {MIN_TRADES_FOR_TRAINING}). Collect more data."
            )
            logger.warning(msg)
            self.training_stats = {
                "trained": False,
                "total_trades": len(df),
                "accuracy": 0.0,
                "win_rate": 0.0,
                "message": msg,
            }
            return self.training_stats

        # Ensure we have the label column
        if "win_loss" not in df.columns:
            self.training_stats = {
                "trained": False,
                "total_trades": len(df),
                "accuracy": 0.0,
                "win_rate": 0.0,
                "message": "Missing 'win_loss' column in trade journal.",
            }
            return self.training_stats

        # Extract features
        features = self.extract_features(df)

        # Select only the training columns (exclude profit_loss_percent which leaks)
        training_cols = [
            "entry_price", "risk_reward", "scanner_score",
            "signal_strength_encoded", "risk_per_share", "price_to_stop_ratio",
        ]
        X = features[training_cols].values

        # Encode labels: WIN=1, LOSS=0
        y = (df["win_loss"] == "WIN").astype(int).values

        # Check we have both classes
        if len(set(y)) < 2:
            msg = "Need both WIN and LOSS trades to train. Only one class present."
            logger.warning(msg)
            self.training_stats = {
                "trained": False,
                "total_trades": len(df),
                "accuracy": 0.0,
                "win_rate": float(y.mean()),
                "message": msg,
            }
            return self.training_stats

        # Train RandomForest classifier
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_split=3,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X, y)
        self.is_trained = True

        # Cross-validation accuracy
        n_folds = min(5, len(df))
        if n_folds >= 2:
            cv_scores = cross_val_score(self.model, X, y, cv=n_folds, scoring="accuracy")
            accuracy = round(float(cv_scores.mean()), 4)
        else:
            accuracy = 0.0

        win_rate = round(float(y.mean()), 4)

        self.training_stats = {
            "trained": True,
            "total_trades": len(df),
            "accuracy": accuracy,
            "win_rate": win_rate,
            "feature_names": training_cols,
            "message": (
                f"Model trained on {len(df)} trades. "
                f"CV accuracy: {accuracy:.1%}, Win rate: {win_rate:.1%}."
            ),
        }

        logger.info(
            "Model trained: %d trades, accuracy=%.1f%%, win_rate=%.1f%%.",
            len(df), accuracy * 100, win_rate * 100,
        )

        return self.training_stats

    def predict(self, signal: dict) -> dict:
        """
        Predict the probability of a trade signal being a winner.

        Converts a signal dictionary (from core/signals.py) into the feature
        format expected by the model, and returns the predicted WIN probability.

        If the model hasn't been trained yet, returns a heuristic-based
        estimate using scanner score and R:R ratio.

        Args:
            signal: Trade signal dictionary with keys like symbol, entry_price,
                    stop_loss, scanner_score, signal_strength, rr_ratio, etc.

        Returns:
            Dictionary containing:
                symbol          (str):   Stock ticker.
                win_probability (float): Predicted chance of winning (0-1).
                confidence      (str):   "HIGH", "MEDIUM", or "LOW".
                recommendation  (str):   "TAKE", "CONSIDER", or "SKIP".
                model_used      (bool):  Whether ML model was used (vs heuristic).
        """
        symbol = signal.get("symbol", "UNKNOWN")

        if not self.is_trained or self.model is None:
            # Fallback: heuristic-based prediction
            return self._heuristic_predict(signal)

        # Build feature vector matching training columns
        entry_price = float(signal.get("entry_price", 0))
        stop_loss = float(signal.get("stop_loss", 0))
        risk_reward = float(signal.get("rr_ratio", 0))
        scanner_score = float(signal.get("scanner_score", 5.0))
        signal_strength = self.strength_map.get(
            signal.get("signal_strength", "MEDIUM"), 2
        )
        risk_per_share = max(entry_price - stop_loss, 0)
        price_to_stop = risk_per_share / entry_price if entry_price > 0 else 0

        X = np.array([[
            entry_price, risk_reward, scanner_score,
            signal_strength, risk_per_share, price_to_stop,
        ]])

        # Predict probability
        proba = self.model.predict_proba(X)
        # Column index 1 = WIN probability (class 1)
        win_idx = list(self.model.classes_).index(1) if 1 in self.model.classes_ else 0
        win_prob = round(float(proba[0][win_idx]), 4)

        confidence, recommendation = self._classify_prediction(win_prob)

        return {
            "symbol": symbol,
            "win_probability": win_prob,
            "confidence": confidence,
            "recommendation": recommendation,
            "model_used": True,
        }

    def get_feature_importance(self) -> dict:
        """
        Get feature importance rankings from the trained model.

        Shows which features contribute most to the model's predictions,
        helping identify what matters most for trade success.

        Returns:
            Dictionary mapping feature name to importance score (0-1).
            Returns empty dict if model not trained.
        """
        if not self.is_trained or self.model is None:
            return {}

        feature_names = self.training_stats.get("feature_names", [])
        importances = self.model.feature_importances_

        importance_dict = {}
        for name, imp in zip(feature_names, importances):
            importance_dict[name] = round(float(imp), 4)

        # Sort by importance (descending)
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))

    def save_model(self, path: str | None = None) -> str:
        """
        Save the trained model to disk using pickle.

        Args:
            path: File path. Defaults to data/trade_model.pkl.

        Returns:
            Path where the model was saved.
        """
        if path is None:
            path = os.path.join(DATA_DIR, "trade_model.pkl")

        os.makedirs(os.path.dirname(path), exist_ok=True)

        model_data = {
            "model": self.model,
            "is_trained": self.is_trained,
            "training_stats": self.training_stats,
            "strength_map": self.strength_map,
            "exit_map": self.exit_map,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        logger.info("Model saved to '%s'.", path)
        return path

    def load_model(self, path: str | None = None) -> bool:
        """
        Load a previously saved model from disk.

        Args:
            path: File path. Defaults to data/trade_model.pkl.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if path is None:
            path = os.path.join(DATA_DIR, "trade_model.pkl")

        if not os.path.isfile(path):
            logger.warning("No saved model found at '%s'.", path)
            return False

        try:
            with open(path, "rb") as f:
                model_data = pickle.load(f)  # noqa: S301

            self.model = model_data["model"]
            self.is_trained = model_data["is_trained"]
            self.training_stats = model_data["training_stats"]
            self.strength_map = model_data.get("strength_map", self.strength_map)
            self.exit_map = model_data.get("exit_map", self.exit_map)

            logger.info("Model loaded from '%s'.", path)
            return True
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            return False

    def get_training_summary(self) -> dict:
        """
        Get a summary of the current model state and training results.

        Returns:
            Dictionary with model status, accuracy, feature importance.
        """
        summary = {
            "is_trained": self.is_trained,
            "training_stats": self.training_stats,
            "feature_importance": self.get_feature_importance(),
        }
        return summary

    def print_training_report(self) -> None:
        """
        Print a formatted training report to the console.
        """
        print("\n" + "=" * 60)
        print("  🧠 TRADE TRAINER — Model Report")
        print("=" * 60)

        if not self.is_trained:
            print("  Model not yet trained.")
            if self.training_stats.get("message"):
                print(f"  Reason: {self.training_stats['message']}")
            print("=" * 60)
            return

        stats = self.training_stats
        print(f"  Total Trades:    {stats.get('total_trades', 0)}")
        print(f"  CV Accuracy:     {stats.get('accuracy', 0):.1%}")
        print(f"  Win Rate:        {stats.get('win_rate', 0):.1%}")
        print("-" * 60)

        importance = self.get_feature_importance()
        if importance:
            print("  Feature Importance:")
            for feat, imp in importance.items():
                bar = "█" * int(imp * 40)
                print(f"    {feat:<26} {imp:.3f}  {bar}")

        print("=" * 60 + "\n")

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _heuristic_predict(self, signal: dict) -> dict:
        """
        Fallback prediction when ML model is not available.

        Uses simple rules based on scanner score and R:R ratio to
        estimate win probability.
        """
        symbol = signal.get("symbol", "UNKNOWN")
        score = float(signal.get("scanner_score", 5.0))
        rr = float(signal.get("rr_ratio", 1.5))
        strength = signal.get("signal_strength", "MEDIUM")

        # Simple heuristic: base probability from score and R:R
        base_prob = 0.4  # Baseline
        base_prob += (score - 5.0) * 0.04  # ±4% per score point above/below 5
        base_prob += (rr - 1.5) * 0.05     # ±5% per R:R point above/below 1.5

        # Strength bonus
        if strength == "STRONG":
            base_prob += 0.1
        elif strength == "WEAK":
            base_prob -= 0.1

        win_prob = max(0.05, min(0.95, round(base_prob, 4)))
        confidence, recommendation = self._classify_prediction(win_prob)

        return {
            "symbol": symbol,
            "win_probability": win_prob,
            "confidence": confidence,
            "recommendation": recommendation,
            "model_used": False,
        }

    @staticmethod
    def _classify_prediction(win_prob: float) -> tuple[str, str]:
        """
        Classify a win probability into confidence level and recommendation.

        Args:
            win_prob: Predicted probability of winning (0-1).

        Returns:
            Tuple of (confidence, recommendation).
        """
        if win_prob >= 0.65:
            return "HIGH", "TAKE"
        elif win_prob >= 0.45:
            return "MEDIUM", "CONSIDER"
        else:
            return "LOW", "SKIP"
