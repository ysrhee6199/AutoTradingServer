// static/app.js

document.addEventListener('DOMContentLoaded', () => {
    
    // --- Mock Data Injection for Initial UI Viewing ---
    
    // 1. Update Hero Metrics
    const totalBalanceEl = document.getElementById('totalBalance');
    const winRateEl = document.getElementById('winRate');
    const winLoseCountEl = document.getElementById('winLoseCount');
    const dailyPnlEl = document.getElementById('dailyPnl');

    setTimeout(() => {
        totalBalanceEl.textContent = "$ 5,240.50";
        totalBalanceEl.classList.add('flash-update');
        
        winRateEl.textContent = "68.5%";
        winLoseCountEl.textContent = "W: 42 / L: 19";
        
        dailyPnlEl.textContent = "+$ 120.50 (+2.3%)";
        dailyPnlEl.className = 'metric-sub positive flash-update';
    }, 500);

    // 2. Render Mock Active Position
    const currentPositionEl = document.getElementById('currentPosition');
    setTimeout(() => {
        const isLong = true; // Toggle to false to see short style
        const tagClass = isLong ? 'tag-long' : 'tag-short';
        const sideText = isLong ? 'LONG' : 'SHORT';
        const pnlColor = isLong ? 'positive' : 'negative';
        const pnlSign = isLong ? '+' : '-';

        currentPositionEl.innerHTML = `
            <div class="pos-card flash-update">
                <div class="pos-header">
                    <span class="pos-symbol">BTC/USDT</span>
                    <span class="pos-tag ${tagClass}">${sideText} 50x</span>
                </div>
                <div class="pos-data-row">
                    <span class="pos-data-label">Entry Price</span>
                    <span>$ 64,200.00</span>
                </div>
                <div class="pos-data-row">
                    <span class="pos-data-label">Mark Price</span>
                    <span>$ 64,550.00</span>
                </div>
                <div class="pos-data-row">
                    <span class="pos-data-label">Margin (USDT)</span>
                    <span>$ 50.00</span>
                </div>
                <div class="pos-pnl">
                    <span class="pos-data-label">Unrealized PNL</span>
                    <span class="pos-pnl-value ${pnlColor}">${pnlSign}$ 25.50 (51.0%)</span>
                </div>
            </div>
        `;
    }, 800);

    // 3. Render Mock Chart Bars
    const chartContainer = document.querySelector('.chart-container');
    chartContainer.innerHTML = '';
    const heights = [20, 35, 30, 50, 45, 70, 65, 85, 95, 80];
    heights.forEach((h, i) => {
        const bar = document.createElement('div');
        bar.className = 'mock-bar';
        bar.style.height = '0%';
        chartContainer.appendChild(bar);
        
        // Animate up
        setTimeout(() => {
            bar.style.height = `${h}%`;
        }, 1000 + (i * 100));
    });

    // 4. Render Mock History Table
    const historyBody = document.getElementById('historyTableBody');
    const mockHistory = [
        { time: '10:45 AM', sig: 'LONG TAKE PROFIT 1', action: 'Close 50%', status: 'Success' },
        { time: '09:20 AM', sig: 'LONG POSITION', action: 'Market Buy', status: 'Success' },
        { time: '09:19 AM', sig: 'SHORT POSITION', action: 'Close Short', status: 'Success' },
        { time: 'Yesterday', sig: 'SHORT POSITION', action: 'Market Sell', status: 'Success' }
    ];

    setTimeout(() => {
        historyBody.innerHTML = '';
        mockHistory.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.time}</td>
                <td style="color: var(--accent-blue)">${row.sig}</td>
                <td>${row.action}</td>
                <td class="positive">${row.status}</td>
            `;
            historyBody.appendChild(tr);
        });
    }, 1200);

    // TODO: In the next phase, replace timeouts with actual fetch() polling from /api/status
});
