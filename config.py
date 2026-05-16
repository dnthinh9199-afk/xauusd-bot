"""
config.py - Cấu hình toàn bộ project XAUUSD Trading Bot
Chỉnh sửa file này trước khi chạy bot
"""

# ============================================================
# TELEGRAM CONFIGURATION
# ============================================================
TELEGRAM_BOT_TOKEN = "8662337998:AAHhhdnwYg6liLr6npIQgJMYcCqNvMH0lLI"      # Token từ @BotFather
TELEGRAM_CHAT_ID = "5777327437"        # Chat ID của bạn

# ============================================================
# DATA SOURCE CONFIGURATION
# Ưu tiên: yfinance (không cần API key)
# Backup: Alpha Vantage (cần API key free tại alphavantage.co)
# ============================================================
DATA_SOURCE       = "yfinance"                  # "yfinance" hoặc "alphavantage"
ALPHA_VANTAGE_KEY = "N6JNU4903OYK4OBN"    # Chỉ cần nếu dùng alphavantage

# ============================================================
# TRADING SYMBOL
# ============================================================
SYMBOL_YFINANCE   = "GC=F"                      # Gold Futures trên Yahoo Finance
SYMBOL_DISPLAY    = "XAUUSD"

# ============================================================
# TIMEFRAMES
# ============================================================
TIMEFRAMES = {
    "H1":  {"period": "5d",  "interval": "1h",  "label": "H1  (1 Hour)"},
    "M15": {"period": "2d",  "interval": "15m", "label": "M15 (15 Min)"},
    "M5":  {"period": "1d",  "interval": "5m",  "label": "M5  (5 Min)"},
}
PRIMARY_TF   = "H1"
SECONDARY_TF = "M15"
ENTRY_TF     = "M5"

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
EMA_FAST      = 8       # EMA nhanh để xác nhận xu hướng ngắn
EMA_SLOW      = 21      # EMA chậm để xác nhận xu hướng chính
RSI_PERIOD    = 14      # RSI để xác nhận momentum
RSI_OB        = 70      # RSI Overbought
RSI_OS        = 30      # RSI Oversold
ATR_PERIOD    = 14      # ATR để tính SL/TP
ATR_SL_MULT   = 1.5     # Nhân ATR cho Stop Loss
ATR_TP_MULT   = 3.0     # Nhân ATR cho Take Profit (RR = 1:2)

# ============================================================
# SIGNAL FILTER
# ============================================================
MIN_SIGNAL_STRENGTH = 55    # % tối thiểu để gửi tín hiệu
STRONG_SIGNAL_THRESHOLD = 75  # % để cảnh báo tín hiệu mạnh
COOLDOWN_MINUTES = 60       # Tối thiểu bao nhiêu phút giữa 2 tín hiệu cùng chiều

# ============================================================
# BOT SCHEDULE
# ============================================================
UPDATE_INTERVAL_MINUTES = 15   # Cập nhật mỗi 15 phút

# ============================================================
# LOGGING
# ============================================================
LOG_FILE      = "logs/trading_bot.log"
SIGNAL_LOG    = "logs/signals.csv"
LOG_LEVEL     = "INFO"

# ============================================================
# DISPLAY
# ============================================================
CLEAR_TERMINAL = True   # Xóa terminal mỗi lần cập nhật
SHOW_CHART     = False  # Hiển thị chart ASCII (experimental)