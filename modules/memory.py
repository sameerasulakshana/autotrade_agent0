import sqlite3
import json
import os
from datetime import datetime

class AgentMemory:
    def __init__(self, db_path=None):
        if db_path is None:
            # Base path is the AgentZero_Core directory
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "database", "brain.db")
        
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._init_db()

    def _init_db(self):
        # Table for active and past trades with context
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                ticket INTEGER PRIMARY KEY,
                symbol TEXT,
                type TEXT,
                entry_price REAL,
                sl REAL,
                tp REAL,
                entry_time TEXT,
                close_time TEXT,
                outcome TEXT, -- 'WIN', 'LOSS', 'BE', 'MANUAL_CLOSE'
                profit REAL,
                rationale TEXT, -- The "Why"
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Table for agent thoughts/logs (Stream of Consciousness)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS thoughts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                category TEXT, -- 'ANALYSIS', 'DECISION', 'REFLECTION', 'HEALTH'
                content TEXT
            )
        ''')

        # Table for account snapshots
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                balance REAL,
                equity REAL,
                margin REAL,
                free_margin REAL,
                open_positions_count INTEGER
            )
        ''')
        self.conn.commit()

        # Table for persistent symbol analysis
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_analysis (
                symbol TEXT PRIMARY KEY,
                timestamp TEXT,
                last_signal TEXT,
                rationale TEXT
            )
        ''')
        self.conn.commit()

    def save_analysis(self, symbol, signal, rationale):
        self.cursor.execute('''
            INSERT OR REPLACE INTO market_analysis (symbol, timestamp, last_signal, rationale)
            VALUES (?, ?, ?, ?)
        ''', (symbol, datetime.now().isoformat(), signal, rationale))
        self.conn.commit()

    def get_last_analysis(self, symbol):
        self.cursor.execute("SELECT * FROM market_analysis WHERE symbol = ?", (symbol,))
        row = self.cursor.fetchone()
        if not row: return None
        columns = [description[0] for description in self.cursor.description]
        return dict(zip(columns, row))

    def log_account_snapshot(self, data):
        self.cursor.execute('''
            INSERT INTO account_history (timestamp, balance, equity, margin, free_margin, open_positions_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), data['balance'], data['equity'], 
              data['margin'], data['free_margin'], data['open_positions_count']))
        self.conn.commit()

    def log_trade(self, ticket, symbol, order_type, price, sl, tp, rationale):
        self.cursor.execute('''
            INSERT INTO trades (ticket, symbol, type, entry_price, sl, tp, entry_time, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticket, symbol, order_type, price, sl, tp, datetime.now().isoformat(), rationale))
        self.conn.commit()

    def update_trade_outcome(self, ticket, close_time, outcome, profit):
        self.cursor.execute('''
            UPDATE trades 
            SET close_time = ?, outcome = ?, profit = ?, is_active = 0
            WHERE ticket = ?
        ''', (close_time, outcome, profit, ticket))
        self.conn.commit()

    def log_thought(self, category, content):
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Color-coded logic for CLI
        colors = {
            "HEALTH": "\033[94m",    # Blue
            "DECISION": "\033[92m",  # Green
            "ANALYSIS": "\033[93m",  # Yellow
            "ERROR": "\033[91m",     # Red
            "AI_REFLECTION": "\033[95m", # Magenta
            "SUCCESS": "\033[92m\033[1m" # Bold Green
        }
        reset = "\033[0m"
        color = colors.get(category, "")
        
        print(f"{color}[{timestamp}] [{category}] {content}{reset}")
        
        self.cursor.execute('''
            INSERT INTO thoughts (timestamp, category, content)
            VALUES (?, ?, ?)
        ''', (datetime.now().isoformat(), category, content))
        self.conn.commit()

    def get_active_trades(self):
        self.cursor.execute("SELECT * FROM trades WHERE is_active = 1")
        columns = [description[0] for description in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]

    def get_performance_stats(self):
        self.cursor.execute("SELECT COUNT(*), SUM(profit) FROM trades WHERE is_active = 0")
        count, total_profit = self.cursor.fetchone()
        return {"total_trades": count, "net_profit": total_profit or 0.0}
