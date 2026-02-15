import time
import requests
import json
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
        self.risk_per_trade_pct = 0.01  # 1% risk per trade
        self.max_trades = 3             # Limit total exposure
        self.current_lot_size = 0.01    # Calculated dynamically
        self.crypto_only_mode = False   # Flag for weekends/closed markets

    def evaluate_account_health(self):
        """Consciously analyze account status and adjust risk."""
        acc = self.executor.get_account_info()
        if not acc: return

        active_count = len(self.executor.get_positions() or [])
        stats = self.memory.get_performance_stats()
        
        # Log snapshot
        acc['open_positions_count'] = active_count
        self.memory.log_account_snapshot(acc)

        system_prompt = "You are Agent Zero's Risk Manager. Analyze account health and set trading limits. Respond in JSON."
        user_prompt = f"""
        Account Status:
        - Balance: {acc['balance']}
        - Equity: {acc['equity']}
        - Margin Level: {(acc['equity']/acc['margin']*100) if acc['margin'] > 0 else 'Infinite'}%
        - Free Margin: {acc['free_margin']}
        - Active Trades: {active_count}
        - Historical Performance: {json.dumps(stats)}

        Task:
        1. Determine if the account is healthy enough for more trades.
        2. Set the maximum number of simultaneous trades allowed (max_trades).
        3. Calculate the ideal lot size for new trades based on equity.
        
        Response Format (JSON only):
        {{
            "is_healthy": bool,
            "max_trades": int,
            "recommended_lot_size": float,
            "health_report": "short explanation"
        }}
        """

        raw_health_decision = self.think(system_prompt, user_prompt)
        try:
            json_str = raw_health_decision.strip('`').replace('json\n', '').strip()
            health = json.loads(json_str)
            
            self.max_trades = health.get('max_trades', 3)
            self.current_lot_size = health.get('recommended_lot_size', 0.01)
            
            msg = f"Health: {'OK' if health['is_healthy'] else 'DANGER'}. " \
                  f"Max Trades: {self.max_trades}, Lot: {self.current_lot_size}. " \
                  f"Reason: {health['health_report']}"
            self.memory.log_thought("HEALTH", msg)
            
            return health['is_healthy']
        except Exception as e:
            self.memory.log_thought("ERROR", f"Health analysis failed: {e}")
            return True

    def think(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the local LLM to get a decision.
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
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
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            self.memory.log_thought("ERROR", f"LLM Call failed: {e}")
            return "ERROR"

    def review_portfolio(self):
        """The 'Consciousness' Loop: Review all open trades."""
        self.evaluate_account_health() # Check health and risk first
        
        self.memory.log_thought("DECISION", "Starting portfolio review cycle...")
        
        active_trades_db = self.memory.get_active_trades()
        mt5_positions = self.executor.get_positions()
        
        if mt5_positions is None:
            self.memory.log_thought("ERROR", "Could not fetch MT5 positions.")
            return

        real_positions = {p.ticket: p for p in mt5_positions}
        
        for trade in active_trades_db:
            ticket = trade['ticket']
            if ticket not in real_positions:
                self.memory.log_thought("REFLECTION", f"Trade {ticket} ({trade['symbol']}) was closed externally.")
                self.memory.update_trade_outcome(ticket, time.strftime('%Y-%m-%dT%H:%M:%S'), "CLOSED", 0.0)
            else:
                self.evaluate_active_trade(trade, real_positions[ticket])

    def evaluate_active_trade(self, trade_db, current_pos):
        """
        Consciously decide whether to keep or kill a trade using AI.
        """
        symbol = trade_db['symbol']
        entry_price = trade_db['entry_price']
        current_price = current_pos.price_current
        profit = current_pos.profit
        rationale = trade_db['rationale']
        sl = trade_db['sl']
        tp = trade_db['tp']
        
        self.memory.log_thought("ANALYSIS", f"Reviewing {symbol} (Ticket {trade_db['ticket']}). Profit: {profit:.2f}")

        system_prompt = "You are Agent Zero, an expert AI trading brain. Your goal is to maximize profit and cut losses early if the trading thesis is invalidated."
        user_prompt = f"""
        Trade Context:
        - Symbol: {symbol}
        - Entry: {entry_price}
        - Current Price: {current_price}
        - P/L: {profit}
        - Stop Loss: {sl}
        - Take Profit: {tp}
        - Original Rationale: {rationale}

        Decision Request:
        Based on the current price and the original rationale, should I CLOSE this trade now or HOLD? 
        If the market structure that justified the trade has broken, suggest CLOSE.
        Respond with exactly 'CLOSE' or 'HOLD' followed by a short one-sentence reason.
        """

        decision_raw = self.think(system_prompt, user_prompt)
        self.memory.log_thought("AI_REFLECTION", f"AI Decision for {symbol}: {decision_raw}")

        if "CLOSE" in decision_raw.upper() and "HOLD" not in decision_raw.upper():
            self.memory.log_thought("DECISION", f"AI requested CLOSE for {symbol}. Executing...")
            success = self.executor.close_position(trade_db['ticket'])
            if success:
                self.memory.update_trade_outcome(trade_db['ticket'], time.strftime('%Y-%m-%dT%H:%M:%S'), "AI_CLOSE", profit)
                self.memory.log_thought("SUCCESS", f"Closed {symbol} via AI decision.")

    def scan_market(self):
        """Scan for new opportunities using AI across multiple symbols."""
        from app_config import SYMBOL_OPTIONS
        
        # enforcement of AI-determined health limits
        active_positions = self.executor.get_positions() or []
        if len(active_positions) >= self.max_trades:
            self.memory.log_thought("HEALTH", f"Scan skipped: At max capacity ({self.max_trades}).")
            return

        status_msg = "Scanning setups..."
        if self.crypto_only_mode:
            status_msg += " [CRYPTO ONLY MODE ACTIVE]"
        self.memory.log_thought("ANALYSIS", f"Scanning setups... Capacity: {len(active_positions)}/{self.max_trades}")
        
        for symbol in SYMBOL_OPTIONS: # Scan all symbols until capacity is reached
            # 0. If in crypto only mode, skip non-crypto pairs
            is_crypto = any(ext in symbol for ext in ["BTC", "ETH", "XRP", "ADA", "SOL", "LTC"])
            if self.crypto_only_mode and not is_crypto:
                continue

            # 1. Skip if we already have an active trade for this symbol
            if any(p.symbol == symbol for p in active_positions):
                continue

            # 2. Check if we analyzed this recently (< 15 mins)
            last_view = self.memory.get_last_analysis(symbol)
            if last_view:
                from datetime import datetime
                time_diff = datetime.now() - datetime.fromisoformat(last_view['timestamp'])
                if time_diff.total_seconds() < 900: # 15 minutes
                    self.memory.log_thought("ANALYSIS", f"Recalling previous view on {symbol} (from {int(time_diff.total_seconds()/60)}m ago): {last_view['last_signal']}")
                    continue

            self.memory.log_thought("ANALYSIS", f"--- Analyzing {symbol} [M30, H1, H4] ---")
            
            # 3. Get Multi-Timeframe Data
            mtf_data = self.executor.get_mtf_data(symbol)
            if not mtf_data:
                continue

            # 4. Ask AI for Analysis
            system_prompt = "You are Agent Zero, an elite algorithmic trader. Analyze data and identify setups. You must return JSON."
            user_prompt = f"""
            Symbol: {symbol}
            Technical Data: {json.dumps(mtf_data, indent=2)}
            Current Risk Setting: {self.current_lot_size} lots.

            Objective:
            Identify high-probability setups. Provide Rationale, Entry, SL, and TP.
            
            Response Format (JSON only):
            {{
                "signal": "BUY" | "SELL" | "WAIT",
                "rationale": "short explanation",
                "entry": float,
                "sl": float,
                "tp": float
            }}
            """

            raw_ai_decision = self.think(system_prompt, user_prompt)
            
            try:
                json_str = raw_ai_decision.strip('`').replace('json\n', '').strip()
                if not json_str: continue
                
                decision = json.loads(json_str)
                
                # Save to Memory for 15-minute persistence
                self.memory.save_analysis(symbol, decision.get('signal'), decision.get('rationale'))
                
                # ALWAYS log the AI's thinking/rationale
                self.memory.log_thought("AI_REFLECTION", f"AI Opinion on {symbol}: {decision.get('rationale', 'No rationale provided.')}")

                if decision.get('signal') in ["BUY", "SELL"]:
                    self.memory.log_thought("DECISION", f"AI Signal Found: {decision['signal']} on {symbol}")
                    
                    # 4. Execute Trade using dynamic lot size
                    result = self.executor.open_trade(
                        symbol=symbol,
                        order_type=decision['signal'],
                        volume=self.current_lot_size, # AI determined size
                        sl=decision['sl'],
                        tp=decision['tp'],
                        comment="AGENT0_AUTO"
                    )
                    
                    if result and result.retcode == 10009: # TRADE_RETCODE_DONE
                        self.memory.log_thought("SUCCESS", f"Opened {decision['signal']} on {symbol} (Ticket: {result.order})")
                        self.memory.log_trade(
                            result.order, symbol, decision['signal'], 
                            decision['entry'], decision['sl'], decision['tp'], 
                            decision['rationale']
                        )
                        if len(self.executor.get_positions() or []) >= self.max_trades:
                            break
                    else:
                        msg = getattr(result, 'comment', 'Unknown error')
                        self.memory.log_thought("ERROR", f"Execution failed for {symbol}: {msg}")
                        if "Market closed" in msg:
                            self.memory.log_thought("HEALTH", "Traditional market closure detected. Activating Crypto-Only Mode.")
                            self.crypto_only_mode = True
                
            except Exception as e:
                self.memory.log_thought("ERROR", f"Failed to parse AI scan decision for {symbol}: {e}")
