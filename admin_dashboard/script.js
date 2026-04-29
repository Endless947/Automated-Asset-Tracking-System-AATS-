/* admin_dashboard/script.js */
const API_BASE = "http://127.0.0.1:8000";
const TOKEN_KEY = "aats_admin_token";
// Client-side staleness threshold (ms). Matches server default `AATS_HEARTBEAT_STALENESS_SEC` (120s).
const HEARTBEAT_STALE_MS = 120 * 1000;

function readTokenFromUrl() {
  const token = new URLSearchParams(window.location.search).get("aats_token");
  return token && token.trim() ? token.trim() : null;
}

function getStoredToken() {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && token.trim()) return token.trim();
  } catch (err) {
    // Ignore storage access issues and continue with URL fallback.
  }
  return null;
}

function setStoredToken(token) {
  if (!token || !token.trim()) return;
  try {
    localStorage.setItem(TOKEN_KEY, token.trim());
  } catch (err) {
    // Ignore storage access issues. URL fallback still works on this session.
  }
}

function clearStoredToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch (err) {
    // Ignore storage access issues.
  }
}

function buildAppUrl(path, extraParams = {}) {
  const url = new URL(path, window.location.href);
  Object.entries(extraParams).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  // file:// origins can isolate storage; keep token in navigation as fallback.
  if (window.location.protocol === "file:" && adminToken) {
    url.searchParams.set("aats_token", adminToken);
  }

  return `${url.pathname}${url.search}`;
}

function propagateAuthTokenInLinks() {
  if (window.location.protocol !== "file:" || !adminToken) return;

  document.querySelectorAll('a[href]').forEach((anchor) => {
    const rawHref = anchor.getAttribute('href');
    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:')) return;

    const url = new URL(rawHref, window.location.href);
    if (!url.pathname.toLowerCase().endsWith('.html')) return;
    url.searchParams.set('aats_token', adminToken);
    anchor.setAttribute('href', `${url.pathname}${url.search}`);
  });
}

let adminToken = getStoredToken() || readTokenFromUrl();
if (adminToken) {
  setStoredToken(adminToken);
}

const isLoginPage = window.location.pathname.endsWith("login.html");

if (!adminToken && !isLoginPage) {
  window.location.href = buildAppUrl("login.html");
}

if (adminToken && isLoginPage) {
  window.location.href = buildAppUrl("index.html");
}

window.addEventListener("DOMContentLoaded", propagateAuthTokenInLinks);

async function fetchJson(url, options = {}) {
  if (!adminToken && !isLoginPage) {
    window.location.href = buildAppUrl("login.html");
    throw new Error("Not authenticated");
  }

  const defaultHeaders = {
    "x-admin-token": adminToken || "",
  };

  const res = await fetch(url, {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  });

  if (res.status === 401 && !isLoginPage) {
    clearStoredToken();
    adminToken = null;
    window.location.href = buildAppUrl("login.html");
    throw new Error("Unauthorized");
  }

  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function getQueryParams() {
  return new URLSearchParams(window.location.search);
}

function severityClass(severity) {
  if (!severity) return 'status-offline';
  if (severity === "CRITICAL") return "status-critical";
  if (severity === "WARNING") return "status-warning";
  if (severity === "OK") return "status-ok";
  return "status-offline";
}

function pcStatusClass(pcStatus) {
  const normalized = (pcStatus || "").toLowerCase();
  if (normalized.includes("online")) return "status-ok";
  if (normalized.includes("offline")) return "status-offline";
  return "status-warning";
}

async function deleteTrackingResource(url, confirmMessage) {
  if (!window.confirm(confirmMessage)) {
    return false;
  }

  await fetchJson(url, { method: "DELETE" });
  return true;
}

async function promptAddLab() {
  const labId = window.prompt('Enter new lab/room id (e.g. lab1):');
  if (!labId) return;
  const trimmed = labId.trim();
  if (!trimmed) return;
  try {
    await fetchJson(`${API_BASE}/labs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lab_id: trimmed }),
    });
    // If we're on the index page, refresh the list in-place.
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
      try { await loadLabs(); } catch (e) { window.location.reload(); }
    } else {
      window.location.href = buildAppUrl('index.html');
    }
  } catch (err) {
    console.error('Create lab failed', err);
    window.alert('Failed to create lab. Ensure API is running and you are authenticated.');
  }
}

// -----------------------------------------------------
// LOGIN PAGE LOGIC
// -----------------------------------------------------
if (isLoginPage) {
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    // Attach listener to form submit event (triggered by button click or Enter key)
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      const username = loginForm.username.value.trim();
      const password = loginForm.password.value.trim();
      const errorDiv = document.getElementById("loginError");

      if (!username || !password) {
        errorDiv.textContent = "Username and password are required.";
        errorDiv.style.display = "block";
        return;
      }

      try {
        const res = await fetchJson(`${API_BASE}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password })
        });
        adminToken = res.token;
        setStoredToken(res.token);
        window.location.href = buildAppUrl("index.html");
      } catch (err) {
        if (err instanceof TypeError || /fetch|network|failed to fetch|connection refused/i.test(err.message)) {
          errorDiv.textContent = "Admin API is not running. Start admin_setup.exe as Administrator, or run the FastAPI server on port 8000.";
        } else {
          errorDiv.textContent = "Invalid credentials.";
        }
        errorDiv.style.display = "block";
      }
    });
  }
}

