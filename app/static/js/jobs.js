function formatJobStatus(value) {
    const colors = {
        RUNNING: "primary",
        DONE: "success",
        FAILED: "danger",
        KILLED: "secondary",
    };
    const color = colors[value] || "secondary";
    return `<span class="badge bg-${color}">${value}</span>`;
}

function formatDurationFromMs(ms) {
    const secs = Math.max(0, Math.floor(ms / 1000));
    if (secs < 60)   return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

// Per-row duration formatter. For RUNNING jobs, marks the cell so the global
// ticker can update it client-side every second without re-fetching.
function formatJobDuration(value, row) {
    if (row.status === "RUNNING" && row.start_time_iso) {
        const startMs = Date.parse(row.start_time_iso);
        const dur = formatDurationFromMs(Date.now() - startMs);
        return `<span class="js-live-duration" data-start-ms="${startMs}">${dur}</span>`;
    }
    return value || "";
}

// Tick every second to update RUNNING-job durations on screen.
setInterval(() => {
    document.querySelectorAll(".js-live-duration").forEach(el => {
        const startMs = parseInt(el.dataset.startMs, 10);
        if (!startMs) return;
        el.textContent = formatDurationFromMs(Date.now() - startMs);
    });
}, 1000);

function formatJobActions(value, row) {
    const logsBtn = `
        <a href="/jobs/${row.id}" class="btn btn-sm btn-outline-primary" title="View linked logs">
            <i class="bi bi-file-earmark-text"></i> ${row.log_count} log${row.log_count === 1 ? '' : 's'}
        </a>`;
    let killBtn = "";
    if (row.status === "RUNNING") {
        killBtn = `
            <div class="btn-group btn-group-sm ms-1" role="group">
                <button class="btn btn-outline-danger" onclick="confirmKillJob('${row.id}')" title="Kill this job (asks scheduler)">
                    <i class="bi bi-x-octagon"></i> Kill
                </button>
                <button class="btn btn-outline-secondary dropdown-toggle dropdown-toggle-split" data-bs-toggle="dropdown" aria-expanded="false"></button>
                <ul class="dropdown-menu">
                    <li><a class="dropdown-item text-danger" href="#" onclick="forceKillJob(event, '${row.id}')">
                        <i class="bi bi-slash-circle"></i> Force-mark as KILLED
                        <div class="small text-muted">Use only if the scheduler is dead</div>
                    </a></li>
                </ul>
            </div>`;
    }
    return logsBtn + killBtn;
}

function confirmKillJob(jobId) {
    if (!confirm("Kill this running job? The scheduler will terminate the process tree.")) return;
    fetch(`/jobs/${encodeURIComponent(jobId)}/kill`, { method: "POST" })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                window.showToast("Kill failed: " + (data.error || "unknown"), "error");
                return;
            }
            window.showToast("Kill request sent — scheduler will terminate the process", "warning");
            $("#jobs-table").bootstrapTable("refresh");
        });
}

function forceKillJob(event, jobId) {
    event.preventDefault();
    if (!confirm("Force-mark this job as KILLED?\n\nThis bypasses the scheduler and just updates the database. Use only when the scheduler is dead.")) return;
    fetch(`/jobs/${encodeURIComponent(jobId)}/force_kill`, { method: "POST" })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                window.showToast("Force-kill failed: " + (data.error || "unknown"), "error");
                return;
            }
            window.showToast("Job marked as KILLED", "success");
            $("#jobs-table").bootstrapTable("refresh");
        });
}

function updateJobTableFilters() {
    const status = document.getElementById("job-status-filter")?.value || "";
    const startDate = document.getElementById("date-filter-start")?.value || "";
    const endDate = document.getElementById("date-filter-end")?.value || "";
    const search = document.getElementById("job-search")?.value || "";

    $("#jobs-table").bootstrapTable("refresh", {
        query: {
            filter_status: status,
            start_date: startDate,
            end_date: endDate,
            search: search,
        },
        pageNumber: 1,
    });
}

document.addEventListener("DOMContentLoaded", async function () {
    const statusFilter = document.getElementById("job-status-filter");
    if (statusFilter) {
        const res = await fetch("/jobs/statuses");
        const statuses = await res.json();
        statuses.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s;
            opt.textContent = s;
            statusFilter.appendChild(opt);
        });
    }

    // Auto-refresh every 15s so we see job state changes (RUNNING → DONE/KILLED).
    if (typeof window.startAutoRefresh === "function") {
        window.startAutoRefresh(15000, () => {
            $("#jobs-table").bootstrapTable("refresh", { silent: true });
        });
    }

    // Flash a row when its status changes between refreshes.
    if (typeof window.watchRowChanges === "function") {
        window.watchRowChanges("#jobs-table", row => row.status);
    }
});
