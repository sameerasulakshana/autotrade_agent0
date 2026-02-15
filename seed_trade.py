from modules.memory import AgentMemory
import sys
import os

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def seed():
    memory = AgentMemory()
    
    # Details of the trade we just took
    ticket = 4228079793
    symbol = "BTCUSD"
    order_type = "BUY"
    price = 69350.0
    sl = 67800.0
    tp = 72000.0
    rationale = "1H Bullish Breakout above 69k with confluence from 4H Higher Low structure. Market sentiment is Extreme Fear (accumulation phase)."

    print(f"Seeding trade {ticket} into Agent Zero Memory...")
    memory.log_trade(ticket, symbol, order_type, price, sl, tp, rationale)
    print("Done. Agent Zero is now conscious of this trade.")

if __name__ == "__main__":
    seed()