// -----------------------------------------------------
// INDEX PAGE (LAB SELECTION) LOGIC
// -----------------------------------------------------
if (window.location.pathname.endsWith("index.html") || window.location.pathname === "/") {
  async function loadLabs() {
    const labGrid = document.getElementById("labGrid");
    if (!labGrid) return;

    try {
      const labs = await fetchJson(`${API_BASE}/labs`);
      labGrid.innerHTML = "";
      
      if (!labs || labs.length === 0) {
        labGrid.innerHTML = `<div class="empty-state">No labs or rooms found. Agent devices might be offline.</div>`;
        return;
      }

      labs.forEach(lab => {
        const card = document.createElement("a");
        card.className = "card";
        card.href = buildAppUrl("dashboard.html", { lab: lab.lab_id });
        
        let statusHtml = '';
        if (lab.status_summary) {
           const okCount = lab.status_summary['CONNECTED'] || 0;
           const missingCount = lab.status_summary['MISSING'] || 0;
           statusHtml = `
             <div class="meta-info" style="margin-top: 10px;">
                <span class="badge status-ok">${okCount} Connected devices</span>
                ${missingCount > 0 ? `<span class="badge status-critical" style="margin-top: 4px">${missingCount} Missing</span>` : ''}
             </div>
           `;
        }

        card.innerHTML = `
          <div class="card-header">
            <div class="card-title">${lab.lab_id}</div>
          </div>
          <p class="meta-info">${lab.pc_count} PCs • ${lab.device_count} Peripheral Devices</p>
          ${statusHtml}
        `;
        labGrid.appendChild(card);
      });
    } catch (err) {
      labGrid.innerHTML = `<div class="empty-state">Error loading labs: ${err.message}</div>`;
    }
  }

  window.addEventListener("DOMContentLoaded", loadLabs);
}

