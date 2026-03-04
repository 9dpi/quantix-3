/**
 * QUANTIX TRADING SIMULATOR ENGINE
 * Handles virtual trading logic, balance management, and TP/SL execution.
 */

class TradingSimulator {
    constructor() {
        this.initialBalance = 50000;
        this.balance = this.loadState('balance', this.initialBalance);
        this.positions = this.loadState('positions', []);
        this.history = this.loadState('history', []);

        // UI Elements
        this.uiBalance = null;
        this.uiEquity = null;
        this.uiPositions = null;

        this.currentPrice = 0;
        this.loggingEndpoint = ''; // Will be set later for Google Sheets
    }

    init() {
        console.log("🚀 Quantix Simulator Initialized");
        this.updateUI();
        this.startPriceMonitor();
    }

    loadState(key, defaultVal) {
        const saved = localStorage.getItem(`quantix_sim_${key}`);
        return saved ? JSON.parse(saved) : defaultVal;
    }

    saveState() {
        localStorage.setItem('quantix_sim_balance', JSON.stringify(this.balance));
        localStorage.setItem('quantix_sim_positions', JSON.stringify(this.positions));
        localStorage.setItem('quantix_sim_history', JSON.stringify(this.history));
    }

    // --- Core Trading Logic ---

    // Spread config (EURUSD typical 1.5 - 2.0 pips)
    getSPREAD() {
        return 0.00020; // Fixed 2.0 pips for simulation consistency
    }

    updatePrice(midPrice) {
        this.currentPrice = parseFloat(midPrice);
        const halfSpread = this.getSPREAD() / 2;

        // MT5 Logic:
        // BID = Price you SELL at
        // ASK = Price you BUY at
        this.bid = this.currentPrice - halfSpread;
        this.ask = this.currentPrice + halfSpread;

        this.checkPositions();
        this.updateUI();
    }

    openPosition(side, symbol, entryMidPrice, tp, sl, size = 1.0, signalId = null) {
        const halfSpread = this.getSPREAD() / 2;

        // MT5 Rule: BUY @ Ask, SELL @ Bid
        const executionPrice = side === 'BUY'
            ? parseFloat(entryMidPrice) + halfSpread
            : parseFloat(entryMidPrice) - halfSpread;

        const position = {
            id: 'ord_' + Date.now(),
            ticket: Math.floor(Math.random() * 1000000),
            openTime: new Date().toISOString(),
            symbol: symbol,
            side: side.toUpperCase(),
            entryPrice: executionPrice, // Store the actual MT5 execution price
            tp: parseFloat(tp),
            sl: parseFloat(sl),
            size: size,
            signalId: signalId,
            status: 'OPEN',
            pnl: 0
        };

        this.positions.push(position);
        this.saveState();
        this.showNotification(`Order Opened: ${side} ${symbol} @ ${executionPrice.toFixed(5)} (Inc. Spread)`);
        this.updateUI();
    }

    closePosition(id, reason = 'MANUAL') {
        const idx = this.positions.findIndex(p => p.id === id);
        if (idx === -1) return;

        const pos = this.positions[idx];
        pos.closeTime = new Date().toISOString();

        // MT5 Rule: Close BUY @ Bid, Close SELL @ Ask
        pos.closePrice = pos.side === 'BUY' ? this.bid : this.ask;
        pos.reason = reason;

        // Calculate Final P&L
        const multiplier = pos.side === 'BUY' ? 1 : -1;
        const pipValue = 10; // $10 per lot per pip
        const pips = (pos.closePrice - pos.entryPrice) * 10000;
        pos.profit = pips * multiplier * pos.size * pipValue;

        this.balance += pos.profit;
        this.history.unshift(pos);
        this.positions.splice(idx, 1);

        this.saveState();
        this.showNotification(`Order Closed: ${pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}$ (${reason})`);
    }

