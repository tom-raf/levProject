// Dashboard interactions. Live/Simulated both stream step events over SSE
// (POST + fetch()'s streamed reader, not the native EventSource -- see
// app.py's docstring for why) and are rendered by the same handleEvent()
// path, whether arriving live or replayed from a clicked history tab.

const CHARGE_DURATION_HOURS = 4; // mirrors rules.py -- display-only mirror, not a second source of truth
const SLOTS_PER_WINDOW = CHARGE_DURATION_HOURS * 2;
const CHART_PLOT_LEFT = 40, CHART_PLOT_RIGHT = 860, CHART_PLOT_TOP = 10, CHART_PLOT_BOTTOM = 196;

const runsHistory = [];
let lastProposalEl = null;

// ---- transcript panel ----

function resetTranscript() {
  document.getElementById("transcript-body").innerHTML =
    '<div class="transcript-empty">press LIVE or SIMULATED above to watch the agents reason</div>';
  lastProposalEl = null;
}

function appendTranscriptEntry(role, text, opts = {}) {
  const body = document.getElementById("transcript-body");
  const emptyMsg = body.querySelector(".transcript-empty");
  if (emptyMsg) emptyMsg.remove();

  const row = document.createElement("div");
  row.className = "transcript-entry" + (opts.tone === "red" ? " entry-tone-red" : "");

  const roleEl = document.createElement("div");
  roleEl.className = "transcript-role";
  roleEl.textContent = role;

  const textEl = document.createElement("div");
  textEl.className = "transcript-text";
  textEl.textContent = text;

  row.append(roleEl, textEl);
  body.appendChild(row);
  return row;
}

function markRejected(el) {
  if (el) el.classList.add("entry-rejected");
}

// ---- chart (FIG.1) ----

function forecastAnchor(forecast) {
  return forecast.day ? new Date(forecast.day + "T00:00:00Z") : new Date(forecast.start);
}

function slotIndexForWindow(forecast, windowStartISO) {
  const anchor = forecastAnchor(forecast);
  const offsetMinutes = (new Date(windowStartISO) - anchor) / 60000;
  return Math.round(offsetMinutes / 30);
}

function meanSlice(values, start, count) {
  const slice = values.slice(start, start + count);
  return slice.reduce((a, b) => a + b, 0) / slice.length;
}

function priceCap(prices) {
  const sorted = [...prices].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length * 0.25)];
}