// -----------------------------------------------------
// DASHBOARD PAGE LOGIC
// -----------------------------------------------------
if (window.location.pathname.endsWith("dashboard.html")) {
  const params = getQueryParams();
  const labId = params.get("lab");
  
  if (!labId) {
    window.location.href = buildAppUrl("index.html");
  }

  document.getElementById("selectedLabName").textContent = labId;

  async function loadDashboard() {
    try {
      // Clear UI while fetching to avoid showing stale cards
      document.getElementById("totalPcsCount").textContent = "…";
      document.getElementById("totalDevicesCount").textContent = "…";
      document.getElementById("activePcsCount").textContent = "…";
      const grid = document.getElementById("deviceGrid");
      grid.innerHTML = `<div class="loading">Loading…</div>`;
      
      const [pcs, devices] = await Promise.all([
        fetchJson(`${API_BASE}/labs/${encodeURIComponent(labId)}/pcs`),
        fetchJson(`${API_BASE}/labs/${encodeURIComponent(labId)}/devices`)
      ]);

      // Check for new critical devices and play alert if needed
      try {
        await checkAndPlayCriticalAlert(devices);
      } catch (err) {
        console.error('Alert check failed', err);
      }

      // Update Sidebar Counts
      document.getElementById("totalPcsCount").textContent = pcs.length;
      document.getElementById("totalDevicesCount").textContent = devices.length;
      
      const activePcs = pcs.filter(p => (p.pc_status || '').toLowerCase() === 'online').length;
      document.getElementById("activePcsCount").textContent = activePcs;

      const criticalDevices = devices.filter(d => d.severity === 'CRITICAL').length;
      document.getElementById("criticalDevicesCount").textContent = criticalDevices;
      if (criticalDevices > 0) {
        document.getElementById("criticalDevicesCount").parentElement.style.color = 'var(--status-critical-text)';
      }

      grid.innerHTML = "";
      
      if (!pcs.length) {
        grid.innerHTML = `<div class="empty-state">No PCs are currently tracked in this lab.</div>`;
        return;
      }

      const typeFilter = document.getElementById("typeFilter") ? document.getElementById("typeFilter").value : "";
      
      const filteredDevices = devices.filter(d => {
        if (typeFilter && d.device_type !== typeFilter) return false;
        return true;
      });

      const devicesByPc = new Map();
      filteredDevices.forEach((device) => {
        const group = devicesByPc.get(device.pc_id) || [];
        group.push(device);
        devicesByPc.set(device.pc_id, group);
      });

      pcs
        .slice()
        .sort((left, right) => left.pc_id.localeCompare(right.pc_id))
        .forEach((pc) => {
          const pcDevices = (devicesByPc.get(pc.pc_id) || []).slice().sort((left, right) => {
            const typeCompare = (left.device_type || "").localeCompare(right.device_type || "");
            if (typeCompare !== 0) return typeCompare;
            return (left.device_id || "").localeCompare(right.device_id || "");
          });

          const section = document.createElement("section");
          section.className = "pc-section";

          const header = document.createElement("div");
          header.className = "pc-header";
          header.innerHTML = `
            <div>
              <div class="pc-title">PC ${pc.pc_id}</div>
              <div class="pc-meta">${pc.pc_status || 'unknown'}${pc.last_seen ? ` • Last seen ${new Date(pc.last_seen).toLocaleString()}` : ''}</div>
            </div>
            <span class="badge ${pcStatusClass(pc.pc_status)}">${pc.pc_status || 'unknown'}</span>
          `;

          const actions = document.createElement("div");
          actions.className = "pc-actions";

          const removePcButton = document.createElement("button");
          removePcButton.type = "button";
          removePcButton.className = "btn btn-danger";
          removePcButton.textContent = "Remove PC from tracking";
          removePcButton.addEventListener("click", async (event) => {
            event.preventDefault();
            event.stopPropagation();

            try {
              await deleteTrackingResource(
                `${API_BASE}/labs/${encodeURIComponent(labId)}/pcs/${encodeURIComponent(pc.pc_id)}`,
                `Remove PC ${pc.pc_id} and all of its devices from tracking?`
              );
              await loadDashboard();
            } catch (err) {
              console.error(err);
              window.alert(`Failed to remove PC ${pc.pc_id} from tracking.`);
            }
          });

          actions.appendChild(removePcButton);
          header.appendChild(actions);
          section.appendChild(header);

          if (pcDevices.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.textContent = typeFilter
              ? "No devices on this PC match the current filter."
              : "No device states are currently tracked for this PC.";
            section.appendChild(empty);
            grid.appendChild(section);
            return;
          }

          const deviceGrid = document.createElement("div");
          deviceGrid.className = "grid pc-device-grid";

          pcDevices.forEach((device) => {
            const card = document.createElement("div");
            card.className = "card device-card";
            card.tabIndex = 0;

            const updatedAt = Date.parse(device.updated_at);
            const isStale = Number.isFinite(updatedAt) && (Date.now() - updatedAt) > HEARTBEAT_STALE_MS;

            card.innerHTML = `
              <div class="card-header">
                <div class="card-title">${device.device_label || device.device_id}</div>
                <span class="badge ${severityClass(device.severity)}">${device.current_status || 'UNKNOWN'}</span>
                ${isStale ? `<span class="badge status-offline" style="margin-left:8px">STALE</span>` : ''}
              </div>
              <p class="meta-info">Type: <strong>${device.device_type}</strong></p>
              <p class="meta-info">PC Host: ${device.pc_id}</p>
              ${device.alert_status === 'PENDING' ? `<p class="meta-info" style="color:var(--status-warning-text)">Debouncing state...</p>` : ''}
              <div class="card-actions">
                <button type="button" class="btn btn-outline" data-action="view">View details</button>
                <button type="button" class="btn btn-danger" data-action="remove-device">Remove device</button>
              </div>
              <div class="meta-info" style="margin-top:auto">Added/Updated: ${new Date(device.updated_at).toLocaleTimeString()}</div>
            `;

            card.addEventListener("click", (event) => {
              if (event.target && event.target instanceof HTMLElement && event.target.closest("button")) {
                return;
              }
              window.location.href = buildAppUrl("device.html", {
                lab: labId,
                pc: device.pc_id,
                device: device.device_id,
              });
            });

            card.addEventListener("keydown", (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = buildAppUrl("device.html", {
                  lab: labId,
                  pc: device.pc_id,
                  device: device.device_id,
                });
              }
            });

            const viewButton = card.querySelector('[data-action="view"]');
            if (viewButton) {
              viewButton.addEventListener("click", () => {
                window.location.href = buildAppUrl("device.html", {
                  lab: labId,
                  pc: device.pc_id,
                  device: device.device_id,
                });
              });
            }

            const removeDeviceButton = card.querySelector('[data-action="remove-device"]');
            if (removeDeviceButton) {
              removeDeviceButton.addEventListener("click", async (event) => {
                event.preventDefault();
                event.stopPropagation();

                try {
                  await deleteTrackingResource(
                    `${API_BASE}/labs/${encodeURIComponent(labId)}/pcs/${encodeURIComponent(device.pc_id)}/devices/${encodeURIComponent(device.device_id)}`,
                    `Remove device ${device.device_label || device.device_id} from tracking?`
                  );
                  await loadDashboard();
                } catch (err) {
                  console.error(err);
                  window.alert(`Failed to remove device ${device.device_id} from tracking.`);
                }
              });
            }

            deviceGrid.appendChild(card);
          });

          section.appendChild(deviceGrid);
          grid.appendChild(section);
        });

    } catch (err) {
      console.error("Dashboard error", err);
    }
  }

  const typeF = document.getElementById("typeFilter");
  if(typeF) typeF.addEventListener("change", loadDashboard);
  
  // -----------------------------
  // Alert audio + stop control
  // -----------------------------
  let _previousCriticalDevices = new Set();
  let _suppressedCurrentCriticals = new Set();
  let _alertAudioEl = null;
  let _audioContext = null;
  let _fallbackOscillator = null;
  let _alertStopRequested = false;
  let _stopAlertButton = null;

  function ensureStopButton() {
    if (_stopAlertButton) return;
    const container = document.querySelector('.topbar-right') || document.body;
    const btn = document.createElement('button');
    btn.id = 'stopAlertBtn';
    btn.className = 'btn btn-danger';
    btn.textContent = 'Stop Alert';
    btn.style.marginLeft = '12px';
    btn.style.display = 'none';
    btn.addEventListener('click', () => {
      stopAlert();
    });
    _stopAlertButton = btn;
    container.appendChild(btn);
  }

  function showStopButton(show) {
    ensureStopButton();
    _stopAlertButton.style.display = show ? 'inline-block' : 'none';
  }

  async function playAlertSound() {
    _alertStopRequested = false;
    showStopButton(true);

    // Try HTMLAudioElement loop first
    try {
      if (!_alertAudioEl) {
        _alertAudioEl = new Audio('alert.mp3');
        _alertAudioEl.loop = true;
        _alertAudioEl.preload = 'auto';
      }
      const playPromise = _alertAudioEl.play();
      if (playPromise !== undefined) {
        await playPromise;
      }
      return;
    } catch (err) {
      console.warn('HTMLAudio play failed, falling back to WebAudio API', err);
    }

    // Fallback: WebAudio continuous tone
    try {
      if (!_audioContext) {
        _audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (_fallbackOscillator) {
        // already playing
        return;
      }
      const osc = _audioContext.createOscillator();
      const gain = _audioContext.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.2;
      osc.connect(gain);
      gain.connect(_audioContext.destination);
      osc.start();
      _fallbackOscillator = { osc, gain };
    } catch (err) {
      console.error('Fallback audio failed', err);
    }
  }

  function stopAlert() {
    _alertStopRequested = true;
    // If audio element playing, stop it
    try {
      if (_alertAudioEl) {
        _alertAudioEl.pause();
        _alertAudioEl.currentTime = 0;
      }
    } catch (err) {
      console.warn('Stopping HTMLAudio failed', err);
    }

    // Stop fallback oscillator
    try {
      if (_fallbackOscillator) {
        try { _fallbackOscillator.osc.stop(); } catch (e) {}
        try { _fallbackOscillator.osc.disconnect(); } catch (e) {}
        try { _fallbackOscillator.gain.disconnect(); } catch (e) {}
        _fallbackOscillator = null;
      }
    } catch (err) {
      console.warn('Stopping fallback oscillator failed', err);
    }

    // Suppress current critical devices until they clear and reappear
    _suppressedCurrentCriticals = new Set(_previousCriticalDevices);
    showStopButton(false);
  }

  async function checkAndPlayCriticalAlert(devices) {
    const currentCritical = new Set();
    devices.forEach(d => {
      if (d.severity === 'CRITICAL') {
        const key = `${d.pc_id}:${d.device_id}`;
        currentCritical.add(key);
      }
    });

    // Remove suppressed keys that are no longer critical
    for (const key of Array.from(_suppressedCurrentCriticals)) {
      if (!currentCritical.has(key)) {
        _suppressedCurrentCriticals.delete(key);
      }
    }

    let newCriticalFound = false;
    for (const key of currentCritical) {
      if (!_previousCriticalDevices.has(key) && !_suppressedCurrentCriticals.has(key)) {
        newCriticalFound = true;
        break;
      }
    }

    // Update previous snapshot
    _previousCriticalDevices = currentCritical;

    if (newCriticalFound && !_alertStopRequested) {
      await playAlertSound();
    }
  }

  // Initialize stop button element now (hidden until needed)
  ensureStopButton();

  window.addEventListener("DOMContentLoaded", () => {
    loadDashboard();
    setInterval(loadDashboard, 5000); 
  });
}

