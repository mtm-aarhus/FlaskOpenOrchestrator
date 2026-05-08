// Statistics page — KPIs, breakdown chart, settings persisted in Constants.

let breakdownChart = null;
let timeseriesChart = null;
let cachedAvailableQueues = [];
let cachedAvailableProcesses = [];
let cachedConfiguredQueues = new Set();
let cachedConfiguredProcesses = new Set();

const QUEUE_FIELDS = ["minutes_per_item", "clicks_per_item"];
const PROCESS_FIELDS = ["minutes_per_run", "clicks_per_run"];

function fmtNumber(n) {
    return Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
}

// ─── Settings ────────────────────────────────────────────────────────────────

function buildSettingsRow(item, kind, fields) {
    const tr = document.createElement("tr");
    tr.dataset.kind = kind;
    tr.dataset.name = item.name;
    const safeName = escapeHtml(item.name);
    const cells = [`<td><code>${safeName}</code></td>`];
    fields.forEach(f => {
        cells.push(`
            <td>
                <input type="number" class="form-control form-control-sm settings-input"
                       min="0" step="0.1" data-field="${f}" value="${item[f] || 0}"
                       oninput="markRowDirty(this)">
            </td>`);
    });
    cells.push(`
        <td class="text-end">
            <button class="btn btn-sm btn-primary save-row-btn" onclick="saveRow(this)" disabled>
                <i class="bi bi-save"></i> Save
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteRow(this)" title="Remove this entry">
                <i class="bi bi-trash"></i>
            </button>
            <span class="row-status ms-1 small" style="display:none;"></span>
        </td>`);
    tr.innerHTML = cells.join("");
    return tr;
}

function refreshDatalists() {
    const qList = document.getElementById("queue-picker-options");
    const pList = document.getElementById("process-picker-options");
    qList.innerHTML = cachedAvailableQueues
        .filter(n => !cachedConfiguredQueues.has(n))
        .map(n => `<option value="${escapeHtml(n)}"></option>`).join("");
    pList.innerHTML = cachedAvailableProcesses
        .filter(n => !cachedConfiguredProcesses.has(n))
        .map(n => `<option value="${escapeHtml(n)}"></option>`).join("");
}

function emptyRow(colspan, text) {
    return `<tr><td colspan="${colspan}" class="text-muted text-center py-3">${text}</td></tr>`;
}

async function loadSettings() {
    const res = await fetch("/stats/settings");
    const data = await res.json();

    document.getElementById("hourly-wage").value = data.hourly_wage_dkk;
    markWageClean();

    cachedAvailableQueues = data.available_queues || [];
    cachedAvailableProcesses = data.available_processes || [];
    cachedConfiguredQueues = new Set(data.queues.map(q => q.name));
    cachedConfiguredProcesses = new Set(data.processes.map(p => p.name));

    const qBody = document.querySelector("#queue-settings-table tbody");
    qBody.innerHTML = "";
    data.queues.forEach(q => qBody.appendChild(buildSettingsRow(q, "queue", QUEUE_FIELDS)));
    if (!data.queues.length) qBody.innerHTML = emptyRow(4, "No queues configured. Add one above.");

    const pBody = document.querySelector("#process-settings-table tbody");
    pBody.innerHTML = "";
    data.processes.forEach(p => pBody.appendChild(buildSettingsRow(p, "process", PROCESS_FIELDS)));
    if (!data.processes.length) pBody.innerHTML = emptyRow(4, "No processes configured. Add one above.");

    refreshDatalists();
}

function markRowDirty(input) {
    const tr = input.closest("tr");
    const btn = tr.querySelector(".save-row-btn");
    if (btn) {
        btn.disabled = false;
        btn.classList.remove("btn-success");
        btn.classList.add("btn-primary");
    }
    const status = tr.querySelector(".row-status");
    if (status) status.style.display = "none";
}