function renderChart(forecast, windowStartISO) {
  const svg = document.getElementById("chart-svg");
  const { prices, carbon } = forecast;
  const n = prices.length;
  if (n === 0) {
    svg.innerHTML = '<text x="450" y="110" text-anchor="middle" class="chart-placeholder">empty horizon</text>';
    return;
  }

  const px = (i) => CHART_PLOT_LEFT + (n > 1 ? i / (n - 1) : 0) * (CHART_PLOT_RIGHT - CHART_PLOT_LEFT);

  const pMin = Math.min(...prices), pMax = Math.max(...prices);
  const pPad = Math.max(1, (pMax - pMin) * 0.15);
  const pLo = pMin - pPad, pHi = pMax + pPad;
  const priceY = (v) => CHART_PLOT_TOP + ((pHi - v) / (pHi - pLo)) * (CHART_PLOT_BOTTOM - CHART_PLOT_TOP);

  const cMin = Math.min(...carbon), cMax = Math.max(...carbon);
  const cPad = Math.max(1, (cMax - cMin) * 0.15);
  const cLo = cMin - cPad, cHi = cMax + cPad;
  const carbonY = (v) => CHART_PLOT_TOP + ((cHi - v) / (cHi - cLo)) * (CHART_PLOT_BOTTOM - CHART_PLOT_TOP);

  const pricePath = prices.map((v, i) => `${px(i).toFixed(1)},${priceY(v).toFixed(1)}`).join(" ");
  const carbonPath = carbon.map((v, i) => `${px(i).toFixed(1)},${carbonY(v).toFixed(1)}`).join(" ");

  const priceTicksSvg = [0, 0.25, 0.5, 0.75, 1].map((f) => pLo + f * (pHi - pLo)).map((v) => `
    <line x1="40" y1="${priceY(v).toFixed(1)}" x2="860" y2="${priceY(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"></line>
    <text x="34" y="${priceY(v).toFixed(1)}" font-size="9" text-anchor="end" fill="var(--ink-soft)" dominant-baseline="middle">${v.toFixed(1)}</text>
  `).join("");

  const carbonTicksSvg = [0, 0.33, 0.66, 1].map((f) => cLo + f * (cHi - cLo)).map((v) => `
    <text x="866" y="${carbonY(v).toFixed(1)}" font-size="9" text-anchor="start" fill="var(--ink-soft)" dominant-baseline="middle">${v.toFixed(0)}</text>
  `).join("");

  const anchor = forecastAnchor(forecast);
  const tickStep = Math.max(1, Math.round(n / 12));
  let hourTicksSvg = "";
  for (let i = 0; i < n; i += tickStep) {
    const t = new Date(anchor.getTime() + i * 30 * 60000);
    const label = t.toISOString().slice(11, 16);
    hourTicksSvg += `
      <line x1="${px(i).toFixed(1)}" y1="10" x2="${px(i).toFixed(1)}" y2="196" stroke="var(--line)" stroke-width="1"></line>
      <text x="${px(i).toFixed(1)}" y="210" font-size="9" text-anchor="middle" fill="var(--ink-soft)">${label}</text>
    `;
  }

  let windowRectSvg = "";
  if (windowStartISO) {
    const idx = Math.max(0, Math.min(n - 1, slotIndexForWindow(forecast, windowStartISO)));
    const slotW = n > 1 ? (CHART_PLOT_RIGHT - CHART_PLOT_LEFT) / (n - 1) : 0;
    const rectX = px(idx);
    const rectW = SLOTS_PER_WINDOW * slotW;
    windowRectSvg = `
      <rect x="${rectX.toFixed(1)}" y="10" width="${rectW.toFixed(1)}" height="186" fill="url(#lc-hatch)" opacity="0.5"></rect>
      <rect x="${rectX.toFixed(1)}" y="10" width="${rectW.toFixed(1)}" height="186" fill="none" stroke="var(--ink)" stroke-width="1.25" stroke-dasharray="4 3"></rect>
      <text x="${(rectX + rectW / 2).toFixed(1)}" y="2" font-size="9.5" text-anchor="middle" fill="var(--ink)" font-weight="600">RECOMMENDED WINDOW</text>
    `;
  }

  svg.innerHTML = `
    <defs>
      <pattern id="lc-hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink-faint)" stroke-width="1"></line>
      </pattern>
    </defs>
    ${priceTicksSvg}${carbonTicksSvg}${hourTicksSvg}${windowRectSvg}
    <polyline points="${carbonPath}" fill="none" stroke="var(--copper)" stroke-width="1.75" stroke-dasharray="5 3"></polyline>
    <polyline points="${pricePath}" fill="none" stroke="var(--blue)" stroke-width="2"></polyline>
  `;
}

// ---- recommendation card ----

function updateRecommendationCard(finalEvent, forecast) {
  const cap = priceCap(forecast.prices);
  const start = new Date(finalEvent.window.start);
  const end = new Date(start.getTime() + CHARGE_DURATION_HOURS * 3600000);
  const fmt = (d) => d.toISOString().slice(11, 16);
  const idx = slotIndexForWindow(forecast, finalEvent.window.start);
  const avgCarbon = meanSlice(forecast.carbon, idx, SLOTS_PER_WINDOW);

  const approved = finalEvent.status === "approved";
  document.getElementById("rec-dot").style.background = approved ? "var(--green)" : "var(--red)";
  document.getElementById("rec-status-label").textContent =
    finalEvent.status.toUpperCase() + (finalEvent.replanned ? " (SENT BACK x1)" : "");
  document.getElementById("rec-window").textContent = fmt(start);
  document.getElementById("rec-duration").textContent = `for ${CHARGE_DURATION_HOURS}h → ends ${fmt(end)}`;
  document.getElementById("rec-price").textContent = finalEvent.window.avg_price.toFixed(2) + "p";
  document.getElementById("rec-carbon").textContent = avgCarbon.toFixed(0) + "g";
  document.getElementById("rec-cap").textContent = cap.toFixed(2) + "p/kWh";
}