    checkPositions() {
        if (!this.bid || !this.ask) return;

        [...this.positions].forEach(pos => {
            // Update Floating P&L (Current exit price)
            const exitPrice = pos.side === 'BUY' ? this.bid : this.ask;
            const multiplier = pos.side === 'BUY' ? 1 : -1;
            const pipDiff = (exitPrice - pos.entryPrice) * 10000;
            pos.pnl = pipDiff * multiplier * pos.size * 10;

            // Check TP
            if (pos.tp > 0) {
                // BUY hits TP when Bid rises to TP
                // SELL hits TP when Ask falls to TP
                if ((pos.side === 'BUY' && this.bid >= pos.tp) ||
                    (pos.side === 'SELL' && this.ask <= pos.tp)) {
                    this.closePosition(pos.id, 'TP_HIT');
                }
            }

            // Check SL
            if (pos.sl > 0) {
                // BUY hits SL when Bid falls to SL
                // SELL hits SL when Ask rises to SL
                if ((pos.side === 'BUY' && this.bid <= pos.sl) ||
                    (pos.side === 'SELL' && this.ask >= pos.sl)) {
                    this.closePosition(pos.id, 'SL_HIT');
                }
            }
        });
    }

    // --- UI Methods ---

    updateUI() {
        // Calculate Equity
        const floatingPnL = this.positions.reduce((sum, p) => sum + p.pnl, 0);
        const equity = this.balance + floatingPnL;

        // Update Header Elements if they exist
        const balEl = document.getElementById('sim-balance');
        const eqEl = document.getElementById('sim-equity');
        const pnlEl = document.getElementById('sim-pnl');

        if (balEl) balEl.innerText = `$${this.formatMoney(this.balance)}`;
        if (eqEl) eqEl.innerText = `$${this.formatMoney(equity)}`;

        if (pnlEl) {
            pnlEl.innerText = `${floatingPnL >= 0 ? '+' : ''}$${this.formatMoney(floatingPnL)}`;
            pnlEl.style.color = floatingPnL >= 0 ? '#10b981' : '#ef4444';
        }

        this.renderPositions();
    }

    renderPositions() {
        const container = document.getElementById('sim-positions-list');
        if (!container) return;

        if (this.positions.length === 0) {
            container.innerHTML = '<div style="padding:1rem; text-align:center; color:#94a3b8; font-size:0.8rem;">No active trades running.</div>';
            return;
        }

        container.innerHTML = this.positions.map(p => `
            <div class="trade-card ${p.pnl >= 0 ? 'win' : 'loss'}">
                <div class="trade-header">
                    <span class="trade-symbol">${p.side} ${p.symbol}</span>
                    <span class="trade-pnl ${p.pnl >= 0 ? 'green' : 'red'}">
                        ${p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}$
                    </span>
                </div>
                <div class="trade-info">
                    Entry: ${p.entryPrice} <br>
                    Current: ${this.currentPrice}
                </div>
                <div class="trade-actions">
                    <button onclick="simulator.closePosition('${p.id}', 'MANUAL_CLOSE')" class="close-btn">Close</button>
                </div>
            </div>
        `).join('');
    }

    // --- Helpers ---

    formatMoney(num) {
        return num.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
    }

    showNotification(msg) {
        // Simple toast or alert
        const toast = document.createElement('div');
        toast.className = 'sim-toast';
        toast.innerText = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    startPriceMonitor() {
        // Hook into existing price updates from main index.html logic
        // We will expose a method that index.html calls when price changes
        window.updateSimulatorPrice = (price) => {
            this.updatePrice(price);
        };
    }

    resetAccount() {
        if (confirm("Reset account balance to $50,000?")) {
            this.balance = 50000;
            this.positions = [];
            this.history = [];
            this.saveState();
            this.updateUI();
        }
    }
}

// Initialize Global Instance
const simulator = new TradingSimulator();

// Expose to window for UI interactions
window.simulator = simulator;
