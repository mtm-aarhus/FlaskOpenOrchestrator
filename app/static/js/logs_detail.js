function getSelectedIds() {
    let selectedRows = $("#logs-table").bootstrapTable("getSelections"); // Bootstrap method
    return selectedRows.map(row => row.id); // Extract IDs
}

function formatLogTime(value) {
    if (!value) return '';

    // Convert timestamp to a Date object
    const date = new Date(value);

    // Format as "DD-MM-YY HH:mm:ss"
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0'); // Months are 0-based
    const year = String(date.getFullYear()).slice(-2); // Get last 2 digits of the year
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
            $("#logs-table").bootstrapTable("refresh"); // Reload table instead of page
        } else {
            alert("Failed to delete selected logs.");
        }
    });
}

function confirmDeleteAllLogs(button) {
    let processName = button.getAttribute("data-process");  // Get process name from data-attribute

    let userInput = prompt(`Type "delete" to permanently delete ALL logs for process: ${processName}`);

    if (userInput !== "delete") {
        alert("Deletion canceled.");
        return;
    }

    fetch(`/logs/${encodeURIComponent(processName)}/delete_all`, {  // Ensure process_name is properly encoded
        method: "POST",
        headers: { "Content-Type": "application/json" }
    }).then(response => response.json())
      .then(data => {
          if (data.success) {
              alert("All logs deleted successfully!");
              $("#logs-table").bootstrapTable("refresh"); // Refresh the table
          } else {
              alert("Failed to delete logs: " + (data.error || "Unknown error"));
          }
      });
}

async function fetchLogLevels(processName) {
    let response = await fetch(`/logs/${encodeURIComponent(processName)}/log_levels`);
    let levels = await response.json();

    let levelFilter = document.getElementById("log-level-filter");
    levelFilter.innerHTML = '<option value="">All Levels</option>'; // Reset dropdown
    
    levels.forEach(level => {
        let option = document.createElement("option");
        option.value = level;
        option.textContent = level;
        levelFilter.appendChild(option);
    });

}


document.addEventListener("DOMContentLoaded", async function() {
    const processName = document.getElementById("logs-table").dataset.processName;
    let levelFilter = document.getElementById("log-level-filter");
    let startDateInput = document.getElementById("date-filter-start");
    let endDateInput = document.getElementById("date-filter-end");

    let isFirstRun = sessionStorage.getItem("logsFirstRun") === false;
    if (!isFirstRun) {
        await fetchLogLevels(processName);

        let urlParams = new URLSearchParams(window.location.search);

        if (urlParams.has("filter_level")) {
            let filterLevel = urlParams.get("filter_level");
            let optionExists = Array.from(levelFilter.options).some(opt => opt.value === filterLevel);

            if (optionExists) {
                levelFilter.value = filterLevel;
            } 
        }

        if (urlParams.has("start_date")) {
            startDateInput.value = urlParams.get("start_date").replace(" ", "T");
        }

        if (urlParams.has("end_date")) {
            endDateInput.value = urlParams.get("end_date").replace(" ", "T");
        } else {
            let now = new Date();
            let timezoneOffset = now.getTimezoneOffset() * 60000;
            let systemTime = new Date(now.getTime() - timezoneOffset);
            endDateInput.value = systemTime.toISOString().slice(0, 16);
        }

        updateTableFilters(); // Call only after ensuring filters are set

        // Mark as initialized so it doesn't reapply filters on reload
        sessionStorage.setItem("logsFirstRun", "false");

        // Remove query parameters from the URL without reloading
        window.history.replaceState({}, document.title, window.location.pathname);
    }
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
    if (!value) return '-'; // Handle empty values

    let maxLength = 175; // Set fixed truncation length
    if (value.length <= maxLength) return value; // If short, show full text

    let shortText = value.substring(0, maxLength) + "..."; // Truncated text

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

// Show full content in modal when clicking
$(document).on("click", ".view-full-text, .truncated-text", function (event) {
    event.preventDefault();

    let fullText = decodeURIComponent($(this).data("full"));

    // Check if it's JSON and format it properly
    try {
        let jsonObject = JSON.parse(fullText);
        fullText = JSON.stringify(jsonObject, null, 4); // Pretty-print JSON
    } catch (e) {
        // Not JSON, show as-is
    }

    $("#modalContent").text(fullText);
    $("#fullTextModal").modal("show");
});

// Copy content to clipboard
$("#copyTextBtn").click(function () {
    let text = $("#modalContent").text();
    navigator.clipboard.writeText(text).then(() => {
        alert("Copied to clipboard!");
    });
});

