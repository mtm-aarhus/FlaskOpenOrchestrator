function getSelectedIds() {
    let selectedRows = $("#logs-table").bootstrapTable("getSelections"); // Bootstrap method
    return selectedRows.map(row => row.id); // Extract IDs
}

function formatLogTime(value) {
    if (!value) return '';

    const date = new Date(value);

    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = String(date.getFullYear()).slice(-2);
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');

    return `${day}-${month}-${year} ${hours}:${minutes}:${seconds}`;
}

function deleteSelectedLogs() {
    let selectedIds = getSelectedIds();
    if (selectedIds.length === 0) {
        alert("No logs selected.");
        return;
    }

    fetch("/logs/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selectedIds })
    }).then(response => response.json()).then(data => {
        if (data.success) {
            alert("Logs deleted successfully!");
            $("#logs-table").bootstrapTable("refresh");
        } else {
            alert("Failed to delete selected logs.");
        }
    });
}

// CHANGED: gør den robust hvis knappen ikke findes / ikke har process
function confirmDeleteAllLogs(button) {
    let processName = button?.getAttribute("data-process");

    if (!processName) {
        alert("Delete all is only available for a specific process.");
        return;
    }

    let userInput = prompt(`Type "delete" to permanently delete ALL logs for process: ${processName}`);

    if (userInput !== "delete") {
        alert("Deletion canceled.");
        return;
    }

    fetch(`/logs/${encodeURIComponent(processName)}/delete_all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
    }).then(response => response.json())
      .then(data => {
          if (data.success) {
              alert("All logs deleted successfully!");
              $("#logs-table").bootstrapTable("refresh");
          } else {
              alert("Failed to delete logs: " + (data.error || "Unknown error"));
          }
      });
}

// CHANGED: brug /logs/all/log_levels når processName er tom
async function fetchLogLevels(processName) {
    const url = processName
        ? `/logs/${encodeURIComponent(processName)}/log_levels`
        : `/logs/all/log_levels`;

    let response = await fetch(url);
    let levels = await response.json();

    let levelFilter = document.getElementById("log-level-filter");
    levelFilter.innerHTML = '<option value="">All Levels</option>';

    levels.forEach(level => {
        let option = document.createElement("option");
        option.value = level;
        option.textContent = level;
        levelFilter.appendChild(option);
    });
}

// CHANGED: fix "logsFirstRun" bug + understøt all-view
document.addEventListener("DOMContentLoaded", async function() {
    const tableEl = document.getElementById("logs-table");
    if (!tableEl) return;

    const processName = tableEl.dataset.processName || "";

    const levelFilter = document.getElementById("log-level-filter");
    const startDateInput = document.getElementById("date-filter-start");
    const endDateInput = document.getElementById("date-filter-end");

    await fetchLogLevels(processName);

    const urlParams = new URLSearchParams(window.location.search);

    if (urlParams.has("filter_level")) {
        const filterLevel = urlParams.get("filter_level");
        const optionExists = Array.from(levelFilter.options).some(opt => opt.value === filterLevel);
        if (optionExists) levelFilter.value = filterLevel;
    }

    if (urlParams.has("start_date")) {
        startDateInput.value = urlParams.get("start_date").replace(" ", "T");
    }

    if (urlParams.has("end_date")) {
        endDateInput.value = urlParams.get("end_date").replace(" ", "T");
    } else {
        const now = new Date();
        const timezoneOffset = now.getTimezoneOffset() * 60000;
        const systemTime = new Date(now.getTime() - timezoneOffset);
        endDateInput.value = systemTime.toISOString().slice(0, 16);
    }

    updateTableFilters();
    window.history.replaceState({}, document.title, window.location.pathname);
});

function updateTableFilters() {
    let level = document.getElementById("log-level-filter")?.value;
    let startDate = document.getElementById("date-filter-start")?.value;
    let endDate = document.getElementById("date-filter-end")?.value;
    let search = document.getElementById("log-search")?.value;

    let queryParams = {
        filter_level: level,
        start_date: startDate,
        end_date: endDate,
        search: search,
    };

    $("#logs-table").bootstrapTable('refresh', {
        query: queryParams,
        pageNumber: 1
    });
}

function truncateText(value, row, index) {
    if (!value) return '-';

    let maxLength = 175;
    if (value.length <= maxLength) return value;

    let shortText = value.substring(0, maxLength) + "...";

    return `
        <span class="truncated-text" style="cursor: pointer;"
              data-full="${encodeURIComponent(value)}">
            ${shortText}
        </span>
        <a href="#" class="view-full-text text-primary" data-full="${encodeURIComponent(value)}" style="margin-left: 5px;">
            <i class="bi-arrows-angle-expand"></i>
        </a>
    `;
}

$(document).on("click", ".view-full-text, .truncated-text", function (event) {
    event.preventDefault();

    let fullText = decodeURIComponent($(this).data("full"));

    try {
        let jsonObject = JSON.parse(fullText);
        fullText = JSON.stringify(jsonObject, null, 4);
    } catch (e) {}

    $("#modalContent").text(fullText);
    $("#fullTextModal").modal("show");
});

$("#copyTextBtn").click(function () {
    let text = $("#modalContent").text();
    navigator.clipboard.writeText(text).then(() => {
        alert("Copied to clipboard!");
    });
});

function toggleViewedSelected() {
    const ids = $('#logs-table').bootstrapTable('getSelections').map(r => r.id);
    if (!ids.length) return;

    fetch("/logs/toggle_viewed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids })
    })
    .then(r => r.json())
    .then(() => {
        $('#logs-table').bootstrapTable('uncheckAll');
        $('#logs-table').bootstrapTable('refresh', { silent: true });
        updateTableFilters();
    });
}