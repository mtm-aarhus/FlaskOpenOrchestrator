async function loadQueueNames() {
    const res = await fetch("/stats/queue_names");
    const names = await res.json();
    const sel = document.getElementById("savings-queue");
    sel.innerHTML = "";
    names.forEach(n => {
        const opt = document.createElement("option");
        opt.value = n;
        opt.textContent = n;
        sel.appendChild(opt);
    });
}

async function calculateSavings() {
    const queueName = document.getElementById("savings-queue").value;
    const minutes = document.getElementById("savings-minutes").value;
    const from = document.getElementById("savings-from").value;
    const to = document.getElementById("savings-to").value;

    const params = new URLSearchParams({
        queue_name: queueName,
        minutes_per_item: minutes,
    });
    if (from) params.set("start_date", from);
    if (to) params.set("end_date", to);

    const res = await fetch(`/stats/savings?${params}`);
    const data = await res.json();

    const out = document.getElementById("savings-result");
    if (data.error) {
        out.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        return;
    }
    out.innerHTML = `
        <div class="alert alert-success mb-0">
            <div><strong>${data.done_count.toLocaleString()}</strong> elements done</div>
            <div><strong>${data.minutes_saved.toLocaleString()}</strong> minutes saved</div>
            <div class="fs-4"><strong>${data.hours_saved.toLocaleString()} hours</strong> total</div>
        </div>`;
}

async function loadSchedulerHealth() {
    const res = await fetch("/stats/scheduler_health");
    const rows = await res.json();
    const out = document.getElementById("scheduler-health");
    if (!rows.length) {
        out.innerHTML = '<div class="text-muted">No schedulers registered.</div>';
        return;
    }
    const colors = { online: "success", stale: "warning", offline: "danger" };
    out.innerHTML = `
        <table class="table table-sm mb-0">
            <thead><tr><th>Machine</th><th>Health</th><th>Last update</th><th>Latest trigger</th></tr></thead>
            <tbody>
                ${rows.map(r => `
                    <tr>
                        <td>${r.machine_name}</td>
                        <td><span class="badge bg-${colors[r.health] || 'secondary'}">${r.health}</span>
                            ${r.minutes_since !== null ? `<small class="text-muted ms-1">(${r.minutes_since}m ago)</small>` : ''}
                        </td>
                        <td>${r.last_update || '-'}</td>
                        <td>${r.latest_trigger || '-'}</td>
                    </tr>`).join('')}
            </tbody>
        </table>`;
}

async function loadDowntime() {
    const days = document.getElementById("downtime-days").value || 30;
    document.getElementById("downtime-days-label").textContent = days;
    const res = await fetch(`/stats/downtime?days=${days}`);
    const data = await res.json();
    const out = document.getElementById("downtime-table");

    if (!data.rows.length) {
        out.innerHTML = '<div class="text-muted">No job runs in this window. Run summary will populate once OO 3.0 has been collecting Jobs data.</div>';
        return;
    }
    out.innerHTML = `
        <table class="table table-sm">
            <thead>
                <tr>
                    <th>Process</th>
                    <th>Total runs</th>
                    <th>Done</th>
                    <th>Failed</th>
                    <th>Killed</th>
                    <th>Running</th>
                    <th>Failure rate</th>
                </tr>
            </thead>
            <tbody>
                ${data.rows.map(r => {
                    const failureRate = r.total ? Math.round((r.FAILED / r.total) * 100) : 0;
                    return `
                        <tr>
                            <td>${r.process_name}</td>
                            <td>${r.total}</td>
                            <td><span class="badge bg-success">${r.DONE}</span></td>
                            <td><span class="badge bg-danger">${r.FAILED}</span></td>
                            <td><span class="badge bg-secondary">${r.KILLED}</span></td>
                            <td><span class="badge bg-primary">${r.RUNNING}</span></td>
                            <td>${failureRate}%</td>
                        </tr>`;
                }).join('')}
            </tbody>
        </table>`;
}

document.addEventListener("DOMContentLoaded", () => {
    loadQueueNames();
    loadSchedulerHealth();
    loadDowntime();
});
