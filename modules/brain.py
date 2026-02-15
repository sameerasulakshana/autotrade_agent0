import time
import requests
import json
import xml.etree.ElementTree as ET
from .memory import AgentMemory
from .execution import MT5Executor

class AgentBrain:
    def __init__(self, memory: AgentMemory, executor: MT5Executor):
        self.memory = memory
        self.executor = executor
        self.base_url = "http://localhost:4141/v1" 
        self.model = "gpt-5-mini"
        self.api_key = "none"
        
        # Risk Settings
        self.risk_per_trade_pct = 0.01
        self.max_trades = 3
        self.current_lot_size = 0.01
        self.crypto_only_mode = True 

    def get_crypto_news(self):
        try:
            url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            news_items = []
            for item in root.findall('./channel/item')[:5]:
                title = item.find('title').text
                desc = item.find('description').text
                news_items.append(f"Title: {title}\nSummary: {desc}")
            return "\n\n".join(news_items)
        except Exception as e:
            return f"Could not fetch news: {e}"

    def evaluate_account_health(self):
        acc = self.executor.get_account_info()
        if not acc: return

        active_count = len(self.executor.get_positions() or [])
        stats = self.memory.get_performance_stats()
        
        acc['open_positions_count'] = active_count
        self.memory.log_account_snapshot(acc)

        system_prompt = "You are Agent Zero's Risk Manager. Analyze account health and set trading limits. Respond in JSON."
        user_prompt = f"Account Status: {json.dumps(acc)}\nStats: {json.dumps(stats)}\nTask: Determine if healthy, set max_trades and lot size."

        raw_health_decision = self.think(system_prompt, user_prompt)
        try:
            json_str = raw_health_decision.strip('`').replace('json\n', '').strip()
            health = json.loads(json_str)
            self.max_trades = health.get('max_trades', 3)
            self.current_lot_size = health.get('recommended_lot_size', 0.01)
            msg = f"Health Check: {health['health_report']}"
            self.memory.log_thought("HEALTH", msg)
            return health['is_healthy']
        except:
            return True

    def think(self, system_prompt: str, user_prompt: str) -> str:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.2
            }
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            self.memory.log_thought("ERROR", f"LLM Call failed: {e}")
            return "ERROR"

    def review_portfolio(self):
        self.evaluate_account_health()
        active_trades_db = self.memory.get_active_trades()
        mt5_positions = self.executor.get_positions()
        if mt5_positions is None: return

        real_positions = {p.ticket: p for p in mt5_positions}
        for trade in active_trades_db:
            ticket = trade['ticket']
            if ticket not in real_positions:
                self.memory.update_trade_outcome(ticket, time.strftime('%Y-%m-%dT%H:%M:%S'), "CLOSED", 0.0)
            else:
                self.evaluate_active_trade(trade, real_positions[ticket])

    def evaluate_active_trade(self, trade_db, current_pos):
        symbol = trade_db['symbol']
        ticket = trade_db['ticket']
        
        self.memory.log_thought("ANALYSIS", f"Reviewing {symbol} (Ticket {ticket}). P/L: {current_pos.profit:.2f}")

        system_prompt = """You are Agent Zero, an expert autonomous trader. 
        Your goal is to actively manage trades. You can HOLD, CLOSE, or MODIFY (adjust SL/TP).
        Respond ONLY in JSON format."""
        
        user_prompt = f"""
        Trade Context:
        - Symbol: {symbol}
        - Type: {trade_db['type']}
        - Entry: {trade_db['entry_price']}
        - Current Price: {current_pos.price_current}
        - Current SL: {current_pos.sl}
        - Current TP: {current_pos.tp}
        - Profit: {current_pos.profit}
        - Original Rationale: {trade_db['rationale']}

        Task:
        1. Decide if we should HOLD, CLOSE, or MODIFY the trade.
        2. If MODIFY, specify 'new_sl' or 'new_tp'.
        3. Provide a brief rationale.
        4. If you need market news, set 'search_needed': true.

        Response JSON:
        {{
            "action": "HOLD" | "CLOSE" | "MODIFY",
            "new_sl": float,
            "new_tp": float,
            "rationale": "...",
            "search_needed": bool
        }}
        """

        raw_decision = self.think(system_prompt, user_prompt)
        
        try:
            json_str = raw_decision.strip('`').replace('json\n', '').strip()
            decision = json.loads(json_str)
            
            if decision.get('search_needed'):
                self.memory.log_thought("ANALYSIS", f"AI requested news for {symbol} management...")
                news = self.get_crypto_news()
                user_prompt += f"\n\nLATEST NEWS:\n{news}\nFinal Decision JSON?"
                raw_decision = self.think(system_prompt, user_prompt)
                json_str = raw_decision.strip('`').replace('json\n', '').strip()
                decision = json.loads(json_str)

            self.memory.log_thought("AI_REFLECTION", f"AI Opinion on {symbol}: {decision.get('rationale')}")

            action = decision.get('action')
            if action == "CLOSE":
                if self.executor.close_position(ticket):
                    self.memory.update_trade_outcome(ticket, time.strftime('%Y-%m-%dT%H:%M:%S'), "AI_CLOSE", current_pos.profit)
                    self.memory.log_thought("SUCCESS", f"Closed {symbol} via AI decision.")
            
            elif action == "MODIFY":
                new_sl = decision.get('new_sl', current_pos.sl)
                new_tp = decision.get('new_tp', current_pos.tp)
                if self.executor.modify_position(ticket, new_sl, new_tp):
                    self.memory.log_thought("SUCCESS", f"Modified {symbol}: New SL {new_sl}, New TP {new_tp}")
                    # Update local DB if needed (optional since MT5 is source of truth)
        except Exception as e:
            self.memory.log_thought("ERROR", f"Trade review error: {e}")

    def scan_market(self):
        active_positions = self.executor.get_positions() or []
        if len(active_positions) >= self.max_trades: return

        symbol = "BTCUSD"
        if any(p.symbol == symbol for p in active_positions): return

        last_view = self.memory.get_last_analysis(symbol)
        if last_view:
            from datetime import datetime
            if (datetime.now() - datetime.fromisoformat(last_view['timestamp'])).total_seconds() < 900:
                return

        self.memory.log_thought("ANALYSIS", f"--- Analyzing {symbol} ---")
        mtf_data = self.executor.get_mtf_data(symbol)
        if not mtf_data: return

        system_prompt = "You are Agent Zero. Analyze BTCUSD. Respond ONLY in JSON."
        user_prompt = f"Data: {json.dumps(mtf_data)}. Risk: {self.current_lot_size} lots. JSON: {{ 'signal': 'BUY'|'SELL'|'WAIT', 'rationale': '...', 'entry': f, 'sl': f, 'tp': f, 'search_needed': bool }}"

        raw_ai_decision = self.think(system_prompt, user_prompt)
        
        try:
            json_str = raw_ai_decision.strip('`').replace('json\n', '').strip()
            decision = json.loads(json_str)
            
            if decision.get('search_needed'):
                self.memory.log_thought("ANALYSIS", "AI requested market sentiment search...")
                news = self.get_crypto_news()
                user_prompt += f"\n\nCONTEXT NEWS:\n{news}\nFinal Decision JSON?"
                raw_ai_decision = self.think(system_prompt, user_prompt)
                json_str = raw_ai_decision.strip('`').replace('json\n', '').strip()
                decision = json.loads(json_str)

            self.memory.save_analysis(symbol, decision.get('signal'), decision.get('rationale'))
            self.memory.log_thought("AI_REFLECTION", f"AI Opinion: {decision.get('rationale')}")

            if decision.get('signal') in ["BUY", "SELL"]:
                result = self.executor.open_trade(symbol, decision['signal'], self.current_lot_size, decision['sl'], decision['tp'], "AGENT0_AUTO")
                if result and result.retcode == 10009:
                    self.memory.log_trade(result.order, symbol, decision['signal'], decision['entry'], decision['sl'], decision['tp'], decision['rationale'])
        except Exception as e:
            self.memory.log_thought("ERROR", f"Scan error: {e}")