function showRowStatus(tr, message, ok = true) {
    const status = tr.querySelector(".row-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("text-success", ok);
    status.classList.toggle("text-danger", !ok);
    status.style.display = "";
    setTimeout(() => { status.style.display = "none"; }, 2500);
}

async function saveRow(btn) {
    const tr = btn.closest("tr");
    const kind = tr.dataset.kind;
    const name = tr.dataset.name;
    const fields = {};
    tr.querySelectorAll(".settings-input").forEach(input => {
        fields[input.dataset.field] = parseFloat(input.value) || 0;
    });

    btn.disabled = true;
    const res = await fetch("/stats/settings/item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, name, fields }),
    });
    const data = await res.json();
    if (!data.success) {
        showRowStatus(tr, data.error || "Failed", false);
        btn.disabled = false;
        return;
    }
    btn.classList.remove("btn-primary");
    btn.classList.add("btn-success");
    showRowStatus(tr, "Saved");
    refreshSummary();
}

async function deleteRow(btn) {
    const tr = btn.closest("tr");
    const kind = tr.dataset.kind;
    const name = tr.dataset.name;
    if (!confirm(`Remove savings settings for "${name}"?`)) return;

    const res = await fetch("/stats/settings/item", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, name }),
    });
    const data = await res.json();
    if (!data.success) {
        window.showToast("Delete failed: " + (data.error || "unknown"), "error");
        return;
    }
    if (kind === "queue") cachedConfiguredQueues.delete(name);
    else                  cachedConfiguredProcesses.delete(name);
    tr.remove();

    const tbody = document.querySelector(`#${kind}-settings-table tbody`);
    if (!tbody.children.length) {
        tbody.innerHTML = emptyRow(4, `No ${kind}s configured. Add one above.`);
    }
    refreshDatalists();
    refreshSummary();
}

function addQueueFromPicker() {
    addPickedItem("queue", "queue-picker", cachedAvailableQueues, cachedConfiguredQueues, QUEUE_FIELDS);
}
function addProcessFromPicker() {
    addPickedItem("process", "process-picker", cachedAvailableProcesses, cachedConfiguredProcesses, PROCESS_FIELDS);
}

function addPickedItem(kind, pickerId, available, configured, fields) {
    const input = document.getElementById(pickerId);
    const name = (input.value || "").trim();
    if (!name) {
        input.focus();
        return;
    }
    if (configured.has(name)) {
        window.showToast("Already configured.", "warning");
        return;
    }
    if (!available.includes(name)) {
        if (!confirm(`"${name}" isn't in the discovered list. Add it anyway?`)) return;
    }
    configured.add(name);
    const tbody = document.querySelector(`#${kind}-settings-table tbody`);
    if (tbody.querySelector("td[colspan]")) tbody.innerHTML = "";  // clear empty-state row
    const blank = { name };
    fields.forEach(f => blank[f] = 0);
    tbody.appendChild(buildSettingsRow(blank, kind, fields));
    input.value = "";
    refreshDatalists();
    // Highlight the new row's first input so the user can start typing.
    const newRow = tbody.lastElementChild;
    const firstInput = newRow.querySelector(".settings-input");
    if (firstInput) firstInput.focus();
    markRowDirty(firstInput);  // enable save button immediately
}

// ─── Hourly wage (saved independently) ──────────────────────────────────────

function markWageDirty() {
    const btn = document.getElementById("save-wage-btn");
    btn.disabled = false;
    document.getElementById("save-wage-status").style.display = "none";
}
function markWageClean() {
    document.getElementById("save-wage-btn").disabled = true;
}

async function saveWage() {
    const wage = parseFloat(document.getElementById("hourly-wage").value) || 0;
    const res = await fetch("/stats/settings/wage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hourly_wage_dkk: wage }),
    });
    const data = await res.json();
    if (!data.success) {
        window.showToast("Save failed: " + (data.error || "unknown"), "error");
        return;
    }
    window.showToast("Hourly wage saved", "success");
    markWageClean();
    const status = document.getElementById("save-wage-status");
    status.style.display = "";
    setTimeout(() => { status.style.display = "none"; }, 2000);
    refreshSummary();
}

