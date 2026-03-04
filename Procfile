# Quantix AI Core - Multi-Agent Edition v4.0
# Railway Procfile - Each agent = 1 service
web: python -m backend.quantix_core.api.main
agent_data: python -m backend.quantix_core.agents.data_fetcher
agent_quality: python -m backend.quantix_core.agents.data_quality
agent_bos: python -m backend.quantix_core.agents.bos_detector
agent_fvg: python -m backend.quantix_core.agents.fvg_locator
agent_liquidity: python -m backend.quantix_core.agents.liquidity
agent_confidence: python -m backend.quantix_core.agents.confidence
agent_session: python -m backend.quantix_core.agents.session_filter
agent_validator: python -m backend.quantix_core.agents.price_validator
agent_rr: python -m backend.quantix_core.agents.rr_optimizer
agent_circuit: python -m backend.quantix_core.agents.circuit_breaker
agent_sizing: python -m backend.quantix_core.agents.position_sizing
agent_dispatcher: python -m backend.quantix_core.agents.dispatcher
agent_watcher: python -m backend.quantix_core.agents.watcher
agent_healing: python -m backend.quantix_core.agents.healing
