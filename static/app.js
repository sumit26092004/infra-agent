const API_BASE = "";

let token = localStorage.getItem("token");
let currentUser = null;
let healthInterval = null;
let lastRx = null;
let lastTx = null;
let lastTime = null;

// Chart globals
let telemetryChart = null;
let diskChart = null;
const chartMaxDataPoints = 20;

// Terminal globals
let terminal = null;
let termWs = null;

// DOM Elements
const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const userBadge = document.getElementById("user-badge");

const executeForm = document.getElementById("execute-form");
const taskInput = document.getElementById("task-input");
const executionLoader = document.getElementById("execution-loader");
const executionResults = document.getElementById("execution-results");

const analyzeForm = document.getElementById("analyze-form");
const logsInput = document.getElementById("logs-input");
const analyzeLoader = document.getElementById("analyze-loader");
const analyzeResults = document.getElementById("analyze-results");

// Init
async function init() {
    if (token) {
        await fetchUser();
    } else {
        showLogin();
    }
}

// Views
function showLogin() {
    loginView.classList.replace("hidden", "active");
    dashboardView.classList.replace("active", "hidden");
    renderSavedSessions();
}

function getSavedSessions() {
    try { return JSON.parse(localStorage.getItem('savedSessions')) || []; } catch { return []; }
}

function addSavedSession(host, username, token) {
    let sessions = getSavedSessions();
    sessions = sessions.filter(s => s.host !== host || s.username !== username);
    sessions.unshift({ host, username, token });
    if (sessions.length > 3) sessions.pop();
    localStorage.setItem('savedSessions', JSON.stringify(sessions));
}

function renderSavedSessions() {
    const sessions = getSavedSessions();
    const container = document.getElementById("saved-sessions-container");
    const grid = document.getElementById("saved-sessions-grid");
    
    if (!container || !grid) return;
    
    if (sessions.length === 0) {
        container.style.display = "none";
        return;
    }
    
    container.style.display = "block";
    grid.innerHTML = "";
    
    sessions.forEach(s => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn secondary w-full";
        btn.style.textAlign = "left";
        btn.style.display = "flex";
        btn.style.justifyContent = "space-between";
        btn.style.alignItems = "center";
        btn.style.padding = "1rem";
        btn.innerHTML = `
            <span><strong style="color:var(--primary)">${s.username}</strong>@${s.host}</span>
            <span style="font-size:1.2rem; color:var(--text-muted);">&rarr;</span>
        `;
        btn.onclick = async () => {
            token = s.token;
            localStorage.setItem("token", token);
            await fetchUser();
            if (!currentUser) { 
                loginError.textContent = "Session expired. Please enter password.";
                loginError.classList.remove("hidden");
                document.getElementById("server_ip").value = s.host;
                document.getElementById("username").value = s.username;
                document.getElementById("password").focus();
            }
        };
        grid.appendChild(btn);
    });
}

function showDashboard() {
    loginView.classList.replace("active", "hidden");
    dashboardView.classList.replace("hidden", "active");
    userBadge.textContent = `${currentUser.username}@${currentUser.host}`;
    
    // Start polling & setup UI
    initChart();
    initDiskChart();
    if (termWs) termWs.close();
    initTerminal();
    
    fetchHealth();
    if (healthInterval) clearInterval(healthInterval);
    healthInterval = setInterval(fetchHealth, 5000);
}

// Auth
loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append("username", document.getElementById("username").value);
    formData.append("password", document.getElementById("password").value);
    
    const serverIp = document.getElementById("server_ip").value;
    if (serverIp) {
        formData.append("server_ip", serverIp);
    }

    try {
        const res = await fetch(`${API_BASE}/login`, {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            token = data.access_token;
            localStorage.setItem("token", token);
            loginError.classList.add("hidden");
            
            const serverIpValue = document.getElementById("server_ip").value || "127.0.0.1";
            addSavedSession(serverIpValue, document.getElementById("username").value, token);
            
            await fetchUser();
        } else {
            loginError.textContent = data.detail || "Login failed";
            loginError.classList.remove("hidden");
        }
    } catch (err) {
        loginError.textContent = "Network error";
        loginError.classList.remove("hidden");
    }
});

