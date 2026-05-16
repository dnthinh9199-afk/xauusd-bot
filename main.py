"""
main.py - Entry point chính của XAUUSD Trading Bot
Điều phối toàn bộ: lấy dữ liệu → phân tích → tín hiệu → hiển thị → Telegram
Chạy vòng lặp tự động mỗi 15 phút
"""

import os
import sys
import time
import signal
import logging
import csv
import traceback
from datetime import datetime
from typing import Dict, Optional

import config
from data_feed import data_feed
from indicators import technical_analysis, IndicatorResult
from strategy import strategy, TradeSignal
from telegram_bot import telegram_bot

# ============================================================
# SETUP LOGGING
# ============================================================

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


# ============================================================
# CSV SIGNAL LOGGER
# ============================================================

def log_signal_to_csv(signal: TradeSignal) -> None:
    """Ghi tín hiệu vào file CSV để theo dõi lịch sử."""
    file_exists = os.path.isfile(config.SIGNAL_LOG)
    with open(config.SIGNAL_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "direction", "entry", "stop_loss",
            "take_profit", "risk_reward", "strength",
            "structure", "pattern", "reasons"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp":   signal.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "direction":   signal.direction,
            "entry":       signal.entry,
            "stop_loss":   signal.stop_loss,
            "take_profit": signal.take_profit,
            "risk_reward": signal.risk_reward,
            "strength":    f"{signal.strength:.0f}",
            "structure":   signal.structure_event,
            "pattern":     signal.nearest_pattern,
            "reasons":     " | ".join(signal.reasons),
        })


# ============================================================
# TERMINAL DASHBOARD
# ============================================================

def clear_screen() -> None:
    if config.CLEAR_TERMINAL:
        os.system("cls" if os.name == "nt" else "clear")


def print_header() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("╔══════════════════════════════════════════════════════╗")
    print("║       XAUUSD Price Action Bot  |  SMC Edition        ║")
    print("║              Phân tích đa khung thời gian            ║")
    print(f"╚══════════════════════════════════════════════════════╝")
    print(f"  🕐 Thời gian: {now}")
    print(f"  🔄 Cập nhật mỗi: {config.UPDATE_INTERVAL_MINUTES} phút\n")


def print_tf_analysis(tf: str, result: IndicatorResult) -> None:
    """In phân tích một timeframe ra terminal."""
    trend_icons = {
        "UPTREND":   "📈 UPTREND  ",
        "DOWNTREND": "📉 DOWNTREND",
        "SIDEWAY":   "➡️  SIDEWAY  ",
    }
    ema_icons = {
        "BULLISH": "🟢",
        "BEARISH": "🔴",
        "NEUTRAL": "⚪",
    }
    rsi_icons = {
        "OVERBOUGHT": "🔴 OB",
        "OVERSOLD":   "🟢 OS",
        "NEUTRAL":    "⚪ --",
    }

    label  = config.TIMEFRAMES[tf]["label"]
    trend  = trend_icons.get(result.trend, result.trend)
    ema_ic = ema_icons.get(result.ema_signal, "⚪")
    rsi_ic = rsi_icons.get(result.rsi_signal, "⚪")

    print(f"  ┌─ {label} ────────────────────────────────")
    print(f"  │  Xu hướng: {trend}  (sức mạnh: {result.trend_strength:.0f}%)")
    print(f"  │  Giá hiện tại: {result.current_price:.2f}   ATR: {result.atr:.2f}")
    print(f"  │  EMA({config.EMA_FAST}/{config.EMA_SLOW}): {result.ema_fast:.2f} / {result.ema_slow:.2f}  [{ema_ic} {result.ema_signal}]")
    print(f"  │  RSI({config.RSI_PERIOD}): {result.rsi:.1f}  [{rsi_ic}]")

    # Structure events
    if result.structure_events:
        last_ev = result.structure_events[-1]
        ev_icon = "🔵" if "UP" in last_ev.kind else "🟡"
        print(f"  │  Structure: {ev_icon} {last_ev.kind} @ {last_ev.price:.2f}")

    # Liquidity
    if result.liquidity_swept != "NONE":
        print(f"  │  💧 Liquidity Swept: {result.liquidity_swept}")

    # Fake Breakout
    if result.fake_breakout:
        print(f"  │  ⚠️  FAKE BREAKOUT phát hiện!")

    # Candle pattern
    if result.candle_patterns:
        p = result.candle_patterns[-1]
        print(f"  │  🕯️  Candle Pattern: {p.name} (strength: {p.strength:.0%})")

    print(f"  └─────────────────────────────────────────────────")


