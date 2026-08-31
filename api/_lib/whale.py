"""
whale_tracker.py
================
Core engine for the Institutional Whale Tracker.

Detects statistically improbable trading days ("whale activity") using an
unsupervised Isolation Forest, then enriches each flagged day with:

  * Directional flow    -> Accumulation (buying) vs Distribution (selling),
                           derived from money-flow indicators (OBV, A/D line, MFI).
  * A human-readable tag -> Volume Spike / Price Gap / Churn / Breakout / Breakdown.
  * A 0-100 strength score -> so anomalies can be ranked, not just listed.
  * Benign-noise filtering -> drops illiquid, low-value days that fire false signals.

It also supports scanning a WATCHLIST of tickers and surfacing only those with
fresh whale activity in the last N days (a lightweight screener).

The module is UI-agnostic; use it from Streamlit, a CLI, a cron job or a notebook.

Quant rigor (see AnalysisConfig)
--------------------------------
Three methodological caveats a quant would raise are addressed explicitly:

  A. Lookahead bias. The default whole-window fit is correct and fast for an
     end-of-day scanner ("what is unusual as of today?"), because today's point
     is only ever scored against past-or-present data. It is NOT valid for
     backtesting, where fitting on the full window leaks the future into past
     rows. Set `detection_mode="walkforward"` for a leakage-free expanding-window
     fit suitable for historical evaluation.

  B. Comparable strength. Strength no longer uses per-stock min/max of the
     Isolation Forest score (which grades every stock on its own curve, so an
     85 on one name is not comparable to an 85 on another). Instead it blends
     components anchored to ABSOLUTE, cross-sectionally meaningful scales
     (RVOL, |return|, MFI extremity) plus a bounded transform of the raw score.
     Scores are now roughly comparable across tickers.

  C. Threshold, not quota. `contamination` forces the model to label a fixed %
     of days as anomalies regardless of regime. The default detection uses an
     absolute decision-function THRESHOLD, so a calm stock can return zero
     anomalies and a wild one can return many. A robust rolling MAD threshold
     is also available.

     THIS ONLY WORKS BECAUSE THE MODEL IS FIT WITH contamination="auto".
     sklearn computes `decision_function = score_samples - offset_`, and when
     `contamination` is a float it sets `offset_` to the `contamination`
     percentile of the TRAINING scores. Since the whole-window fit scores the
     very rows it was fit on, exactly `contamination x n` of them land below
     zero BY CONSTRUCTION — "threshold" mode then returns an identical flag set
     to "quota" mode on every input, calm or wild. That defeated the entire
     point of the mode. Fitting with contamination="auto" pins `offset_` at a
     fixed -0.5, which makes `decision_function` the absolute, regime-independent
     scale this mode always claimed to use. See `_new_model`.

Disclaimer
----------
Educational/research use only. NOT financial advice. Anomalous activity has many
benign causes (index rebalances, dividends, options expiry, news). DYOR.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind
from . import market_data, symbols

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "scikit-learn is required. Install with `pip install -r requirements.txt`."
    ) from exc


logger = logging.getLogger(__name__)

# Features fed into the Isolation Forest. These are directional/relative so the
# model reasons about *behaviour* rather than absolute price scale.
FEATURE_COLUMNS = [
    "Price_Change_%",
    "Volume_vs_Avg",
    "Abs_Price_Change_%",
    "MFI",
    "OBV_Change_Z",
    "Intraday_Range_%",
]


class WhaleTrackerError(Exception):
    """Base exception for all Whale Tracker errors."""


class DataFetchError(WhaleTrackerError):
    """Raised when market data cannot be fetched or is empty/invalid."""


@dataclass
class AnalysisConfig:
    """Tunable parameters for an analysis run.

    Detection modes
    ---------------
    detection_mode:
        * "threshold"  (default) -- flag days whose Isolation Forest decision
          score falls below `score_threshold`. NOT a quota: a calm stock may
          return zero anomalies, a volatile one many. Whole-window fit (fast;
          correct for end-of-day scanning, has lookahead bias for backtests).
        * "mad"        -- robust, self-calibrating threshold: flag days whose
          score is more than `mad_k` median-absolute-deviations below the
          rolling median score. Adapts the cutoff per stock without a fixed %.
        * "quota"      -- legacy behaviour: force `contamination` fraction of
          days to be anomalies (kept for backward compatibility).
        * "walkforward" -- leakage-free expanding-window evaluation for
          backtesting: for each day t >= warmup, fit scaler+model on days
          [0, t) only and score day t. Slower; use for historical validation.

    score_threshold:
        Decision-function cutoff for "threshold" mode, on the absolute scale
        produced by a contamination="auto" fit (see `_new_model`). There,
        `decision_function = 0.5 - s`, where `s` is the Liu et al. isolation
        score in (0, 1): s = 0.5 means "indistinguishable from normal", s -> 1
        means "strongly isolated". So the cutoff maps as

            score_threshold   0.00  ->  s > 0.50   (about half of all days)
            score_threshold  -0.10  ->  s > 0.60   (default; genuinely unusual)
            score_threshold  -0.15  ->  s > 0.65   (stricter)

        The default is -0.10, NOT 0.0. Zero sits at the centre of the isolation
        score distribution rather than in its tail.
    contamination:
        Used ONLY by "quota" mode, which takes its own quantile of the scores.
        It is deliberately NOT passed to the model fit — doing so is what
        collapsed "threshold" into "quota" (see caveat C in the module header).
    mad_k:
        Number of MADs below the rolling median score to flag in "mad" mode.
    walkforward_warmup:
        Minimum history (rows) before walk-forward starts scoring.
    walkforward_refit_every:
        Refit the model every N steps in walk-forward mode (>1 speeds it up by
        reusing a recent fit; 1 = refit every day, most rigorous).
    walkforward_max_fits:
        Hard ceiling on how many model fits a single walk-forward run may cost.
        Without it the run is O(rows): a 2y window is ~88 fits (~8s), but
        `period="max"` on a long-listed name is ~3,200 fits (~5 MINUTES), which
        is a denial-of-service primitive reachable from one request. When the
        cadence implied by `walkforward_refit_every` would exceed this budget,
        the cadence is widened so the cost stays bounded.

        This does NOT weaken the leakage guarantee. Refitting less often means
        day t is scored by a model trained on [0, t') for some t' <= t — still
        strictly past data, never future. A staler model is more conservative,
        not more informed. Set to 0 to disable the ceiling (offline use only).
    """

    period: str = "2y"
    detection_mode: str = "threshold"    # threshold | mad | quota | walkforward
    score_threshold: float = -0.10       # absolute cutoff for "threshold" mode
    mad_k: float = 3.0                   # MADs below rolling median for "mad" mode
    contamination: float = 0.02          # anomaly fraction for "quota" mode ONLY
    rolling_window: int = 20             # window for rolling averages / baselines
    mfi_window: int = 14                 # Money Flow Index look-back
    walkforward_warmup: int = 60         # min rows before walk-forward scores
    walkforward_refit_every: int = 5     # refit cadence in walk-forward mode
    walkforward_max_fits: int = 150      # hard ceiling on walk-forward cost
    random_state: int = 42
    min_rows: int = 40
    min_avg_turnover: float = 0.0        # min avg daily $ turnover to keep a ticker
    max_workers: int = 8                 # parallelism for watchlist scans

    VALID_MODES = ("threshold", "mad", "quota", "walkforward")

    def validate(self) -> None:
        if self.detection_mode not in self.VALID_MODES:
            raise ValueError(f"detection_mode must be one of {self.VALID_MODES}.")
        if not 0.0 < self.contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5 (exclusive).")
        if self.mad_k <= 0:
            raise ValueError("mad_k must be positive.")
        if self.rolling_window < 2:
            raise ValueError("rolling_window must be at least 2.")
        if self.mfi_window < 2:
            raise ValueError("mfi_window must be at least 2.")
        if self.walkforward_warmup < max(self.rolling_window, self.mfi_window):
            raise ValueError("walkforward_warmup should be >= rolling_window and mfi_window.")
        if self.walkforward_refit_every < 1:
            raise ValueError("walkforward_refit_every must be >= 1.")
        if self.walkforward_max_fits < 0:
            raise ValueError("walkforward_max_fits must be >= 0 (0 disables the ceiling).")
        if self.min_rows < max(self.rolling_window, self.mfi_window):
            raise ValueError("min_rows should be >= rolling_window and mfi_window.")


@dataclass
class AnalysisResult:
    """Output of a full single-ticker analysis run."""

    ticker: str
    data: pd.DataFrame       # full history: features + anomaly flags/labels
    anomalies: pd.DataFrame  # anomalous subset, ranked by strength (desc)
    config: AnalysisConfig = field(default_factory=AnalysisConfig)

    @property
    def total_days(self) -> int:
        return len(self.data)

    @property
    def anomaly_count(self) -> int:
        return len(self.anomalies)

    @property
    def anomaly_rate(self) -> float:
        return (self.anomaly_count / self.total_days) if self.total_days else 0.0

    def recent_anomalies(self, days: int = 10) -> pd.DataFrame:
        """Anomalies whose date falls within the last `days` calendar days."""
        if self.anomalies.empty:
            return self.anomalies
        cutoff = self.data.index.max() - pd.Timedelta(days=days)
        return self.anomalies[self.anomalies.index >= cutoff]

    @staticmethod
    def _bias_of(frame: pd.DataFrame) -> str:
        if frame.empty:
            return "Neutral"
        score = frame["Flow_Signal"].sum()
        if score > 0:
            return "Accumulation"
        if score < 0:
            return "Distribution"
        return "Mixed"

    @property
    def net_flow_bias(self) -> str:
        """Accumulation vs distribution across EVERY anomaly in the window.

        Note the horizon: on a 2y period this is a two-year verdict. It is a
        summary of the whole history, not a statement about where flow is now —
        use `recent_flow_bias` for that.
        """
        return self._bias_of(self.anomalies)

    def recent_flow_bias(self, days: int = 10) -> str:
        """Flow bias over the last `days` only — the current-state reading."""
        return self._bias_of(self.recent_anomalies(days))


class WhaleTracker:
    """Fetch -> engineer features -> detect -> classify -> score."""

    def __init__(self, config: Optional[AnalysisConfig] = None) -> None:
        self.config = config or AnalysisConfig()
        self.config.validate()

    # ------------------------------------------------------------------ #
    # Data acquisition
    # ------------------------------------------------------------------ #
    def fetch_data(self, ticker: str, period: Optional[str] = None) -> pd.DataFrame:
        """Download and clean OHLCV data, then engineer features."""
        ticker = self._normalize_ticker(ticker)
        period = period or self.config.period

        logger.info("Fetching %s (period=%s)", ticker, period)
        # NORMALISED AT THE BOUNDARY, not here. This method used to pass
        # yfinance's frame through untouched — tz-aware index and all — which is
        # why `index.py` had to strip the timezone from three frames by hand
        # before the event study could align them. Every frame now arrives on
        # the same contract.
        history = market_data.ohlcv(
            # OPT-OUT 4 OF 4. The reader's own ticker; see `market_data`'s
            # module docstring for why these four are the only ones.
            ticker, period=period, allow_stale=True)
        if history is None:
            raise DataFetchError(f"No data found for '{ticker}'. {symbols.hint(ticker)}")

        df = self._engineer_features(history)

        if len(df) < self.config.min_rows:
            raise DataFetchError(
                f"Only {len(df)} usable rows for '{ticker}'; need at least "
                f"{self.config.min_rows}. Try a longer period."
            )
        return df

    # ------------------------------------------------------------------ #
    # Feature engineering (incl. money-flow indicators)
    # ------------------------------------------------------------------ #
    def _engineer_features(self, history: pd.DataFrame) -> pd.DataFrame:
        w = self.config.rolling_window
        cols = ["Open", "High", "Low", "Close", "Volume"]
        df = history[[c for c in cols if c in history.columns]].copy()
        if "Open" not in df.columns:
            df["Open"] = df["Close"].shift(1)

        # --- basic returns / relative volume ---
        df["Price_Change_%"] = df["Close"].pct_change(fill_method=None) * 100
        df["Abs_Price_Change_%"] = df["Price_Change_%"].abs()
        rolling_vol = df["Volume"].rolling(w, min_periods=1).mean()
        df["Volume_vs_Avg"] = df["Volume"] / rolling_vol.replace(0, np.nan)   # RVOL
        df["Turnover"] = df["Close"] * df["Volume"]                            # $ traded
        df["Intraday_Range_%"] = (df["High"] - df["Low"]) / df["Close"].replace(0, np.nan) * 100
        df["Gap_%"] = (df["Open"] - df["Close"].shift(1)) / df["Close"].shift(1) * 100

        # --- On-Balance Volume (OBV) ---
        direction = np.sign(df["Close"].diff().fillna(0))
        df["OBV"] = (direction * df["Volume"]).fillna(0).cumsum()
        obv_change = df["OBV"].diff()
        obv_std = obv_change.rolling(w, min_periods=2).std().replace(0, np.nan)
        df["OBV_Change_Z"] = (obv_change / obv_std).fillna(0)

        # --- Accumulation/Distribution Line ---
        hl_range = (df["High"] - df["Low"]).replace(0, np.nan)
        mfm = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / hl_range
        mfm = mfm.fillna(0)
        df["AD_Line"] = (mfm * df["Volume"]).cumsum()

        # --- Money Flow Index (MFI) ---
        df["MFI"] = ind.money_flow_index(df["High"], df["Low"], df["Close"],
                                         df["Volume"], self.config.mfi_window)

        df = df.replace([np.inf, -np.inf], np.nan).dropna()
        return df

    # ------------------------------------------------------------------ #
    # Anomaly detection + enrichment
    # ------------------------------------------------------------------ #
    def detect_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score every day and flag anomalies according to `detection_mode`.

        Adds columns:
          Anomaly_Score : Isolation Forest decision_function (lower = more anomalous;
                          ~0 boundary, negative = anomaly). In walk-forward mode this
                          is the leakage-free out-of-sample score.
          Anomaly       : bool flag per the configured mode.
          Flow / Tag / Strength : enrichment (see _classify_flow / _tag_and_score).
        """
        if df.empty:
            raise WhaleTrackerError("Cannot detect anomalies on an empty DataFrame.")
        missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
        if missing:
            raise WhaleTrackerError(f"DataFrame is missing feature columns: {missing}")

        result = df.copy()
        mode = self.config.detection_mode

        if mode == "walkforward":
            result["Anomaly_Score"] = self._walkforward_scores(result)
        else:
            # Whole-window fit: correct & fast for end-of-day scanning.
            scaled = StandardScaler().fit_transform(result[FEATURE_COLUMNS].to_numpy())
            model = self._new_model()
            model.fit(scaled)
            result["Anomaly_Score"] = model.decision_function(scaled)

        result["Anomaly"] = self._flag_from_scores(result["Anomaly_Score"], mode)

        result = self._classify_flow(result)
        result = self._tag_and_score(result)
        return result

    def _new_model(self) -> IsolationForest:
        """Always fit with contamination="auto". See caveat C in the module header.

        Passing a float `contamination` here sets sklearn's `offset_` to that
        percentile of the training scores, which makes `decision_function` a
        RELATIVE scale and turns "threshold" mode into "quota" mode. "auto"
        pins `offset_` at -0.5, so `decision_function = 0.5 - s` on the absolute
        isolation-score scale and a cutoff means the same thing on every ticker.

        "quota" and "mad" are unaffected: both derive their cutoff from the
        scores themselves (a quantile and a rolling median), and both are
        invariant to the constant shift this changes.
        """
        return IsolationForest(
            contamination="auto",
            random_state=self.config.random_state,
            n_estimators=200,
        )

    def _flag_from_scores(self, scores: pd.Series, mode: str) -> pd.Series:
        """Turn decision-function scores into boolean anomaly flags.

        This is where the forced-quota problem (caveat C) is solved: only the
        legacy 'quota' mode pins a fixed fraction; 'threshold' and 'mad' let the
        count float with the actual regime (possibly zero, possibly many)."""
        scores = scores.fillna(scores.median())
        if mode == "quota":
            # Legacy: bottom `contamination` fraction of scores are anomalies.
            cutoff = np.quantile(scores.to_numpy(), self.config.contamination)
            return scores <= cutoff
        if mode == "mad":
            # Robust, self-calibrating: flag scores far below the rolling median.
            w = self.config.rolling_window
            med = scores.rolling(w, min_periods=w // 2).median()
            mad = (scores - med).abs().rolling(w, min_periods=w // 2).median()
            # 1.4826 scales MAD to a std-equivalent for ~normal data.
            lower = med - self.config.mad_k * 1.4826 * mad
            flag = scores < lower
            return flag.fillna(False)
        # Default "threshold" and "walkforward": absolute decision-function
        # cutoff on the contamination="auto" scale, where 0.5 - score is the
        # isolation score. The count floats with the regime: a calm series can
        # return zero, a violent one can return far more than `contamination`.
        return scores < self.config.score_threshold

    def _walkforward_scores(self, df: pd.DataFrame) -> pd.Series:
        """Leakage-free expanding-window scoring (caveat A).

        For each day t >= warmup, fit the scaler + Isolation Forest ONLY on days
        [0, t) and score day t out-of-sample. No future information ever touches
        a past decision. Warmup rows get NaN (insufficient history to score).
        Refit cadence is controlled by `walkforward_refit_every` for speed."""
        X = df[FEATURE_COLUMNS].to_numpy()
        n = len(X)
        warmup = self.config.walkforward_warmup
        refit_every = self._walkforward_cadence(n)
        scores = np.full(n, np.nan)

        scaler = None
        model = None
        last_fit = -(10 ** 9)
        for t in range(warmup, n):
            if model is None or (t - last_fit) >= refit_every:
                scaler = StandardScaler().fit(X[:t])
                model = self._new_model()
                model.fit(scaler.transform(X[:t]))
                last_fit = t
            scores[t] = model.decision_function(scaler.transform(X[t : t + 1]))[0]
        return pd.Series(scores, index=df.index)

    def _walkforward_cadence(self, n: int) -> int:
        """Refit cadence, widened when the row count would blow the fit budget.

        The configured cadence is a floor, never a ceiling: this only ever makes
        the run cheaper, and only when it would otherwise exceed
        `walkforward_max_fits`. See that field's docstring for why widening the
        cadence cannot leak future information.
        """
        configured = self.config.walkforward_refit_every
        budget = self.config.walkforward_max_fits
        steps = max(0, n - self.config.walkforward_warmup)
        if budget <= 0 or steps <= 0:
            return configured

        needed = math.ceil(steps / budget)
        if needed <= configured:
            return configured
        logger.info(
            "walk-forward: %d rows would cost %d fits; widening refit cadence "
            "%d -> %d to stay within the %d-fit budget",
            n, math.ceil(steps / configured), configured, needed, budget,
        )
        return needed

    def _classify_flow(self, df: pd.DataFrame) -> pd.DataFrame:
        """Label each row as Accumulation / Distribution / Neutral via a vote of
        OBV direction, A/D line direction, MFI level and price direction."""
        obv_up = df["OBV"].diff().fillna(0) > 0
        ad_up = df["AD_Line"].diff().fillna(0) > 0
        mfi_bull = df["MFI"] > 55
        mfi_bear = df["MFI"] < 45
        price_up = df["Price_Change_%"] > 0

        vote = (
            obv_up.astype(int) - (~obv_up).astype(int)
            + ad_up.astype(int) - (~ad_up).astype(int)
            + mfi_bull.astype(int) - mfi_bear.astype(int)
            + price_up.astype(int) - (~price_up).astype(int)
        )
        df["Flow_Signal"] = np.sign(vote).astype(int)  # -1, 0, +1
        df["Flow"] = df["Flow_Signal"].map({1: "Accumulation", -1: "Distribution", 0: "Neutral"})
        return df

    def _tag_and_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add a human-readable tag and a 0-100 strength score for each row."""
        def tag(row) -> str:
            tags = []
            if row["Volume_vs_Avg"] >= 2.5:
                tags.append("Volume Spike")
            if abs(row["Gap_%"]) >= 3:
                tags.append("Price Gap")
            if row["Volume_vs_Avg"] >= 2 and row["Abs_Price_Change_%"] < 1.5:
                tags.append("Churn")  # heavy volume, little price move = absorption
            if row["Price_Change_%"] >= 4 and row["Volume_vs_Avg"] >= 1.8:
                tags.append("Breakout")
            if row["Price_Change_%"] <= -4 and row["Volume_vs_Avg"] >= 1.8:
                tags.append("Breakdown")
            return ", ".join(tags) if tags else "Unusual Activity"

        df["Tag"] = df.apply(tag, axis=1)

        # --- Strength score (caveat B: cross-sectionally comparable) ---------
        # The old score normalized the Isolation Forest output by this stock's
        # own min/max, so an 85 on one name was graded on a different curve than
        # an 85 on another. We instead build Strength from components anchored to
        # ABSOLUTE, universally meaningful scales, plus a BOUNDED transform of the
        # raw score that does not depend on this series' extremes:
        #
        #   rvol   : relative volume vs its own recent average (already unit-free)
        #   move   : |daily return| in % (absolute market scale)
        #   mfi_ex : distance of MFI from neutral 50 (absolute 0-100 oscillator)
        #   iso    : logistic squash of how far below 0 the decision score is
        #            (0 -> ~0.5, more negative -> ->1), independent of series max
        rvol = df["Volume_vs_Avg"].clip(0, 6) / 6                 # ~6x vol = max
        move = df["Abs_Price_Change_%"].clip(0, 12) / 12          # ~12% move = max
        mfi_ex = (df["MFI"] - 50).abs() / 50                      # 0..1
        # Squash the raw decision score with a fixed-scale logistic. Anomalies
        # (score < 0) map above 0.5; the transform uses a fixed slope, NOT the
        # series' own min/max, so it is comparable across tickers.
        iso = 1.0 / (1.0 + np.exp(df["Anomaly_Score"].fillna(0) / 0.05))
        raw = 0.35 * iso + 0.30 * rvol + 0.20 * move + 0.15 * mfi_ex
        df["Strength"] = (raw * 100).round(0).clip(0, 100).astype(int)
        return df

    # ------------------------------------------------------------------ #
    # Orchestration (single ticker)
    # ------------------------------------------------------------------ #
    def analyze(self, ticker: str, period: Optional[str] = None) -> AnalysisResult:
        data = self.fetch_data(ticker, period=period)

        # Benign-noise filter: drop illiquid days below the turnover floor.
        if self.config.min_avg_turnover > 0:
            liquid = data["Turnover"].rolling(self.config.rolling_window, min_periods=1).mean()
            data = data[liquid >= self.config.min_avg_turnover]
            if data.empty:
                raise DataFetchError(
                    f"'{ticker}' falls below the minimum turnover threshold."
                )

        scored = self.detect_anomalies(data)
        anomalies = scored[scored["Anomaly"]].copy().sort_values("Strength", ascending=False)

        logger.info(
            "%s: %d anomalies / %d days (%.1f%%), bias=%s",
            ticker, len(anomalies), len(scored),
            100 * len(anomalies) / len(scored) if len(scored) else 0.0,
            AnalysisResult(ticker, scored, anomalies, self.config).net_flow_bias,
        )
        return AnalysisResult(
            ticker=self._normalize_ticker(ticker),
            data=scored,
            anomalies=anomalies,
            config=self.config,
        )

    # ------------------------------------------------------------------ #
    # Watchlist scan (multi-ticker screener)
    # ------------------------------------------------------------------ #
    def scan_watchlist(
        self,
        tickers: list[str],
        recent_days: int = 10,
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Scan many tickers and return a ranked table of those showing fresh
        whale activity within the last `recent_days`.

        Returns one row per ticker with recent anomaly count, dominant flow,
        top strength, latest signal date and its tag. Tickers that fail to fetch
        are skipped (with a logged warning) rather than aborting the whole scan.
        """
        tickers = [self._normalize_ticker(t) for t in dict.fromkeys(tickers) if t and t.strip()]
        rows: list[dict] = []

        def work(tk: str) -> Optional[dict]:
            try:
                res = self.analyze(tk, period=period)
            except WhaleTrackerError as exc:
                logger.warning("Skipping %s: %s", tk, exc)
                return None
            recent = res.recent_anomalies(recent_days)
            if recent.empty:
                return None
            top = recent.sort_values("Strength", ascending=False).iloc[0]
            acc = int((recent["Flow"] == "Accumulation").sum())
            dist = int((recent["Flow"] == "Distribution").sum())
            dominant = "Accumulation" if acc > dist else "Distribution" if dist > acc else "Mixed"
            return {
                "Ticker": tk,
                "Recent Anomalies": len(recent),
                # The ticker's OWN long-run flag rate, which is the null the
                # screener's significance test measures each hit against.
                "Anomaly Rate": res.anomaly_rate,
                "Total Days": res.total_days,
                "Dominant Flow": dominant,
                "Top Strength": int(top["Strength"]),
                "Latest Signal": recent.index.max().strftime("%Y-%m-%d"),
                "Latest Tag": top["Tag"],
                "Latest Close": round(float(res.data["Close"].iloc[-1]), 2),
                "RVOL (top)": round(float(top["Volume_vs_Avg"]), 2),
            }

        max_workers = max(1, min(self.config.max_workers, len(tickers) or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(work, tk): tk for tk in tickers}
            for fut in as_completed(futures):
                row = fut.result()
                if row:
                    rows.append(row)

        if not rows:
            return pd.DataFrame(
                columns=[
                    "Ticker", "Recent Anomalies", "Anomaly Rate", "Total Days",
                    "Dominant Flow", "Top Strength", "Latest Signal", "Latest Tag",
                    "Latest Close", "RVOL (top)",
                ]
            )
        return (
            pd.DataFrame(rows)
            .sort_values(["Top Strength", "Recent Anomalies"], ascending=False)
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        if not ticker or not str(ticker).strip():
            raise DataFetchError("Ticker symbol must be a non-empty string.")
        return str(ticker).strip().upper()