logoutBtn.addEventListener("click", () => {
    token = null;
    currentUser = null;
    localStorage.removeItem("token");
    if (healthInterval) clearInterval(healthInterval);
    showLogin();
});

async function fetchUser() {
    try {
        const res = await fetch(`${API_BASE}/me`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            currentUser = await res.json();
            showDashboard();
        } else {
            throw new Error();
        }
    } catch {
        token = null;
        localStorage.removeItem("token");
        showLogin();
    }
}

let pendingPlan = [];
const confirmationSection = document.getElementById("confirmation-section");
const pendingCommandsDiv = document.getElementById("pending-commands");
const confirmBtn = document.getElementById("confirm-execute-btn");
const cancelBtn = document.getElementById("cancel-execute-btn");

function initDiskChart() {
    const ctx = document.getElementById('disk-chart');
    if (!ctx) return;
    if (diskChart) diskChart.destroy();
    
    diskChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Used', 'Free'],
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#a855f7', 'rgba(255, 255, 255, 0.05)'],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#cbd5e1',
                    padding: 10
                }
            }
        }
    });
}

function initTerminal() {
    const container = document.getElementById('terminal-container');
    if (!container) return;
    container.innerHTML = '';
    
    terminal = new Terminal({
        cursorBlink: true,
        theme: {
            background: '#000000',
            foreground: '#0ea5e9',
            cursor: '#0ea5e9',
            selectionBackground: 'rgba(14, 165, 233, 0.3)'
        },
        fontFamily: 'monospace'
    });
    
    terminal.open(container);
    terminal.writeln('Initializing SSH WebSocket Connection...\r\n');
    
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/terminal?token=${token}`;
    
    termWs = new WebSocket(wsUrl);
    
    const statusBadge = document.getElementById('terminal-status');
    
    termWs.onopen = () => {
        if(statusBadge) {
            statusBadge.textContent = 'Connected';
            statusBadge.style.color = '#10b981';
            statusBadge.style.background = 'rgba(16, 185, 129, 0.2)';
        }
    };
    
    termWs.onmessage = (event) => {
        terminal.write(event.data);
    };
    
    termWs.onclose = () => {
        if(statusBadge) {
            statusBadge.textContent = 'Disconnected';
            statusBadge.style.color = '#ef4444';
            statusBadge.style.background = 'rgba(239, 68, 68, 0.2)';
        }
        terminal.writeln('\r\n[Connection Closed]');
    };
    
    termWs.onerror = () => {
        terminal.writeln('\r\n[WebSocket Error Occurred]');
    };
    
    terminal.onData(data => {
        if (termWs.readyState === WebSocket.OPEN) {
            termWs.send(data);
        }
    });
}

function initChart() {
    const ctx = document.getElementById('health-chart');
    if (!ctx) return;
    if (telemetryChart) telemetryChart.destroy();
    
    Chart.defaults.color = 'rgba(255, 255, 255, 0.7)';
    Chart.defaults.font.family = "'Inter', sans-serif";
    
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(chartMaxDataPoints).fill(''),
            datasets: [
                {
                    label: 'CPU Usage (%)',
                    data: Array(chartMaxDataPoints).fill(0),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 4
                },
                {
                    label: 'RAM Usage (%)',
                    data: Array(chartMaxDataPoints).fill(0),
                    borderColor: '#ec4899',
                    backgroundColor: 'rgba(236, 72, 153, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0
            },
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 10
                }
            }
        }
    });
}

// Health Polling
async function fetchHealth() {
    if (!token) return;
    try {
        const res = await fetch(`${API_BASE}/health`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            const data = await res.json();
            
            document.getElementById("health-cpu").textContent = `${data.cpu}%`;
            document.getElementById("cpu-bar").style.width = `${data.cpu}%`;
            if (data.load_avg) document.getElementById("health-cpu-load").textContent = data.load_avg;
            
            document.getElementById("health-ram").textContent = `${data.ram}%`;
            document.getElementById("ram-bar").style.width = `${data.ram}%`;
            if (data.ram_free !== undefined) {
                const freeGB = (data.ram_free / 1024).toFixed(1);
                const totalGB = (data.ram_total / 1024).toFixed(1);
                document.getElementById("health-ram-free").textContent = freeGB;
                document.getElementById("health-ram-total").textContent = totalGB;
            }
            
            document.getElementById("health-disk").textContent = `${data.disk}%`;
            if (data.disk_avail) document.getElementById("health-disk-avail").textContent = data.disk_avail;
            
            if (diskChart) {
                diskChart.data.datasets[0].data = [data.disk, 100 - data.disk];
                diskChart.update();
            }
            
            if (data.services_running !== undefined) {
                document.getElementById('svc-running').textContent = data.services_running;
                document.getElementById('svc-failed').textContent = data.services_failed;
                
                if (data.services_inactive !== undefined) {
                    document.getElementById('svc-inactive').textContent = data.services_inactive;
                }
                
                const flist = document.getElementById('failed-services-list');
                if (data.services_failed > 0 && data.failed_names) {
                    flist.textContent = "Failed Units: " + data.failed_names.split(',').join(', ');
                } else {
                    flist.textContent = "";
                }
                
                const rlist = document.getElementById('running-services-list');
                if (data.services_running > 0 && data.running_names) {
                    rlist.style.display = "block";
                    rlist.textContent = "Running Units: " + data.running_names.split(',').join(', ');
                } else {
                    rlist.style.display = "none";
                    rlist.textContent = "";
                }
                
                const ilist = document.getElementById('inactive-services-list');
                if (data.services_inactive > 0 && data.inactive_names) {
                    ilist.style.display = "block";
                    ilist.textContent = "Stopped Units: " + data.inactive_names.split(',').join(', ');
                } else {
                    ilist.style.display = "none";
                    ilist.textContent = "";
                }
            }
            
            const now = Date.now();
            if (lastRx !== null && lastTx !== null && lastTime !== null) {
                const timeDiffSec = (now - lastTime) / 1000;
                const rxDiff = data.rx - lastRx;
                const txDiff = data.tx - lastTx;
                
                const rxKbps = (rxDiff / timeDiffSec / 1024).toFixed(1);
                const txKbps = (txDiff / timeDiffSec / 1024).toFixed(1);
                const totalKbps = ((rxDiff + txDiff) / timeDiffSec / 1024).toFixed(1);
                
                document.getElementById("health-net").textContent = `${totalKbps} KB/s`;
                document.getElementById("net-rx").innerHTML = `&darr; ${rxKbps} KB/s`;
                document.getElementById("net-tx").innerHTML = `&uarr; ${txKbps} KB/s`;
            }
            
            lastRx = data.rx;
            lastTx = data.tx;
            lastTime = now;
            
            if (telemetryChart) {
                const nowLabel = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
                
                telemetryChart.data.labels.shift();
                telemetryChart.data.datasets[0].data.shift();
                telemetryChart.data.datasets[1].data.shift();
                
                telemetryChart.data.labels.push(nowLabel);
                telemetryChart.data.datasets[0].data.push(data.cpu);
                telemetryChart.data.datasets[1].data.push(data.ram);
                
                telemetryChart.update('none');
            }
        }
    } catch (err) {
        console.error("Health poll failed");
    }
}

// Generate Task
executeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    executionLoader.classList.remove("hidden");
    executionResults.classList.add("hidden");
    confirmationSection.classList.add("hidden");
    executionResults.innerHTML = "";
    pendingCommandsDiv.innerHTML = "";
    pendingPlan = [];

    try {
        const res = await fetch(`${API_BASE}/plan`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ task: taskInput.value })
        });
        const data = await res.json();
        
        if (!res.ok) {
            let errorText = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            executionResults.innerHTML = `<div class="cmd-error">Error: ${errorText}</div>`;
            executionResults.classList.remove("hidden");
        } else {
            pendingPlan = data.plan;
            if (pendingPlan && pendingPlan.length > 0) {
                if (!data.is_safe) {
                    pendingCommandsDiv.innerHTML += `<div class="cmd-error" style="margin-bottom:1rem;">⚠️ Warning: This plan contains potentially unsafe commands. Execution may be blocked or require careful review.</div>`;
                }
                pendingPlan.forEach(step => {
                    let riskColor = "var(--text-color)";
                    if (step.risk_level === "CRITICAL") riskColor = "#ef4444";
                    else if (step.risk_level === "HIGH") riskColor = "#f97316";
                    else if (step.risk_level === "MEDIUM") riskColor = "#eab308";
                    else if (step.risk_level === "LOW") riskColor = "#22c55e";

                    pendingCommandsDiv.innerHTML += `
                        <div class="cmd-title" style="display:flex; justify-content:space-between; align-items:center;">
                            <span><span style="color:var(--primary); font-weight:bold;">Step ${step.step}:</span> $ ${step.command}</span>
                            <span style="font-size:0.75rem; padding: 0.2rem 0.5rem; background: rgba(255,255,255,0.1); border-radius: 4px; border-left: 3px solid ${riskColor}; color:${riskColor}; font-weight:bold;">${step.risk_level}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#9ca3af; margin-bottom:1rem; margin-top:0.2rem; margin-left: 3.5rem;">
                            <span style="display:block;"><strong>Purpose:</strong> ${step.purpose}</span>
                            ${step.safety_reason !== "Standard safe command" ? `<span style="display:block; color:${riskColor};"><strong>Safety:</strong> ${step.safety_reason}</span>` : ''}
                        </div>
                    `;
                });
                confirmationSection.classList.remove("hidden");
            } else {
                executionResults.innerHTML = `<div class="cmd-error">No plan generated.</div>`;
                executionResults.classList.remove("hidden");
            }
        }
    } catch (err) {
        executionResults.innerHTML = `<div class="cmd-error">Network error</div>`;
        executionResults.classList.remove("hidden");
    } finally {
        executionLoader.classList.add("hidden");
    }
});

// Confirm Execution
confirmBtn.addEventListener("click", async () => {
    confirmationSection.classList.add("hidden");
    executionLoader.classList.remove("hidden");
    executionResults.classList.add("hidden");
    executionResults.innerHTML = "";

    try {
        const res = await fetch(`${API_BASE}/execute`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ plan: pendingPlan })
        });
        const data = await res.json();
        
        if (!res.ok) {
            let errorText = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            executionResults.innerHTML = `<div class="cmd-error">Error: ${errorText}</div>`;
            executionResults.classList.remove("hidden");
        } else {
            if (data.error) {
                 executionResults.innerHTML += `<div class="cmd-error">Agent Error: ${data.error}</div>`;
            }
            if (data.results && data.results.length > 0) {
                data.results.forEach(r => {
                    executionResults.innerHTML += `
                        <div class="cmd-title">$ ${r.command}</div>
                        <div class="cmd-output">${r.result.output || ''}</div>
                        ${r.result.error ? `<div class="cmd-error">${r.result.error}</div>` : ''}
                    `;
                });
            }
        }
    } catch (err) {
        executionResults.innerHTML = `<div class="cmd-error">Network error</div>`;
    } finally {
        executionLoader.classList.add("hidden");
        executionResults.classList.remove("hidden");
    }
});

// Cancel Execution
cancelBtn.addEventListener("click", () => {
    confirmationSection.classList.add("hidden");
    pendingPlan = [];
});

// Analyze Logs
analyzeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    analyzeLoader.classList.remove("hidden");
    analyzeResults.classList.add("hidden");
    analyzeResults.innerHTML = "";

    try {
        const res = await fetch(`${API_BASE}/analyze-logs`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ logs: logsInput.value })
        });
        const data = await res.json();
        
        if (!res.ok) {
            let errorText = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            analyzeResults.innerHTML = `<div class="cmd-error">Error: ${errorText}</div>`;
        } else {
            const diag = data.diagnosis;
            if (diag.error) {
                analyzeResults.innerHTML = `<div class="cmd-error">Agent Error: ${diag.error}</div>`;
            } else {
                let riskColor = "var(--text-color)";
                if (diag.severity === "CRITICAL") riskColor = "#ef4444";
                else if (diag.severity === "HIGH") riskColor = "#f97316";
                else if (diag.severity === "MEDIUM") riskColor = "#eab308";
                else if (diag.severity === "LOW") riskColor = "#22c55e";

                let html = `
                    <div style="margin-bottom: 1rem;">
                        <span style="font-size:0.75rem; padding: 0.2rem 0.5rem; background: rgba(255,255,255,0.1); border-radius: 4px; border-left: 3px solid ${riskColor}; color:${riskColor}; font-weight:bold;">${diag.severity}</span>
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Root Cause:</strong>
                        <div style="color: #9ca3af; margin-top: 0.2rem;">${diag.root_cause}</div>
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Recommended Fix:</strong>
                        <div style="color: #9ca3af; margin-top: 0.2rem;">${diag.recommended_fix}</div>
                    </div>
                `;

                if (diag.commands && diag.commands.length > 0) {
                    html += `<div style="margin-bottom: 1rem;"><strong>Commands to Run:</strong><div class="cmd-output" style="margin-top: 0.5rem;">`;
                    diag.commands.forEach(cmd => {
                        html += `<div>$ ${cmd}</div>`;
                    });
                    html += `</div></div>`;
                    
                    html += `<button id="execute-fix-btn" class="btn secondary w-full">Apply Recommended Fix</button>`;
                }
                
                analyzeResults.innerHTML = html;

                const execFixBtn = document.getElementById("execute-fix-btn");
                if (execFixBtn) {
                    execFixBtn.addEventListener("click", async () => {
                        execFixBtn.disabled = true;
                        execFixBtn.textContent = "Executing...";
                        
                        const plan = diag.commands.map((cmd, i) => ({
                            step: i + 1,
                            command: cmd,
                            purpose: "Apply AI recommended fix",
                            risk_level: diag.severity,
                            safety_reason: "AI generated fix"
                        }));

                        try {
                            const execRes = await fetch(`${API_BASE}/execute`, {
                                method: "POST",
                                headers: {
                                    "Authorization": `Bearer ${token}`,
                                    "Content-Type": "application/json"
                                },
                                body: JSON.stringify({ plan: plan })
                            });
                            const execData = await execRes.json();
                            
                            if (!execRes.ok) {
                                analyzeResults.innerHTML += `<div class="cmd-error" style="margin-top:1rem;">Execution Error: ${execData.detail}</div>`;
                            } else {
                                let resultsHtml = `<div style="margin-top:1rem;"><strong>Execution Results:</strong></div>`;
                                execData.results.forEach(r => {
                                    resultsHtml += `
                                        <div class="cmd-title" style="margin-top:0.5rem;">$ ${r.command}</div>
                                        <div class="cmd-output">${r.result.output || ''}</div>
                                        ${r.result.error ? `<div class="cmd-error">${r.result.error}</div>` : ''}
                                    `;
                                });
                                analyzeResults.innerHTML += resultsHtml;
                            }
                        } catch(err) {
                            analyzeResults.innerHTML += `<div class="cmd-error" style="margin-top:1rem;">Network Error during execution.</div>`;
                        }
                    });
                }
            }
        }
    } catch (err) {
        analyzeResults.innerHTML = `<div class="cmd-error">Network error</div>`;
    } finally {
        analyzeLoader.classList.add("hidden");
        analyzeResults.classList.remove("hidden");
    }
});

// Boot
init();
