from pymt5linux import MetaTrader5
import sys
import os

# Ensure we can import from parent if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class MT5Executor:
    def __init__(self, host='0.0.0.0', port=8001):
        self.mt5 = MetaTrader5(host=host, port=port)
        if not self.mt5.initialize():
            raise ConnectionError("Failed to connect to MT5")

    def get_market_data(self, symbol, timeframe, count=100):
        rates = self.mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            return None
        return rates

    def get_positions(self):
        return self.mt5.positions_get()

    def close_position(self, ticket):
        position = self.mt5.positions_get(ticket=ticket)
        if not position:
            return False
        
        pos = position[0]
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": self.mt5.ORDER_TYPE_SELL if pos.type == 0 else self.mt5.ORDER_TYPE_BUY,
            "price": self.mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else self.mt5.symbol_info_tick(pos.symbol).ask,
            "magic": 123456,
            "comment": "AgentZero Auto-Close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        result = self.mt5.order_send(request)
        return result.retcode == self.mt5.TRADE_RETCODE_DONE

    def modify_position(self, ticket, sl, tp):
        """Update Stop Loss and Take Profit for an open position."""
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": float(sl),
            "tp": float(tp)
        }
        result = self.mt5.order_send(request)
        return result.retcode == self.mt5.TRADE_RETCODE_DONE

    def open_trade(self, symbol, order_type, volume, sl, tp, comment):
        price = self.mt5.symbol_info_tick(symbol).ask if order_type == "BUY" else self.mt5.symbol_info_tick(symbol).bid
        type_op = self.mt5.ORDER_TYPE_BUY if order_type == "BUY" else self.mt5.ORDER_TYPE_SELL
        
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": type_op,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "magic": 123456,
            "comment": comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        result = self.mt5.order_send(request)
        return result

    def get_account_info(self):
        acc = self.mt5.account_info()
        if acc is None: return None
        return {
            "balance": acc.balance,
            "equity": acc.equity,
            "margin": acc.margin,
            "free_margin": acc.margin_free,
            "currency": acc.currency
        }

    def get_mtf_data(self, symbol: str) -> dict:
        """Fetch H4, H1, and M30 data for analysis."""
        data = {}
        # Mapping timeframe strings to MT5 constants
        tf_map = {
            "H4": self.mt5.TIMEFRAME_H4,
            "H1": self.mt5.TIMEFRAME_H1,
            "M30": self.mt5.TIMEFRAME_M30
        }
        
        for label, tf in tf_map.items():
            rates = self.mt5.copy_rates_from_pos(symbol, tf, 0, 50)
            if rates is not None:
                # Convert to standard Python types for JSON serialization
                data[label] = [
                    {
                        "time": int(r[0]), 
                        "open": float(r[1]), 
                        "high": float(r[2]), 
                        "low": float(r[3]), 
                        "close": float(r[4])
                    } 
                    for r in rates[-10:] 
                ]
        return data

    def shutdown(self):
        self.mt5.shutdown()
