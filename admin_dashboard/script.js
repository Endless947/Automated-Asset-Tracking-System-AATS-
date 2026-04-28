/* admin_dashboard/script.js */
const API_BASE = "http://127.0.0.1:8000";
// Client-side staleness threshold (ms). Matches server default `AATS_HEARTBEAT_STALENESS_SEC` (120s).
const HEARTBEAT_STALE_MS = 120 * 1000;

let adminToken = localStorage.getItem("aats_admin_token");
const isLoginPage = window.location.pathname.endsWith("login.html");

if (!adminToken && !isLoginPage) {
  window.location.href = "login.html";
}

async function fetchJson(url, options = {}) {
  if (!adminToken && !isLoginPage) {
    window.location.href = "login.html";
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
    localStorage.removeItem("aats_admin_token");
    window.location.href = "login.html";
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

// -----------------------------------------------------
// LOGIN PAGE LOGIC
// -----------------------------------------------------
if (isLoginPage) {
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = loginForm.username.value;
      const password = loginForm.password.value;
      const errorDiv = document.getElementById("loginError");

      try {
        const res = await fetchJson(`${API_BASE}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password })
        });
        localStorage.setItem("aats_admin_token", res.token);
        window.location.href = "index.html";
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
        card.href = `dashboard.html?lab=${encodeURIComponent(lab.lab_id)}`;
        
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
    window.location.href = "index.html";
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

      // Render Devices Grid
      const grid = document.getElementById("deviceGrid");
      grid.innerHTML = "";
      
      if (!devices.length) {
        grid.innerHTML = `<div class="empty-state">No devices found in this lab.</div>`;
        return;
      }

      const typeFilter = document.getElementById("typeFilter") ? document.getElementById("typeFilter").value : "";
      
      const filteredDevices = devices.filter(d => {
        if (typeFilter && d.device_type !== typeFilter) return false;
        return true;
      });

      filteredDevices.forEach(d => {
        const card = document.createElement("a");
        card.className = "card";
        card.href = `device.html?lab=${encodeURIComponent(labId)}&pc=${encodeURIComponent(d.pc_id)}&device=${encodeURIComponent(d.device_id)}`;
        
        // Determine if this device state is stale (server time vs client time may differ)
        const updatedAt = Date.parse(d.updated_at);
        const isStale = Number.isFinite(updatedAt) && (Date.now() - updatedAt) > HEARTBEAT_STALE_MS;

        card.innerHTML = `
          <div class="card-header">
            <div class="card-title">${d.device_label || d.device_id}</div>
            <span class="badge ${severityClass(d.severity)}">${d.current_status || 'UNKNOWN'}</span>
            ${isStale ? `<span class="badge status-offline" style="margin-left:8px">STALE</span>` : ''}
          </div>
          <p class="meta-info">Type: <strong>${d.device_type}</strong></p>
          <p class="meta-info">PC Host: ${d.pc_id}</p>
          ${d.alert_status === 'PENDING' ? `<p class="meta-info" style="color:var(--status-warning-text)">Debouncing state...</p>` : ''}
          <div class="meta-info" style="margin-top:auto">Added/Updated: ${new Date(d.updated_at).toLocaleTimeString()}</div>
        `;
        grid.appendChild(card);
      });

    } catch (err) {
      console.error("Dashboard error", err);
    }
  }

  const typeF = document.getElementById("typeFilter");
  if(typeF) typeF.addEventListener("change", loadDashboard);
  
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
    window.location.href = "index.html";
  }

  document.getElementById("deviceBreadcrumb").textContent = `${labId} / ${deviceId}`;

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
