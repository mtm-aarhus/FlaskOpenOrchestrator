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

function formatJobActions(value, row) {
    return `
        <a href="/jobs/${row.id}" class="btn btn-sm btn-outline-primary" title="View linked logs">
            <i class="bi bi-file-earmark-text"></i> ${row.log_count} log${row.log_count === 1 ? '' : 's'}
        </a>`;
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
    if (!statusFilter) return;

    const res = await fetch("/jobs/statuses");
    const statuses = await res.json();
    statuses.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        statusFilter.appendChild(opt);
    });
});
