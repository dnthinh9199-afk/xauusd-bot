"""
strategy.py - Chiến lược giao dịch Price Action + SMC
Tổng hợp tín hiệu từ đa khung thời gian, tính SL/TP, độ mạnh tín hiệu
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple

import config
from indicators import IndicatorResult, CandlePattern, StructureEvent

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class TradeSignal:
    """Tín hiệu giao dịch hoàn chỉnh."""
    direction: str          # "BUY" / "SELL" / "WAIT"
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    strength: float = 0.0   # 0–100%
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    timeframe_bias: Dict[str, str] = field(default_factory=dict)  # tf → direction
    structure_event: str = ""   # BOS_UP / CHOCH_DOWN / v.v.
    nearest_pattern: str = ""   # Candle pattern gần nhất


# ============================================================
# STRATEGY ENGINE
# ============================================================

class PriceActionStrategy:
    """
    Chiến lược giao dịch dựa trên Price Action và SMC.
    Logic:
    1. Xác định bias từ H1 (xu hướng chính)
    2. Xác nhận bằng M15 (structure)
    3. Tìm điểm vào lệnh từ M5 (trigger)
    4. Tính SL/TP theo ATR
    5. Lọc tín hiệu theo cooldown và strength
    """

    def __init__(self):
        self._last_signal_time: Dict[str, datetime] = {}  # direction → time
        self._last_signal: Optional[TradeSignal] = None

    def generate_signal(
        self,
        results: Dict[str, IndicatorResult]
    ) -> TradeSignal:
        """
        Tạo tín hiệu giao dịch từ kết quả phân tích đa khung.

        Args:
            results: Dict mapping timeframe → IndicatorResult

        Returns:
            TradeSignal hoàn chỉnh
        """
        signal = TradeSignal(direction="WAIT")

        h1  = results.get(config.PRIMARY_TF)
        m15 = results.get(config.SECONDARY_TF)
        m5  = results.get(config.ENTRY_TF)

        if not all([h1, m15, m5]):
            signal.warnings.append("Thiếu dữ liệu một số timeframe")
            return signal

        # ---- Bước 1: Bias từ H1 ----
        h1_bias, h1_score = self._get_tf_bias(h1)
        signal.timeframe_bias[config.PRIMARY_TF] = h1_bias

        # ---- Bước 2: Xác nhận M15 ----
        m15_bias, m15_score = self._get_tf_bias(m15)
        signal.timeframe_bias[config.SECONDARY_TF] = m15_bias

        # ---- Bước 3: Trigger từ M5 ----
        m5_bias, m5_score = self._get_tf_bias(m5)
        signal.timeframe_bias[config.ENTRY_TF] = m5_bias

        # ---- Bước 4: Đồng thuận đa khung ----
        direction, base_strength = self._calc_mtf_consensus(
            h1_bias, h1_score, m15_bias, m15_score, m5_bias, m5_score
        )

        if direction == "WAIT":
            signal.reasons.append("Không đủ đồng thuận đa khung thời gian")
            return signal

        signal.direction = direction

        # ---- Bước 5: Điểm cộng từ SMC ----
        bonus = 0.0
        # Structure Events
        struct_bonus, struct_label = self._eval_structure(m15, direction)
        bonus += struct_bonus
        if struct_label:
            signal.structure_event = struct_label
            signal.reasons.append(f"Cấu trúc: {struct_label}")

        # Liquidity Sweep
        liq_bonus = self._eval_liquidity(m5, direction)
        bonus += liq_bonus
        if liq_bonus > 0:
            signal.reasons.append(f"Liquidity Sweep xác nhận {direction}")

        # Fake Breakout
        fb_bonus = self._eval_fake_breakout(m5, direction)
        bonus += fb_bonus
        if fb_bonus > 0:
            signal.reasons.append("Fake Breakout được phát hiện")

        # Candle Pattern tại M5
        pattern_bonus, pattern_name = self._eval_candle_patterns(m5, direction)
        bonus += pattern_bonus
        if pattern_name:
            signal.nearest_pattern = pattern_name
            signal.reasons.append(f"Mẫu nến: {pattern_name}")

        # Supply/Demand Zone
        sd_bonus = self._eval_sd_zones(m15, direction, m5.current_price)
        bonus += sd_bonus
        if sd_bonus > 0:
            signal.reasons.append(f"Giá trong {'Demand' if direction=='BUY' else 'Supply'} Zone")

        # RSI confirmation
        rsi_bonus = self._eval_rsi(m5, direction)
        bonus += rsi_bonus
        if rsi_bonus < 0:
            signal.warnings.append(f"RSI {m5.rsi:.1f} ngược chiều tín hiệu")

        # ---- Bước 6: Tổng điểm ----
        signal.strength = min(base_strength + bonus, 100.0)

        # ---- Bước 7: SL / TP ----
        entry_price = m5.current_price
        atr = m5.atr if m5.atr > 0 else entry_price * 0.001

        if direction == "BUY":
            stop_loss   = entry_price - atr * config.ATR_SL_MULT
            take_profit = entry_price + atr * config.ATR_TP_MULT
        else:
            stop_loss   = entry_price + atr * config.ATR_SL_MULT
            take_profit = entry_price - atr * config.ATR_TP_MULT

        risk   = abs(entry_price - stop_loss)
        reward = abs(entry_price - take_profit)
        rr     = reward / risk if risk > 0 else 0

        signal.entry       = round(entry_price, 2)
        signal.stop_loss   = round(stop_loss, 2)
        signal.take_profit = round(take_profit, 2)
        signal.risk_reward = round(rr, 2)

        # ---- Bước 8: Lọc cooldown ----
        if not self._check_cooldown(direction):
            signal.direction = "WAIT"
            signal.warnings.append(
                f"Cooldown {config.COOLDOWN_MINUTES} phút chưa hết, bỏ tín hiệu"
            )
            return signal

        # ---- Bước 9: Lọc strength tối thiểu ----
        if signal.strength < config.MIN_SIGNAL_STRENGTH:
            signal.direction = "WAIT"
            signal.warnings.append(
                f"Độ mạnh {signal.strength:.0f}% < ngưỡng {config.MIN_SIGNAL_STRENGTH}%"
            )
            return signal

        # Ghi nhận thời gian tín hiệu
        self._last_signal_time[direction] = datetime.now()
        self._last_signal = signal

        logger.info(
            f"[Strategy] ✅ Tín hiệu {direction} | Strength: {signal.strength:.0f}% | "
            f"Entry: {signal.entry} | SL: {signal.stop_loss} | TP: {signal.take_profit}"
        )
        return signal

    # ----------------------------------------------------------
    # BIAS PER TIMEFRAME
    # ----------------------------------------------------------

    def _get_tf_bias(self, result: IndicatorResult) -> Tuple[str, float]:
        """
        Xác định thiên hướng (BUY/SELL/NEUTRAL) cho một timeframe.
        Returns: (bias, score 0-100)
        """
        score = 0.0

        # Xu hướng Price Action
        if result.trend == "UPTREND":
            score += result.trend_strength * 0.6
            bias_trend = "BUY"
        elif result.trend == "DOWNTREND":
            score += result.trend_strength * 0.6
            bias_trend = "SELL"
        else:
            return "NEUTRAL", 30.0

        # EMA xác nhận
        if result.ema_signal == "BULLISH" and bias_trend == "BUY":
            score += 20
        elif result.ema_signal == "BEARISH" and bias_trend == "SELL":
            score += 20
        elif result.ema_signal != "NEUTRAL":
            score -= 10

        return bias_trend, min(score, 100)

    # ----------------------------------------------------------
    # MULTI-TIMEFRAME CONSENSUS
    # ----------------------------------------------------------

    def _calc_mtf_consensus(
        self,
        h1_bias: str, h1_score: float,
        m15_bias: str, m15_score: float,
        m5_bias: str, m5_score: float,
    ) -> Tuple[str, float]:
        """
        Tính toán sự đồng thuận giữa các khung thời gian.
        H1 = weight 50%, M15 = 30%, M5 = 20%
        """
        votes_buy = 0
        votes_sell = 0

        weights = {"H1": 0.50, "M15": 0.30, "M5": 0.20}
        biases  = {
            config.PRIMARY_TF:   (h1_bias,  h1_score),
            config.SECONDARY_TF: (m15_bias, m15_score),
            config.ENTRY_TF:     (m5_bias,  m5_score),
        }

        weighted_score = 0.0
        for tf, (bias, score) in biases.items():
            w = weights.get(tf, 0.2)
            if bias == "BUY":
                votes_buy += 1
                weighted_score += score * w
            elif bias == "SELL":
                votes_sell += 1
                weighted_score += score * w

        # Cần ít nhất H1 + một TF khác đồng thuận
        if votes_buy >= 2 and h1_bias == "BUY":
            return "BUY", weighted_score
        elif votes_sell >= 2 and h1_bias == "SELL":
            return "SELL", weighted_score

        return "WAIT", 0.0

    # ----------------------------------------------------------
    # SCORING HELPERS
    # ----------------------------------------------------------

    def _eval_structure(self, result: IndicatorResult, direction: str) -> Tuple[float, str]:
        """Đánh giá BOS / CHoCH cho tín hiệu."""
        if not result.structure_events:
            return 0.0, ""

        last_event = result.structure_events[-1]

        buy_events  = ["BOS_UP", "CHOCH_UP"]
        sell_events = ["BOS_DOWN", "CHOCH_DOWN"]

        if direction == "BUY" and last_event.kind in buy_events:
            return 15.0, last_event.kind
        elif direction == "SELL" and last_event.kind in sell_events:
            return 15.0, last_event.kind

        return 0.0, ""

    def _eval_liquidity(self, result: IndicatorResult, direction: str) -> float:
        """Liquidity Sweep xác nhận tín hiệu: +10."""
        if direction == "BUY"  and result.liquidity_swept == "LOW_SWEPT":
            return 10.0
        if direction == "SELL" and result.liquidity_swept == "HIGH_SWEPT":
            return 10.0
        return 0.0

    def _eval_fake_breakout(self, result: IndicatorResult, direction: str) -> float:
        """Fake Breakout xác nhận tín hiệu: +8."""
        if result.fake_breakout:
            return 8.0
        return 0.0

    def _eval_candle_patterns(
        self,
        result: IndicatorResult,
        direction: str
    ) -> Tuple[float, str]:
        """Candle Pattern xác nhận tín hiệu: tối đa +12."""
        if not result.candle_patterns:
            return 0.0, ""

        pattern_map = {
            "BUY":  ["PIN_BAR_BULL", "ENGULFING_BULL"],
            "SELL": ["PIN_BAR_BEAR", "ENGULFING_BEAR"],
        }
        neutral = ["INSIDE_BAR", "DOJI"]

        for p in reversed(result.candle_patterns):
            if p.name in (pattern_map.get(direction, []) + neutral):
                score = p.strength * 12
                return score, p.name

        return 0.0, ""

    def _eval_sd_zones(
        self,
        result: IndicatorResult,
        direction: str,
        price: float
    ) -> float:
        """Giá trong Supply/Demand Zone: +10."""
        if direction == "BUY":
            for zone in result.demand_zones:
                if zone.bottom <= price <= zone.top:
                    return 10.0
        elif direction == "SELL":
            for zone in result.supply_zones:
                if zone.bottom <= price <= zone.top:
                    return 10.0
        return 0.0

    def _eval_rsi(self, result: IndicatorResult, direction: str) -> float:
        """RSI xác nhận hoặc ngược chiều: ±8."""
        if direction == "BUY":
            if result.rsi_signal == "OVERSOLD":
                return 8.0
            elif result.rsi_signal == "OVERBOUGHT":
                return -8.0
        elif direction == "SELL":
            if result.rsi_signal == "OVERBOUGHT":
                return 8.0
            elif result.rsi_signal == "OVERSOLD":
                return -8.0
        return 0.0

    # ----------------------------------------------------------
    # COOLDOWN
    # ----------------------------------------------------------

    def _check_cooldown(self, direction: str) -> bool:
        """Kiểm tra cooldown giữa 2 tín hiệu cùng chiều."""
        last_time = self._last_signal_time.get(direction)
        if last_time is None:
            return True
        elapsed = datetime.now() - last_time
        return elapsed >= timedelta(minutes=config.COOLDOWN_MINUTES)


# Singleton instance
strategy = PriceActionStrategy()