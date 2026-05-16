"""
data_feed.py - Module lấy dữ liệu XAUUSD từ Yahoo Finance / Alpha Vantage
Tự động retry khi lỗi, cache dữ liệu để tránh spam API
"""

import time
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict
import requests

import config

logger = logging.getLogger(__name__)


class DataFeed:
    """
    Class quản lý việc lấy dữ liệu giá XAUUSD từ nhiều nguồn.
    Hỗ trợ: yfinance (mặc định), Alpha Vantage (backup)
    """

    def __init__(self):
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache 5 phút

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------

    def get_ohlcv(self, timeframe: str, retries: int = 3) -> Optional[pd.DataFrame]:
        """
        Lấy dữ liệu OHLCV cho timeframe chỉ định.

        Args:
            timeframe: "H1", "M15", "M5"
            retries: Số lần thử lại nếu lỗi

        Returns:
            DataFrame với cột: open, high, low, close, volume
            Hoặc None nếu thất bại hoàn toàn
        """
        # Kiểm tra cache còn hạn không
        if self._is_cache_valid(timeframe):
            logger.debug(f"[DataFeed] Cache hit cho {timeframe}")
            return self._cache[timeframe].copy()

        tf_config = config.TIMEFRAMES.get(timeframe)
        if not tf_config:
            logger.error(f"[DataFeed] Timeframe không hợp lệ: {timeframe}")
            return None

        # Thử lấy dữ liệu với retry
        for attempt in range(1, retries + 1):
            try:
                df = self._fetch_yfinance(
                    period=tf_config["period"],
                    interval=tf_config["interval"],
                )
                if df is not None and len(df) >= 50:
                    self._cache[timeframe] = df
                    self._cache_time[timeframe] = datetime.now()
                    logger.info(
                        f"[DataFeed] ✅ {timeframe}: {len(df)} nến "
                        f"(giá cuối: {df['close'].iloc[-1]:.2f})"
                    )
                    return df.copy()
                else:
                    logger.warning(
                        f"[DataFeed] Dữ liệu không đủ {timeframe} - attempt {attempt}"
                    )

            except Exception as e:
                logger.warning(
                    f"[DataFeed] Lỗi attempt {attempt}/{retries} [{timeframe}]: {e}"
                )
                if attempt < retries:
                    wait = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.info(f"[DataFeed] Đợi {wait}s rồi thử lại...")
                    time.sleep(wait)

        # Trả về cache cũ nếu có (dù hết hạn)
        if timeframe in self._cache:
            logger.warning(f"[DataFeed] Dùng cache cũ cho {timeframe}")
            return self._cache[timeframe].copy()

        logger.error(f"[DataFeed] ❌ Không lấy được dữ liệu {timeframe}")
        return None

    def get_all_timeframes(self) -> Dict[str, Optional[pd.DataFrame]]:
        """Lấy dữ liệu tất cả timeframes cùng lúc."""
        result = {}
        for tf in config.TIMEFRAMES:
            result[tf] = self.get_ohlcv(tf)
            time.sleep(0.5)  # Tránh rate limit
        return result

    def get_current_price(self) -> Optional[float]:
        """Lấy giá hiện tại của XAUUSD."""
        try:
            ticker = yf.Ticker(config.SYMBOL_YFINANCE)
            info = ticker.fast_info
            price = getattr(info, 'last_price', None)
            if price:
                return float(price)

            # Fallback: lấy từ dữ liệu M5
            df = self.get_ohlcv("M5")
            if df is not None:
                return float(df["close"].iloc[-1])
        except Exception as e:
            logger.error(f"[DataFeed] Lỗi lấy giá hiện tại: {e}")
        return None

    # ----------------------------------------------------------
    # PRIVATE METHODS
    # ----------------------------------------------------------

    def _fetch_yfinance(self, period: str, interval: str) -> Optional[pd.DataFrame]:
        """
        Lấy dữ liệu từ Yahoo Finance.
        Tự động chuẩn hóa cột và xử lý múi giờ.
        """
        ticker = yf.Ticker(config.SYMBOL_YFINANCE)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df is None or df.empty:
            raise ValueError("Yahoo Finance trả về dữ liệu rỗng")

        # Chuẩn hóa tên cột về lowercase
        df.columns = [c.lower() for c in df.columns]

        # Chỉ giữ cột cần thiết
        needed = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in needed if c in df.columns]]

        # Bỏ NaN và giá trị âm
        df = df.dropna()
        df = df[df["close"] > 0]

        # Reset index, giữ timestamp làm cột
        df = df.reset_index()
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "datetime"})
        elif "Date" in df.columns:
            df = df.rename(columns={"Date": "datetime"})

        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.sort_values("datetime").reset_index(drop=True)

        return df

    def _is_cache_valid(self, timeframe: str) -> bool:
        """Kiểm tra cache còn hạn sử dụng không."""
        if timeframe not in self._cache_time:
            return False
        age = datetime.now() - self._cache_time[timeframe]
        return age < self._cache_ttl


# Singleton instance
data_feed = DataFeed()