// -----------------------------------------------------
// DEVICE DETAIL PAGE LOGIC
// -----------------------------------------------------
if (window.location.pathname.endsWith("device.html")) {
  const params = getQueryParams();
  const labId = params.get("lab");
  const pcId = params.get("pc");
  const deviceId = params.get("device");

  if (!labId || !deviceId) {
    window.location.href = buildAppUrl("index.html");
  }

  document.getElementById("deviceBreadcrumb").textContent = `${labId} / ${deviceId}`;
  const removeDeviceButton = document.getElementById("removeDeviceBtn");

  if (removeDeviceButton) {
    removeDeviceButton.addEventListener("click", async () => {
      try {
        await deleteTrackingResource(
          `${API_BASE}/labs/${encodeURIComponent(labId)}/pcs/${encodeURIComponent(pcId)}/devices/${encodeURIComponent(deviceId)}`,
          `Remove device ${deviceId} from tracking?`
        );
        window.location.href = buildAppUrl("dashboard.html", { lab: labId });
      } catch (err) {
        console.error(err);
        window.alert(`Failed to remove device ${deviceId} from tracking.`);
      }
    });
  }

  function determineIcon(type) {
    if(type === 'bluetooth') return 'Bluetooth';
    if(type === 'usb') return 'USB';
    return type;
  }

  async function loadDevice() {
    try {
      // There's no single device endpoint, so get all for lab, then filter.
      const devices = await fetchJson(`${API_BASE}/labs/${encodeURIComponent(labId)}/devices`);
      const device = devices.find(d => d.device_id === deviceId && d.pc_id === pcId);

      if (!device) {
        document.getElementById("deviceInfo").innerHTML = `<div class="empty-state">Device not found in current states. It may have been removed.</div>`;
        return;
      }

      document.getElementById("deviceNameTitle").textContent = device.device_label || device.device_id;
      document.getElementById("deviceIcon").textContent = determineIcon(device.device_type).substring(0, 1).toUpperCase();
      document.getElementById("deviceStatusBadge").className = `badge ${severityClass(device.severity)}`;
      document.getElementById("deviceStatusBadge").textContent = device.current_status;

      // Populate Info Grid
      document.getElementById("infoId").textContent = device.device_id;
      document.getElementById("infoType").textContent = device.device_type;
      document.getElementById("infoHost").textContent = device.pc_id;
      document.getElementById("infoRssi").textContent = device.rssi != null ? `${device.rssi} dBm` : 'N/A';
      document.getElementById("infoUpdated").textContent = new Date(device.updated_at).toLocaleString();
      document.getElementById("infoAlert").textContent = device.alert_status;
      // Stale indicator for device detail
      const updatedAt = Date.parse(device.updated_at);
      const detailStale = Number.isFinite(updatedAt) && (Date.now() - updatedAt) > HEARTBEAT_STALE_MS;
      const staleEl = document.getElementById("infoStale");
      if (staleEl) {
        staleEl.textContent = detailStale ? 'Stale (no recent heartbeat)' : '';
      }

      // Load Recent Events specific to this device
      const queryParams = new URLSearchParams({
         lab_id: labId,
         pc_id: pcId,
         device_id: deviceId,
         limit: "15"
      });
      const events = await fetchJson(`${API_BASE}/events?${queryParams.toString()}`);
      
      const tbody = document.getElementById("deviceEventsBody");
      tbody.innerHTML = "";

      if(!events || events.length === 0){
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No recent events.</td></tr>`;
      } else {
        events.forEach(e => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${new Date(e.received_at).toLocaleString()}</td>
            <td><span class="badge ${severityClass(e.severity)}">${e.status}</span></td>
            <td>${e.alert_status}</td>
            <td style="font-family:monospace; font-size: 0.75rem">${e.details_json || '{}'}</td>
          `;
          tbody.appendChild(tr);
        });
      }

    } catch (err) {
      console.error(err);
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    loadDevice();
    setInterval(loadDevice, 5000); 
  });
}