def print_signal(signal: TradeSignal) -> None:
    """In tín hiệu giao dịch ra terminal với màu sắc."""
    print("\n" + "═" * 58)

    if signal.direction == "BUY":
        print("  🟢🟢🟢  TÍN HIỆU: BUY (MUA)  🟢🟢🟢")
    elif signal.direction == "SELL":
        print("  🔴🔴🔴  TÍN HIỆU: SELL (BÁN) 🔴🔴🔴")
    else:
        print("  ⏸⏸⏸  KHÔNG CÓ TÍN HIỆU - CHỜ  ⏸⏸⏸")
        if signal.warnings:
            for w in signal.warnings:
                print(f"  ⚠️  {w}")
        print("═" * 58)
        return

    # Strength bar
    bar_len  = 30
    filled   = int(signal.strength / 100 * bar_len)
    bar      = "█" * filled + "░" * (bar_len - filled)
    str_icon = "🔥" if signal.strength >= 80 else ("💪" if signal.strength >= 65 else "✅")
    print(f"\n  {str_icon} Độ mạnh: [{bar}] {signal.strength:.0f}%")

    print(f"\n  💰 Entry:       {signal.entry:.2f}")
    print(f"  🛑 Stop Loss:   {signal.stop_loss:.2f}  ({abs(signal.entry - signal.stop_loss):.2f} USD)")
    print(f"  🎯 Take Profit: {signal.take_profit:.2f}  ({abs(signal.entry - signal.take_profit):.2f} USD)")
    print(f"  📐 Risk/Reward: 1:{signal.risk_reward:.1f}")

    # MTF bias
    print(f"\n  📊 Phân tích đa khung:")
    for tf, bias in signal.timeframe_bias.items():
        b_icon = "🟢" if bias == "BUY" else ("🔴" if bias == "SELL" else "⚪")
        print(f"     {b_icon} {tf:4s}: {bias}")

    # Reasons
    if signal.reasons:
        print(f"\n  🔍 Lý do tín hiệu:")
        for r in signal.reasons:
            print(f"     • {r}")

    # Warnings
    if signal.warnings:
        print(f"\n  ⚠️  Lưu ý:")
        for w in signal.warnings:
            print(f"     • {w}")

    print("\n" + "═" * 58)


def print_footer(next_update: str) -> None:
    print(f"\n  🔄 Lần cập nhật tiếp theo: {next_update}")
    print("  📁 Log: logs/trading_bot.log | Tín hiệu: logs/signals.csv")
    print("  🛑 Nhấn Ctrl+C để dừng bot\n")


# ============================================================
# CORE ANALYSIS LOOP
# ============================================================

def run_analysis() -> Optional[TradeSignal]:
    """
    Chạy một vòng phân tích đầy đủ.
    Returns TradeSignal hoặc None nếu lỗi.
    """
    logger.info("=" * 50)
    logger.info(f"[Main] Bắt đầu phân tích lúc {datetime.now().strftime('%H:%M:%S')}")

    # 1. Lấy dữ liệu tất cả timeframes
    all_data = data_feed.get_all_timeframes()
    missing  = [tf for tf, df in all_data.items() if df is None]
    if missing:
        logger.warning(f"[Main] Thiếu dữ liệu: {missing}")

    # 2. Phân tích kỹ thuật từng timeframe
    results: Dict[str, IndicatorResult] = {}
    for tf, df in all_data.items():
        if df is not None:
            logger.info(f"[Main] Đang phân tích {tf}...")
            results[tf] = technical_analysis.analyze(df)
        else:
            logger.warning(f"[Main] Bỏ qua {tf} - không có dữ liệu")

    if not results:
        logger.error("[Main] Không có kết quả phân tích nào")
        return None

    # 3. Sinh tín hiệu giao dịch
    signal = strategy.generate_signal(results)

    # 4. Hiển thị dashboard
    clear_screen()
    print_header()

    for tf in config.TIMEFRAMES:
        if tf in results:
            print_tf_analysis(tf, results[tf])
            print()

    print_signal(signal)

    # 5. Gửi Telegram nếu có tín hiệu
    if signal.direction in ("BUY", "SELL"):
        # Lưu vào CSV
        log_signal_to_csv(signal)

        # Gửi Telegram
        telegram_bot.send_signal(signal)

        # Gửi cảnh báo tín hiệu mạnh
        if signal.strength >= config.STRONG_SIGNAL_THRESHOLD:
            telegram_bot.send_strong_alert(signal)
            logger.info(
                f"[Main] 🔥 Tín hiệu MẠNH {signal.direction} "
                f"| Strength: {signal.strength:.0f}%"
            )

    return signal


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Vòng lặp chính của bot."""
    logger.info("=" * 60)
    logger.info(f"[Main] XAUUSD Trading Bot khởi động")
    logger.info(f"[Main] Cập nhật mỗi {config.UPDATE_INTERVAL_MINUTES} phút")
    logger.info("=" * 60)

    # Gửi thông báo khởi động Telegram
    telegram_bot.test_connection()
    telegram_bot.send_startup()

    # Xử lý Ctrl+C
    def handle_exit(sig, frame):
        print("\n\n  👋 Bot đang dừng... Tạm biệt!\n")
        logger.info("[Main] Bot dừng bởi người dùng (Ctrl+C)")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_exit)

    # Vòng lặp chính
    iteration = 0
    while True:
        iteration += 1
        logger.info(f"[Main] ── Vòng lặp #{iteration} ──")

        try:
            trade_signal = run_analysis()

            # Tính thời gian ngủ
            sleep_seconds = config.UPDATE_INTERVAL_MINUTES * 60
            next_update   = datetime.fromtimestamp(
                time.time() + sleep_seconds
            ).strftime("%H:%M:%S")
            print_footer(next_update)

            logger.info(f"[Main] Ngủ {sleep_seconds}s đến {next_update}")
            time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            handle_exit(None, None)

        except Exception as e:
            err_msg = f"Lỗi không mong đợi: {e}"
            logger.error(f"[Main] ❌ {err_msg}")
            logger.error(traceback.format_exc())
            telegram_bot.send_error(err_msg)

            # Đợi 60s rồi thử lại
            logger.info("[Main] Đợi 60s rồi tiếp tục...")
            time.sleep(60)


if __name__ == "__main__":
    main()