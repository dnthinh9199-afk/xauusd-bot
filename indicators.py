"""
indicators.py - Tính toán các chỉ báo kỹ thuật và Price Action patterns
Ưu tiên Price Action, dùng EMA/RSI/ATR chỉ để xác nhận
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import logging

import config

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SwingPoint:
    """Điểm Swing High hoặc Swing Low."""
    index: int
    price: float
    kind: str       # "high" hoặc "low"
    datetime: object = None


@dataclass
class Zone:
    """Supply Zone hoặc Demand Zone."""
    top: float
    bottom: float
    kind: str       # "supply" hoặc "demand"
    strength: int = 1   # Số lần test
    created_at: int = 0


@dataclass
class StructureEvent:
    """BOS hoặc CHoCH event."""
    kind: str       # "BOS_UP", "BOS_DOWN", "CHOCH_UP", "CHOCH_DOWN"
    price: float
    index: int


@dataclass
class CandlePattern:
    """Candle Pattern được phát hiện."""
    name: str       # "PIN_BAR_BULL", "ENGULFING_BEAR", v.v.
    index: int
    strength: float  # 0–1


@dataclass
class IndicatorResult:
    """Kết quả tổng hợp tất cả chỉ báo cho 1 timeframe."""
    # Trend
    trend: str = "SIDEWAY"          # UPTREND / DOWNTREND / SIDEWAY
    trend_strength: float = 0.0

    # EMA
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    ema_signal: str = "NEUTRAL"     # BULLISH / BEARISH / NEUTRAL

    # RSI
    rsi: float = 50.0
    rsi_signal: str = "NEUTRAL"     # OVERBOUGHT / OVERSOLD / NEUTRAL

    # ATR
    atr: float = 0.0

    # Price structure
    swing_highs: List[SwingPoint] = field(default_factory=list)
    swing_lows: List[SwingPoint] = field(default_factory=list)
    structure_events: List[StructureEvent] = field(default_factory=list)
    supply_zones: List[Zone] = field(default_factory=list)
    demand_zones: List[Zone] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)

    # Candle patterns
    candle_patterns: List[CandlePattern] = field(default_factory=list)

    # Liquidity
    liquidity_swept: str = "NONE"   # "HIGH_SWEPT", "LOW_SWEPT", "NONE"
    fake_breakout: bool = False

    # Current price
    current_price: float = 0.0
    current_close: float = 0.0


# ============================================================
# MAIN INDICATOR CLASS
# ============================================================

class TechnicalAnalysis:
    """
    Class tính toán tất cả chỉ báo kỹ thuật.
    Được thiết kế để dễ mở rộng thêm AI sau này.
    """

    def __init__(self):
        self.swing_lookback = 5   # Số nến xét trái/phải cho swing point

    def analyze(self, df: pd.DataFrame) -> IndicatorResult:
        """
        Phân tích toàn bộ dataframe và trả về IndicatorResult.

        Args:
            df: DataFrame với cột open, high, low, close, volume

        Returns:
            IndicatorResult chứa tất cả kết quả phân tích
        """
        result = IndicatorResult()

        if df is None or len(df) < 50:
            logger.warning("[Indicators] Không đủ dữ liệu để phân tích")
            return result

        try:
            # Giá hiện tại
            result.current_price = float(df["close"].iloc[-1])
            result.current_close = result.current_price

            # 1. Chỉ báo kỹ thuật cơ bản
            df = self._calc_ema(df)
            df = self._calc_rsi(df)
            df = self._calc_atr(df)

            result.ema_fast = float(df[f"ema_{config.EMA_FAST}"].iloc[-1])
            result.ema_slow = float(df[f"ema_{config.EMA_SLOW}"].iloc[-1])
            result.rsi      = float(df["rsi"].iloc[-1])
            result.atr      = float(df["atr"].iloc[-1])

            # EMA signal
            result.ema_signal = self._ema_signal(result.ema_fast, result.ema_slow)

            # RSI signal
            result.rsi_signal = self._rsi_signal(result.rsi)

            # 2. Price Action: Swing Points
            result.swing_highs, result.swing_lows = self._find_swings(df)

            # 3. Xu hướng chính theo Price Action
            result.trend, result.trend_strength = self._determine_trend(
                result.swing_highs, result.swing_lows, result.ema_signal
            )

            # 4. BOS & CHoCH
            result.structure_events = self._find_structure_events(
                result.swing_highs, result.swing_lows
            )

            # 5. Supply & Demand Zones
            result.supply_zones, result.demand_zones = self._find_sd_zones(
                df, result.swing_highs, result.swing_lows
            )

            # 6. Support & Resistance
            result.support_levels, result.resistance_levels = self._find_sr_levels(
                result.swing_highs, result.swing_lows, result.current_price
            )

            # 7. Liquidity Sweep
            result.liquidity_swept = self._detect_liquidity_sweep(df, result.swing_highs, result.swing_lows)

            # 8. Fake Breakout
            result.fake_breakout = self._detect_fake_breakout(df, result.resistance_levels, result.support_levels)

            # 9. Candle Patterns
            result.candle_patterns = self._find_candle_patterns(df)

        except Exception as e:
            logger.error(f"[Indicators] Lỗi phân tích: {e}", exc_info=True)

        return result

    # ----------------------------------------------------------
    # BASIC INDICATORS
    # ----------------------------------------------------------

    def _calc_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tính EMA nhanh và chậm."""
        df[f"ema_{config.EMA_FAST}"] = df["close"].ewm(span=config.EMA_FAST, adjust=False).mean()
        df[f"ema_{config.EMA_SLOW}"] = df["close"].ewm(span=config.EMA_SLOW, adjust=False).mean()
        return df

    def _calc_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tính RSI."""
        delta = df["close"].diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].fillna(50)
        return df

    def _calc_atr(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tính ATR (Average True Range)."""
        high = df["high"]
        low  = df["low"]
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.ewm(span=config.ATR_PERIOD, adjust=False).mean()
        return df

    def _ema_signal(self, fast: float, slow: float) -> str:
        if fast > slow * 1.001:   # Buffer 0.1% để tránh noise
            return "BULLISH"
        elif fast < slow * 0.999:
            return "BEARISH"
        return "NEUTRAL"

    def _rsi_signal(self, rsi: float) -> str:
        if rsi >= config.RSI_OB:
            return "OVERBOUGHT"
        elif rsi <= config.RSI_OS:
            return "OVERSOLD"
        return "NEUTRAL"

    # ----------------------------------------------------------
    # SWING POINTS
    # ----------------------------------------------------------

    def _find_swings(self, df: pd.DataFrame, n: int = 5) -> Tuple[List[SwingPoint], List[SwingPoint]]:
        """
        Tìm Swing High và Swing Low bằng phương pháp fractal.
        n: số nến bên trái và phải cần so sánh
        """
        highs = []
        lows  = []
        length = len(df)

        for i in range(n, length - n):
            window_high = df["high"].iloc[i - n: i + n + 1]
            window_low  = df["low"].iloc[i - n: i + n + 1]

            # Swing High: đỉnh cao nhất trong cửa sổ
            if df["high"].iloc[i] == window_high.max():
                dt = df["datetime"].iloc[i] if "datetime" in df.columns else None
                highs.append(SwingPoint(index=i, price=df["high"].iloc[i], kind="high", datetime=dt))

            # Swing Low: đáy thấp nhất trong cửa sổ
            if df["low"].iloc[i] == window_low.min():
                dt = df["datetime"].iloc[i] if "datetime" in df.columns else None
                lows.append(SwingPoint(index=i, price=df["low"].iloc[i], kind="low", datetime=dt))

        # Giữ 10 swing gần nhất
        return highs[-10:], lows[-10:]

    # ----------------------------------------------------------
    # TREND DETERMINATION
    # ----------------------------------------------------------

    def _determine_trend(
        self,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint],
        ema_signal: str
    ) -> Tuple[str, float]:
        """
        Xác định xu hướng bằng Higher High / Higher Low và Lower High / Lower Low.
        EMA chỉ dùng để xác nhận thêm.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "SIDEWAY", 0.0

        # Sắp xếp theo thứ tự thời gian
        sh = sorted(swing_highs, key=lambda x: x.index)
        sl = sorted(swing_lows,  key=lambda x: x.index)

        # So sánh 3 đỉnh và đáy gần nhất
        recent_highs = [s.price for s in sh[-3:]]
        recent_lows  = [s.price for s in sl[-3:]]

        hh = all(recent_highs[i] < recent_highs[i+1] for i in range(len(recent_highs)-1))
        hl = all(recent_lows[i]  < recent_lows[i+1]  for i in range(len(recent_lows)-1))
        lh = all(recent_highs[i] > recent_highs[i+1] for i in range(len(recent_highs)-1))
        ll = all(recent_lows[i]  > recent_lows[i+1]  for i in range(len(recent_lows)-1))

        pa_score = 0.0
        trend    = "SIDEWAY"

        if hh and hl:
            trend    = "UPTREND"
            pa_score = 70.0
        elif lh and ll:
            trend    = "DOWNTREND"
            pa_score = 70.0
        elif hh or hl:
            trend    = "UPTREND"
            pa_score = 45.0
        elif lh or ll:
            trend    = "DOWNTREND"
            pa_score = 45.0

        # Xác nhận bằng EMA
        if trend == "UPTREND"   and ema_signal == "BULLISH":
            pa_score = min(pa_score + 20, 100)
        elif trend == "DOWNTREND" and ema_signal == "BEARISH":
            pa_score = min(pa_score + 20, 100)
        elif ema_signal != "NEUTRAL" and trend != "SIDEWAY":
            pa_score = max(pa_score - 10, 0)

        return trend, pa_score

    # ----------------------------------------------------------
    # BOS & CHoCH
    # ----------------------------------------------------------

    def _find_structure_events(
        self,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint]
    ) -> List[StructureEvent]:
        """
        Phát hiện Break of Structure (BOS) và Change of Character (CHoCH).

        BOS: Cấu trúc tiếp diễn xu hướng chính (phá đỉnh trong uptrend)
        CHoCH: Cấu trúc đảo chiều (phá đáy trong uptrend)
        """
        events = []
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return events

        sh = sorted(swing_highs, key=lambda x: x.index)
        sl = sorted(swing_lows,  key=lambda x: x.index)

        # BOS UP: giá phá đỉnh swing high trước → tiếp diễn uptrend
        for i in range(1, len(sh)):
            if sh[i].price > sh[i-1].price:
                events.append(StructureEvent(
                    kind="BOS_UP",
                    price=sh[i].price,
                    index=sh[i].index
                ))

        # BOS DOWN: giá phá đáy swing low trước → tiếp diễn downtrend
        for i in range(1, len(sl)):
            if sl[i].price < sl[i-1].price:
                events.append(StructureEvent(
                    kind="BOS_DOWN",
                    price=sl[i].price,
                    index=sl[i].index
                ))

        # CHoCH: phát hiện khi xu hướng ngược chiều với BOS gần nhất
        if len(events) >= 2:
            last_two = sorted(events, key=lambda x: x.index)[-2:]
            if last_two[0].kind.startswith("BOS_UP") and last_two[1].kind == "BOS_DOWN":
                events.append(StructureEvent(
                    kind="CHOCH_DOWN",
                    price=sl[-1].price,
                    index=sl[-1].index
                ))
            elif last_two[0].kind.startswith("BOS_DOWN") and last_two[1].kind == "BOS_UP":
                events.append(StructureEvent(
                    kind="CHOCH_UP",
                    price=sh[-1].price,
                    index=sh[-1].index
                ))

        # Chỉ trả về 5 sự kiện gần nhất
        return sorted(events, key=lambda x: x.index)[-5:]

    # ----------------------------------------------------------
    # SUPPLY & DEMAND ZONES
    # ----------------------------------------------------------

    def _find_sd_zones(
        self,
        df: pd.DataFrame,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint]
    ) -> Tuple[List[Zone], List[Zone]]:
        """
        Xác định Supply Zone và Demand Zone dựa trên swing points.
        Supply Zone: vùng giá mà từ đó giá giảm mạnh (bán mạnh)
        Demand Zone: vùng giá mà từ đó giá tăng mạnh (mua mạnh)
        """
        supply_zones = []
        demand_zones = []

        atr = df["atr"].iloc[-1] if "atr" in df.columns else df["close"].std() * 0.5

        # Supply Zone từ Swing High
        for sh in swing_highs[-5:]:
            idx = sh.index
            if idx >= len(df):
                continue
            # Thân nến tại swing high tạo zone
            candle_open  = float(df["open"].iloc[idx])
            candle_close = float(df["close"].iloc[idx])
            zone_top    = max(candle_open, candle_close) + atr * 0.1
            zone_bottom = sh.price - atr * 0.5
            if zone_top > zone_bottom:
                supply_zones.append(Zone(
                    top=zone_top,
                    bottom=zone_bottom,
                    kind="supply",
                    created_at=idx
                ))

        # Demand Zone từ Swing Low
        for sl in swing_lows[-5:]:
            idx = sl.index
            if idx >= len(df):
                continue
            candle_open  = float(df["open"].iloc[idx])
            candle_close = float(df["close"].iloc[idx])
            zone_top    = sl.price + atr * 0.5
            zone_bottom = min(candle_open, candle_close) - atr * 0.1
            if zone_top > zone_bottom:
                demand_zones.append(Zone(
                    top=zone_top,
                    bottom=zone_bottom,
                    kind="demand",
                    created_at=idx
                ))

        return supply_zones[-3:], demand_zones[-3:]

    # ----------------------------------------------------------
    # SUPPORT & RESISTANCE
    # ----------------------------------------------------------

    def _find_sr_levels(
        self,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint],
        current_price: float,
        max_levels: int = 3
    ) -> Tuple[List[float], List[float]]:
        """
        Tìm các mức Support và Resistance gần giá hiện tại nhất.
        Support: swing lows dưới giá hiện tại
        Resistance: swing highs trên giá hiện tại
        """
        supports = sorted(
            [s.price for s in swing_lows if s.price < current_price],
            reverse=True
        )[:max_levels]

        resistances = sorted(
            [s.price for s in swing_highs if s.price > current_price]
        )[:max_levels]

        return supports, resistances

    # ----------------------------------------------------------
    # LIQUIDITY SWEEP
    # ----------------------------------------------------------

    def _detect_liquidity_sweep(
        self,
        df: pd.DataFrame,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint]
    ) -> str:
        """
        Phát hiện Liquidity Sweep:
        Khi giá vượt qua swing high/low rồi đóng cửa ngược lại.
        Đây là dấu hiệu Market Maker săn liquidity.
        """
        if len(df) < 3:
            return "NONE"

        last   = df.iloc[-1]
        prev   = df.iloc[-2]

        # Lấy swing levels gần nhất
        recent_highs = [s.price for s in swing_highs[-3:]]
        recent_lows  = [s.price for s in swing_lows[-3:]]

        if not recent_highs or not recent_lows:
            return "NONE"

        nearest_high = max(recent_highs)
        nearest_low  = min(recent_lows)

        # Sweep High: nến trước chọc lên vượt high, nến sau đóng cửa xuống
        if (prev["high"] > nearest_high and
                last["close"] < nearest_high and
                last["close"] < prev["open"]):
            return "HIGH_SWEPT"

        # Sweep Low: nến trước chọc xuống vượt low, nến sau đóng cửa lên
        if (prev["low"] < nearest_low and
                last["close"] > nearest_low and
                last["close"] > prev["open"]):
            return "LOW_SWEPT"

        return "NONE"

    # ----------------------------------------------------------
    # FAKE BREAKOUT
    # ----------------------------------------------------------

    def _detect_fake_breakout(
        self,
        df: pd.DataFrame,
        resistance_levels: List[float],
        support_levels: List[float]
    ) -> bool:
        """
        Phát hiện Fake Breakout:
        Giá vượt S/R nhưng không giữ được và quay đầu.
        """
        if len(df) < 3 or not resistance_levels or not support_levels:
            return False

        last = df.iloc[-1]
        prev = df.iloc[-2]

        nearest_res = min(resistance_levels)
        nearest_sup = max(support_levels)

        # Fake Breakout Up: prev phá resistance nhưng last đóng dưới resistance
        if prev["high"] > nearest_res and last["close"] < nearest_res:
            return True

        # Fake Breakout Down: prev phá support nhưng last đóng trên support
        if prev["low"] < nearest_sup and last["close"] > nearest_sup:
            return True

        return False

    # ----------------------------------------------------------
    # CANDLE PATTERNS
    # ----------------------------------------------------------

    def _find_candle_patterns(self, df: pd.DataFrame) -> List[CandlePattern]:
        """
        Phát hiện các mẫu nến Price Action:
        - Pin Bar (Hammer / Shooting Star)
        - Engulfing (Bullish / Bearish)
        - Inside Bar
        - Doji
        """
        patterns = []
        if len(df) < 3:
            return patterns

        for i in range(max(1, len(df) - 5), len(df)):
            c = df.iloc[i]
            p = df.iloc[i - 1] if i > 0 else None

            body   = abs(c["close"] - c["open"])
            total  = c["high"] - c["low"]
            upper  = c["high"] - max(c["close"], c["open"])
            lower  = min(c["close"], c["open"]) - c["low"]
            is_bull = c["close"] > c["open"]

            if total < 1e-6:
                continue

            # --- Pin Bar ---
            # Thân nhỏ (<= 30% tổng), bóng một chiều dài (>= 60%)
            if body / total <= 0.3:
                if lower / total >= 0.6 and upper / total <= 0.15:
                    patterns.append(CandlePattern(
                        name="PIN_BAR_BULL",
                        index=i,
                        strength=min(lower / total, 1.0)
                    ))
                elif upper / total >= 0.6 and lower / total <= 0.15:
                    patterns.append(CandlePattern(
                        name="PIN_BAR_BEAR",
                        index=i,
                        strength=min(upper / total, 1.0)
                    ))

            # --- Engulfing ---
            if p is not None:
                prev_body = abs(p["close"] - p["open"])
                if prev_body > 0:
                    # Bullish Engulfing: nến tăng phủ toàn bộ nến giảm trước
                    if (not (p["close"] > p["open"]) and   # prev giảm
                            is_bull and
                            c["open"] <= p["close"] and
                            c["close"] >= p["open"] and
                            body > prev_body):
                        patterns.append(CandlePattern(
                            name="ENGULFING_BULL",
                            index=i,
                            strength=min(body / prev_body / 2, 1.0)
                        ))
                    # Bearish Engulfing
                    elif (p["close"] > p["open"] and       # prev tăng
                              not is_bull and
                              c["open"] >= p["close"] and
                              c["close"] <= p["open"] and
                              body > prev_body):
                        patterns.append(CandlePattern(
                            name="ENGULFING_BEAR",
                            index=i,
                            strength=min(body / prev_body / 2, 1.0)
                        ))

                # --- Inside Bar ---
                if (c["high"] <= p["high"] and c["low"] >= p["low"]):
                    patterns.append(CandlePattern(
                        name="INSIDE_BAR",
                        index=i,
                        strength=0.5
                    ))

            # --- Doji ---
            if body / total <= 0.1:
                patterns.append(CandlePattern(
                    name="DOJI",
                    index=i,
                    strength=0.4
                ))

        return patterns[-5:]  # Trả về 5 pattern gần nhất


# Singleton instance
technical_analysis = TechnicalAnalysis()