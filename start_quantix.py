"""
Quantix Multi-Agent System Orchestrator (Local Mode)
=====================================================
Starts all 15 agents and the Web API in a single process.
Ideal for local operation where the PC stays on for the signal lifecycle.
"""

import os
import sys
import time
import signal
import threading
import subprocess
from loguru import logger

# Set PYTHONPATH to current directory
os.environ["PYTHONPATH"] = os.getcwd()

# List of all agent modules to start
AGENTS = [
    "backend.quantix_core.agents.data_fetcher",
    "backend.quantix_core.agents.data_quality",
    "backend.quantix_core.agents.bos_detector",
    "backend.quantix_core.agents.fvg_locator",
    "backend.quantix_core.agents.liquidity",
    "backend.quantix_core.agents.confidence",
    "backend.quantix_core.agents.session_filter",
    "backend.quantix_core.agents.price_validator",
    "backend.quantix_core.agents.rr_optimizer",
    "backend.quantix_core.agents.circuit_breaker",
    "backend.quantix_core.agents.position_sizing",
    "backend.quantix_core.agents.dispatcher",
    "backend.quantix_core.agents.watcher",
    "backend.quantix_core.agents.healing",
]

processes = []

def signal_handler(sig, frame):
    logger.warning("🛑 Shutting down all agents...")
    for p in processes:
        try:
            p.terminate()
        except:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def start_agent(module):
    """Starts an agent in a background process."""
    logger.info(f"🚀 Starting Agent: {module}")
    cmd = [sys.executable, "-m", module]
    # Use stdout/stderr redirection to loguru if needed, or just let them print to terminal
    p = subprocess.Popen(cmd)
    return p

def run_main():
    print("="*60)
    print("🌌 QUANTIX MULTI-AGENT V4.0 - LOCAL ORCHESTRATOR")
    print("="*60)
    print("PC Lifecycle Strategy: ON for signal life (max 120m)")
    print("-" * 60)
    
    # 1. Start Redis check (optional if using local redis)
    # logger.info("Checking Redis status...")
    
    # 2. Start all Agents
    for agent in AGENTS:
        p = start_agent(agent)
        processes.append(p)
        time.sleep(0.5) # Prevent CPU spike on start
    
    # 3. Start Web API (Blocking or background)
    logger.info("🌐 Starting Web API Dashboard...")
    try:
        # Start API in a way that captures Ctrl+C
        cmd_api = [sys.executable, "-m", "backend.quantix_core.api.main"]
        api_proc = subprocess.Popen(cmd_api)
        processes.append(api_proc)
        
        logger.success("✨ ALL SYSTEMS OPERATIONAL! Press Ctrl+C to stop.")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    run_main()
