async function getJson(path, options = {}) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return await resp.json();
}

function toMoney(v) {
  return Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function toNum(v, p = 8) {
  return Number(v).toFixed(p);
}

function renderStatus(status) {
  const signal = status.last_signal || {};
  const account = status.account || {};
  const ts = status.last_tick_ts ? new Date(status.last_tick_ts * 1000).toISOString() : "N/A";

  document.getElementById("meta").textContent = `${status.symbol} ${status.interval} | Last tick: ${ts}`;

  document.getElementById("account").innerHTML = `
    <p>Cash: $${toMoney(account.cash || 0)}</p>
    <p>Asset Qty: ${toNum(account.base_asset_qty || 0)}</p>
    <p>Mark Price: $${toMoney(account.mark_price || 0)}</p>
    <p>Equity: $${toMoney(account.equity || 0)}</p>
  `;

  document.getElementById("signal").innerHTML = `
    <p>Action: <strong>${signal.action || "hold"}</strong></p>
    <p>Reason: ${signal.reason || "N/A"}</p>
    <p>MACD: ${toNum(signal.macd || 0, 6)}</p>
    <p>Signal: ${toNum(signal.signal || 0, 6)}</p>
    <p>Volume Ratio: ${toNum(signal.volume_ratio || 0, 4)}</p>
  `;

  const health = [];
  health.push(`<p>Live Trading Enabled: <strong>${status.live_trading_enabled ? "true" : "false"}</strong></p>`);
  if (status.last_error) {
    health.push(`<p class="bad">Last Error: ${status.last_error}</p>`);
  } else {
    health.push("<p>Last Error: none</p>");
  }
  document.getElementById("health").innerHTML = health.join("");
}

function renderTrades(trades) {
  const el = document.getElementById("trades");
  if (!Array.isArray(trades) || trades.length === 0) {
    el.innerHTML = '<tr><td colspan="5">No trades yet.</td></tr>';
    return;
  }

  el.innerHTML = trades
    .slice()
    .reverse()
    .map((t) => `
      <tr>
        <td>${t.timestamp_iso}</td>
        <td>${t.side}</td>
        <td>${t.symbol}</td>
        <td>${toNum(t.quantity || 0)}</td>
        <td>$${toMoney(t.price || 0)}</td>
      </tr>
    `)
    .join("");
}

async function refresh() {
  const [status, trades] = await Promise.all([getJson("/api/status"), getJson("/api/trades")]);
  renderStatus(status);
  renderTrades(trades);
}

async function runTick() {
  await getJson("/api/tick", { method: "POST" });
  await refresh();
}

document.getElementById("tickBtn").addEventListener("click", runTick);
refresh();
setInterval(refresh, 7000);
