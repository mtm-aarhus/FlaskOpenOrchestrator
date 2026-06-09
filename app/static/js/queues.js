// Status pill IDs mapped to backend query-param names.
const STATUS_PILLS = {
    "overview-has-failed":      "has_failed",
    "overview-has-in-progress": "has_in_progress",
    "overview-has-new":         "has_new",
    "overview-has-done":        "has_done",
    "overview-has-abandoned":   "has_abandoned",
};

function queryParams(params) {
    const out = {
        start_date: document.getElementById("overview-start")?.value || "",
        end_date:   document.getElementById("overview-end")?.value || "",
    };
    for (const [id, qp] of Object.entries(STATUS_PILLS)) {
        out[qp] = document.getElementById(id)?.checked ? "true" : "false";
    }
    return out;
}

function responseHandler(res) {
    return res.rows || res;
}

let overviewRefreshTimer = null;
let overviewSearchTimer = null;

function updateOverviewFilters(delay = 350) {
    clearTimeout(overviewRefreshTimer);

    const refresh = () => {
        $("#queues-overview-table").bootstrapTable("refresh", { pageNumber: 1 });
    };

    if (delay <= 0) {
        refresh();
        return;
    }

    overviewRefreshTimer = setTimeout(refresh, delay);
}

function updateOverviewSearch(delay = 150) {
    clearTimeout(overviewSearchTimer);

    const search = () => {
        const value = document.getElementById("overview-search")?.value || "";
        $("#queues-overview-table").bootstrapTable("resetSearch", value);
    };

    if (delay <= 0) {
        search();
        return;
    }

    overviewSearchTimer = setTimeout(search, delay);
}

function clearOverviewFilters() {
    document.getElementById("overview-search").value = "";
    document.getElementById("overview-start").value = "";
    document.getElementById("overview-end").value = "";
    for (const id of Object.keys(STATUS_PILLS)) {
        const el = document.getElementById(id);
        if (el) el.checked = false;
    }
    updateOverviewSearch(0);
    updateOverviewFilters(0);
}

// Apply URL params on first table render; used by home-page deep-links and chart drill-down.
function applyQueueOverviewUrlFilters() {
    const params = new URLSearchParams(window.location.search);
    const known = ["search", "start_date", "end_date", ...Object.values(STATUS_PILLS)];
    if (!known.some(k => params.has(k))) return;

    if (params.has("search"))     document.getElementById("overview-search").value = params.get("search");
    if (params.has("start_date")) document.getElementById("overview-start").value = params.get("start_date");
    if (params.has("end_date"))   document.getElementById("overview-end").value   = params.get("end_date");
    for (const [id, qp] of Object.entries(STATUS_PILLS)) {
        if (params.has(qp)) {
            const el = document.getElementById(id);
            if (el) el.checked = params.get(qp) === "true";
        }
    }
    window.history.replaceState({}, document.title, window.location.pathname);
    updateOverviewSearch(0);
    updateOverviewFilters(0);
}

document.addEventListener("DOMContentLoaded", () => {
    $("#queues-overview-table").one("post-body.bs.table", applyQueueOverviewUrlFilters);
});