// ---- event handling (shared by live streaming and history replay) ----

function handleEvent(ctx, event) {
  switch (event.step) {
    case "forecast":
      ctx.forecast = event;
      renderChart(ctx.forecast, null);
      break;
    case "proposal":
      lastProposalEl = appendTranscriptEntry("ANALYST", event.explanation);
      break;
    case "rule_check":
      if (event.violations && event.violations.length) {
        markRejected(lastProposalEl);
        appendTranscriptEntry("REVIEWER", event.violations.join("; "), { tone: "red" });
      }
      break;
    case "reviewer_verdict":
      if (!event.approved) {
        markRejected(lastProposalEl);
      }
      appendTranscriptEntry("REVIEWER", event.reasoning, { tone: event.approved ? undefined : "red" });
      break;
    case "replan":
      break; // rejection reasoning already rendered above -- no separate line needed
    case "final":
      ctx.final = event;
      updateRecommendationCard(event, ctx.forecast);
      renderChart(ctx.forecast, event.window.start);
      break;
  }
}

// ---- history tabs ----

function addHistoryTab(entry) {
  const container = document.getElementById("history-tabs");
  const emptyMsg = container.querySelector(".history-empty");
  if (emptyMsg) emptyMsg.remove();

  const btn = document.createElement("div");
  btn.className = "history-tab";
  const time = new Date(entry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  btn.textContent = `${entry.type.toUpperCase()} — ${time}`;
  btn.addEventListener("click", () => selectHistoryTab(entry));
  container.appendChild(btn);
  entry.tabEl = btn;

  selectHistoryTab(entry);
}

function selectHistoryTab(entry) {
  document.querySelectorAll(".history-tab").forEach((el) => el.classList.remove("active"));
  entry.tabEl.classList.add("active");

  resetTranscript();
  const ctx = { forecast: null, final: null };
  for (const event of entry.events) handleEvent(ctx, event);

  document.getElementById("tb-mode").textContent = entry.type.toUpperCase();
  document.getElementById("tb-status").textContent = ctx.final ? ctx.final.status.toUpperCase() : "DONE";
}

// ---- running a stream ----

function setButtonsDisabled(disabled) {
  document.getElementById("btn-live").disabled = disabled;
  document.getElementById("btn-simulated").disabled = disabled;
}

async function runStream(type, url) {
  setButtonsDisabled(true);
  resetTranscript();
  document.getElementById("tb-mode").textContent = type.toUpperCase();
  document.getElementById("tb-status").textContent = "RUNNING…";

  const ctx = { forecast: null, final: null, events: [] };

  try {
    const resp = await fetch(url, { method: "POST" });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        if (!chunk.startsWith("data: ")) continue;
        const event = JSON.parse(chunk.slice(6));
        ctx.events.push(event);
        handleEvent(ctx, event);
      }
    }

    document.getElementById("tb-status").textContent = ctx.final ? ctx.final.status.toUpperCase() : "DONE";

    const entry = { id: Date.now(), type, timestamp: new Date().toISOString(), events: ctx.events };
    runsHistory.push(entry);
    addHistoryTab(entry);
  } catch (err) {
    console.error(`${type} run failed:`, err);
    document.getElementById("tb-status").textContent = "ERROR";
  } finally {
    setButtonsDisabled(false);
  }
}

// ---- wiring ----

const transcriptToggle = document.getElementById("transcript-toggle");
const transcriptBody = document.getElementById("transcript-body");
const transcriptLabel = document.getElementById("transcript-toggle-label");

transcriptToggle.addEventListener("click", () => {
  const collapsed = transcriptBody.style.display === "none";
  transcriptBody.style.display = collapsed ? "" : "none";
  transcriptLabel.textContent = collapsed ? "[ − COLLAPSE ]" : "[ + EXPAND ]";
});

document.getElementById("btn-live").addEventListener("click", () => {
  runStream("live", "/run/live");
});

document.getElementById("btn-simulated").addEventListener("click", () => {
  runStream("simulated", "/run/simulated");
});
