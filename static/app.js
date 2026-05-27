const API_BASE = "";

let token = localStorage.getItem("token");
let currentUser = null;

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
}

function showDashboard() {
    loginView.classList.replace("active", "hidden");
    dashboardView.classList.replace("hidden", "active");
    userBadge.textContent = `${currentUser.username}@${currentUser.host}`;
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



// Boot
init();
