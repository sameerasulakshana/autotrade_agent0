import time
import sys
import os
from modules.memory import AgentMemory
from modules.execution import MT5Executor
from modules.brain import AgentBrain
from app_config import MT5_HOST, MT5_PORT

def main():
    print("Initializing Agent Zero Core...")
    
    # 1. Initialize Memory
    memory = AgentMemory()
    print("Memory Module: Online")
    
    # 2. Initialize Execution (MT5)
    try:
        executor = MT5Executor(host=MT5_HOST, port=MT5_PORT)
        print("Execution Module: Online (Connected to MT5)")
    except Exception as e:
        print(f"Execution Module Failed: {e}")
        return

    # 3. Initialize Brain
    brain = AgentBrain(memory, executor)
    print("Brain Module: Online")
    
    print("\n" + "="*60)
    print("          AGENT ZERO: DUAL-MODE MONITORING          ")
    print("          (1h Analysis | +/- 1.00 Profit Review)    ")
    print("="*60 + "\n")
    
    last_known_profit = -999999.0
    last_analysis_time = 0
    analysis_interval = 3600 # 1 Hour in seconds
    
    try:
        while True:
            current_time = time.time()
            
            # --- HIGH FREQUENCY TRADE MONITORING ---
            positions = executor.get_positions()
            current_total_profit = sum([p.profit for p in positions]) if positions else 0.0
            
            # Check for fluctuation trigger (+- 1.00)
            fluctuation = abs(current_total_profit - last_known_profit)
            
            if fluctuation >= 1.00:
                print(f"\n--- [PORTFOLIO REVIEW] Fluctuation: {current_total_profit - last_known_profit:+.2f} ---")
                # Review existing trades ONLY
                brain.review_portfolio()
                last_known_profit = current_total_profit
                time.sleep(1) # Brief pause

            # --- SCHEDULED MARKET ANALYSIS (1h) ---
            if (current_time - last_analysis_time) >= analysis_interval:
                print(f"\n--- [SCHEDULED ANALYSIS] Time: {time.strftime('%H:%M:%S')} ---")
                # Scan for NEW trades
                brain.scan_market()
                last_analysis_time = current_time
                # Update baseline profit after scan to avoid immediate double-trigger
                last_known_profit = current_total_profit 

            # Interference Mechanism (Non-blocking check)
            import select
            i, o, e = select.select([sys.stdin], [], [], 0.5) 
            if i:
                line = sys.stdin.readline().strip()
                print("\n" + "!"*20 + " MANUAL INTERVENTION " + "!"*20)
                cmd = input("Command? (close_all / stop / analyze / resume): ").lower()
                if cmd == "close_all":
                    if positions:
                        for p in positions:
                            executor.close_position(p.ticket)
                        print("[SYSTEM] All positions closed.")
                elif cmd == "stop":
                    print("[SYSTEM] Stopping agent.")
                    break
                elif cmd == "analyze":
                    print("[SYSTEM] Forcing analysis...")
                    brain.scan_market()
                    last_analysis_time = time.time()
                elif cmd == "resume":
                    print("[SYSTEM] Resuming...")
                else:
                    print("[SYSTEM] Unknown command.")
            
            # Tiny sleep to reduce CPU load
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Agent Zero...")
        executor.shutdown()

if __name__ == "__main__":
    main()
