const API_BASE = "http://localhost:8000";
const seenCritical = new Set();

let adminToken = localStorage.getItem("aats_admin_token");

if (!adminToken) {
  // Not logged in – send the user to the login page.
  window.location.href = "login.html";
}

const healthBadge = document.getElementById("healthBadge");
const pcStatusGrid = document.getElementById("pcStatusGrid");
const deviceGrid = document.getElementById("deviceGrid");
const eventsBody = document.getElementById("eventsBody");
const alertAudio = document.getElementById("alertAudio");

function severityClass(severity) {
  if (severity === "CRITICAL") return "critical";
  if (severity === "WARNING") return "warning";
  return "ok";
}

function pcStatusClass(pcStatus) {
  if (!pcStatus) return "";
  const s = pcStatus.toLowerCase();
  if (s === "online") return "pc-online";
  if (s === "offline") return "pc-offline";
  return "";
}

function toneFallback() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.05, ctx.currentTime);
    osc.start();
    osc.stop(ctx.currentTime + 0.2);
  } catch (_) {}
}

function playAlertSound() {
  alertAudio.currentTime = 0;
  alertAudio.play().catch(() => toneFallback());
}

async function fetchJson(url) {
  if (!adminToken) {
    adminToken = localStorage.getItem("aats_admin_token");
  }
  if (!adminToken) {
    window.location.href = "login.html";
    throw new Error("Not authenticated");
  }

  const res = await fetch(url, {
    headers: {
      "x-admin-token": adminToken,
    },
  });

  if (res.status === 401) {
    localStorage.removeItem("aats_admin_token");
    window.location.href = "login.html";
    throw new Error("Unauthorized");
  }

  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function renderPcStatus(pcs) {
  pcStatusGrid.innerHTML = "";
  if (!pcs.length) {
    pcStatusGrid.innerHTML = "<p>No heartbeat data yet for this lab.</p>";
    return;
  }

  for (const pc of pcs) {
    const card = document.createElement("div");
    card.className = `card pc-card ${pcStatusClass(pc.pc_status)}`;
    card.innerHTML = `
      <h3>PC ${pc.pc_id}</h3>
      <p><strong>Status:</strong> ${pc.pc_status}</p>
      <p><strong>Last seen:</strong> ${pc.last_seen || "—"}</p>
      <p><strong>Agent:</strong> ${pc.agent_version || "unknown"}</p>
      <p class="meta"><strong>Updated:</strong> ${pc.updated_at}</p>
    `;
    pcStatusGrid.appendChild(card);
  }
}

function renderDevices(devices) {
  deviceGrid.innerHTML = "";
  if (!devices.length) {
    deviceGrid.innerHTML = "<p>No devices found for selected lab.</p>";
    return;
  }

  for (const d of devices) {
    const isPending = d.alert_status === "PENDING";
    const card = document.createElement("div");
    card.className = `card ${severityClass(d.severity)} ${isPending ? "pending" : ""}`;
    const alertLabel = isPending ? "PENDING (debounce)" : d.alert_status;
    const pendingBadge = isPending
      ? `<span class="chip chip-pending">Debouncing for critical...</span>`
      : "";
    card.innerHTML = `
      <h3>${d.device_label || d.device_id}</h3>
      <p><strong>PC:</strong> ${d.pc_id}</p>
      <p><strong>Type:</strong> ${d.device_type}</p>
      <p><strong>Status:</strong> ${d.current_status}</p>
      <p><strong>Severity:</strong> ${d.severity}</p>
      <p><strong>Alert:</strong> ${alertLabel}</p>
      ${d.pending_since ? `<p><strong>Pending since:</strong> ${d.pending_since}</p>` : ""}
      <p class="meta"><strong>Updated:</strong> ${d.updated_at}</p>
      ${pendingBadge}
    `;
    deviceGrid.appendChild(card);
  }
}

function renderEvents(events) {
  eventsBody.innerHTML = "";
  const rows = events.slice(0, 100);
  for (const e of rows) {
    const tr = document.createElement("tr");
    tr.className = severityClass(e.severity);
    tr.innerHTML = `
      <td>${e.received_at || ""}</td>
      <td>${e.lab_id || ""}</td>
      <td>${e.pc_id || ""}</td>
      <td>${e.device_label || e.device_id || ""}</td>
      <td>${e.device_type || ""}</td>
      <td>${e.status || ""}</td>
      <td>${e.severity || ""}</td>
      <td>${e.alert_status || ""}</td>
    `;
    eventsBody.appendChild(tr);

    if (e.severity === "CRITICAL" && e.event_id && !seenCritical.has(e.event_id)) {
      seenCritical.add(e.event_id);
      playAlertSound();
    }
  }
}

async function refresh() {
  const labId = document.getElementById("labFilter").value.trim();
  const pcId = document.getElementById("pcFilter").value.trim();
  const severity = document.getElementById("severityFilter").value;

  if (!labId) return;

  try {
    const health = await fetchJson(`${API_BASE}/health`);
    healthBadge.textContent = `Server: ${health.status}`;
    healthBadge.className = "badge ok";

    const devices = await fetchJson(`${API_BASE}/labs/${encodeURIComponent(labId)}/devices`);
    renderDevices(devices);

    const params = new URLSearchParams({ lab_id: labId, limit: "200" });
    if (pcId) params.set("pc_id", pcId);
    if (severity) params.set("severity", severity);

    const events = await fetchJson(`${API_BASE}/events?${params.toString()}`);
    renderEvents(events);
  } catch (err) {
    healthBadge.textContent = `Server error: ${err.message}`;
    healthBadge.className = "badge critical";
  }
}

document.getElementById("refreshBtn").addEventListener("click", refresh);
setInterval(refresh, 5000);
refresh();