// ─── Summary (KPI cards + chart + breakdown table) ─────────────────────────

async function refreshTimeseries(days) {
    const res = await fetch(`/stats/timeseries?days=${days}`);
    const data = await res.json();

    const label = document.getElementById("timeseries-bucket-label");
    if (label) label.textContent = data.bucket === "week" ? "weekly buckets" : "daily buckets";

    const ctx = document.getElementById("timeseries-chart").getContext("2d");
    if (timeseriesChart) timeseriesChart.destroy();
    timeseriesChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.labels,
            datasets: [{
                label: "Hours saved",
                data: data.hours_saved,
                borderColor: "rgba(13, 110, 253, 1)",
                backgroundColor: "rgba(13, 110, 253, 0.15)",
                fill: true,
                tension: 0.25,
                pointRadius: 3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        afterLabel: (ctx) => {
                            const dkk = data.dkk_saved[ctx.dataIndex];
                            return dkk != null ? `DKK saved: ${fmtNumber(dkk)}` : "";
                        },
                    },
                },
            },
            scales: {
                x: { ticks: { autoSkip: true, maxTicksLimit: 10 } },
                y: { beginAtZero: true, title: { display: true, text: "Hours" } },
            },
        },
    });
}

async function refreshSummary() {
    const days = document.getElementById("stats-days").value;
    refreshTimeseries(days);    // fire-and-forget; chart updates independently
    const res = await fetch(`/stats/summary?days=${days}`);
    const data = await res.json();
    const t = data.totals;

    document.getElementById("kpi-hours").textContent = fmtNumber(t.hours_saved);
    document.getElementById("kpi-money").textContent = fmtNumber(t.dkk_saved);
    document.getElementById("kpi-items").textContent = fmtNumber(t.items);
    document.getElementById("kpi-clicks").textContent = fmtNumber(t.clicks_saved);

    const top = data.breakdown.slice(0, 10);
    const ctx = document.getElementById("breakdown-chart").getContext("2d");
    if (breakdownChart) breakdownChart.destroy();
    breakdownChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: top.map(r => r.name),
            datasets: [{
                label: "Hours saved",
                data: top.map(r => r.hours_saved),
                backgroundColor: top.map(r => r.type === "queue"
                    ? "rgba(13, 110, 253, 0.6)"
                    : "rgba(25, 135, 84, 0.6)"),
                borderColor: top.map(r => r.type === "queue"
                    ? "rgba(13, 110, 253, 1)"
                    : "rgba(25, 135, 84, 1)"),
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { beginAtZero: true, title: { display: true, text: "Hours" } } },
            plugins: { legend: { display: false } }
        }
    });

    const tbody = document.querySelector("#breakdown-table tbody");
    if (!data.breakdown.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-muted text-center py-3">
            No savings data yet. Add a queue/process below and set its minutes/clicks per item.
        </td></tr>`;
    } else {
        tbody.innerHTML = data.breakdown.map(r => `
            <tr>
                <td>${escapeHtml(r.name)}</td>
                <td><span class="badge bg-${r.type === 'queue' ? 'primary' : 'success'}">${r.type}</span></td>
                <td class="text-end">${fmtNumber(r.count)}</td>
                <td class="text-end">${fmtNumber(r.hours_saved)}</td>
                <td class="text-end">${fmtNumber(r.clicks_saved)}</td>
                <td class="text-end"><strong>${fmtNumber(r.dkk_saved)}</strong></td>
            </tr>
        `).join("");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const tryRender = () => {
        if (typeof Chart === "undefined") return setTimeout(tryRender, 50);
        loadSettings();
        refreshSummary();
    };
    tryRender();
});
