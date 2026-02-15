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
    print("          AGENT ZERO: DYNAMIC PROFIT MONITORING          ")
    print("="*60 + "\n")
    
    last_known_profit = -999999.0
    cycle_count = 1
    
    try:
        while True:
            # High-frequency check of profit
            positions = executor.get_positions()
            current_total_profit = sum([p.profit for p in positions]) if positions else 0.0
            
            # Check for fluctuation trigger (+- 0.20)
            fluctuation = abs(current_total_profit - last_known_profit)
            
            if fluctuation >= 0.20:
                print(f"\n--- [THOUGHT CYCLE #{cycle_count}] Fluctuation: {fluctuation:+.2f} ---")
                print(f"[SYSTEM] Total Profit: {current_total_profit:.2f} (Triggered Analysis)")
                
                # 1. Review Portfolio (Consciousness)
                brain.review_portfolio()
                
                # 2. Scan Market (Opportunity)
                brain.scan_market() 
                
                last_known_profit = current_total_profit
                cycle_count += 1
                
                # Small gap after a full cycle to prevent runaway loops if profit is jittery
                time.sleep(2)
            
            # Interference Mechanism (Non-blocking check)
            import select
            i, o, e = select.select([sys.stdin], [], [], 0.5) # Check every 0.5s
            if i:
                line = sys.stdin.readline().strip()
                print("\n" + "!"*20 + " MANUAL INTERVENTION " + "!"*20)
                cmd = input("Command? (close_all / stop / resume): ").lower()
                if cmd == "close_all":
                    if positions:
                        for p in positions:
                            executor.close_position(p.ticket)
                        print("[SYSTEM] All positions closed.")
                elif cmd == "stop":
                    print("[SYSTEM] Stopping agent.")
                    break
                elif cmd == "resume":
                    print("[SYSTEM] Resuming...")
                else:
                    print("[SYSTEM] Unknown command.")
            
            # Tiny sleep to reduce CPU load while monitoring
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Agent Zero...")
        executor.shutdown()

if __name__ == "__main__":
    main()
