function getSelectedIds() {
    return $("#queues-table").bootstrapTable("getSelections").map(row => row.id);
}

function retrySelected() {
    let selectedIds = getSelectedIds();
    if (selectedIds.length === 0) {
        alert("No queues selected.");
        return;
    }

    if (!confirm(`Are you sure you want to retry ${selectedIds.length} selected queue item(s)?`)) {
        return; // Cancel if user presses "Cancel"
    }
    fetch("/queues/update_status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selectedIds, status: "NEW" })
    }).then(response => response.json()).then(data => {
        if (data.success) {
            alert("Queues set to NEW successfully!");
            $("#queues-table").bootstrapTable("refresh"); // Refresh the table without reloading the page
        } else {
            alert("Failed to retry selected queues.");
        }
    });
}

function deleteSelected() {
    let selectedIds = getSelectedIds();
    if (selectedIds.length === 0) {
        alert("No queues selected.");
        return;
    }
    if (!confirm("Are you sure you want to delete the selected queues?")) {
        return;
    }
    fetch("/queues/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selectedIds })
    }).then(response => response.json()).then(data => {
        if (data.success) {
            alert("Queues deleted successfully!");
            $("#queues-table").bootstrapTable("refresh"); // Refresh the table dynamically
        } else {
            alert("Failed to delete selected queues.");
        }
    });
}


function toggleSelectAll(source) {
    let checkboxes = document.querySelectorAll(".select-checkbox");
    checkboxes.forEach(checkbox => checkbox.checked = source.checked);
}

document.addEventListener("DOMContentLoaded", function () {
    let checkboxes = document.querySelectorAll(".select-checkbox");
    let selectAllCheckbox = document.getElementById("select-all");

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener("change", function () {
            // Update "Select All" checkbox when individual checkboxes change
            selectAllCheckbox.checked = checkboxes.length === document.querySelectorAll(".select-checkbox:checked").length;
        });
    });
});

function updateTableFilters() {
    let status = document.getElementById("queue-status-filter")?.value;
    let startDate = document.getElementById("date-filter-start")?.value;
    let endDate = document.getElementById("date-filter-end")?.value;
    let search = document.getElementById("queue-search")?.value;

    let queryParams = {
        filter_status: status,
        start_date: startDate,
        end_date: endDate,
        search: search,
    };


    $("#queues-table").bootstrapTable('refresh', {
        query: queryParams,
        pageNumber: 1  // Reset to first page when filtering
    });
}



function truncateText(value, row, index) {
    if (!value) return '-'; // Handle empty values

    let maxLength = 30; // Set fixed truncation length
    if (value.length <= maxLength) return value; // If short, show full text

    let shortText = value.substring(0, maxLength) + "..."; // Truncated text

    return `
        <span class="truncated-text" style="cursor: pointer;" 
              data-full="${encodeURIComponent(value)}">
            ${shortText}
        </span>
        <a href="#" class="view-full-text text-primary" data-full="${encodeURIComponent(value)}" style="margin-left: 5px; --bs-link-color-rgb">
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

document.addEventListener("DOMContentLoaded", async function() {
    const queueName = document.getElementById("queues-table").dataset.queueName;
    let statusFilter = document.getElementById("queue-status-filter");
    let startDateInput = document.getElementById("date-filter-start");
    let endDateInput = document.getElementById("date-filter-end");

    let isFirstRun = sessionStorage.getItem("queuesFirstRun") === false;
    if (!isFirstRun) {
        cachedProcessName = await getProcessName(queueName);
        await fetchQueueStatuses(queueName);

        let urlParams = new URLSearchParams(window.location.search);

        // Wait for the queue statuses to be populated before setting filters
        if (urlParams.has("filter_status")) {
            let filterStatus = urlParams.get("filter_status");
            let optionExists = Array.from(statusFilter.options).some(opt => opt.value === filterStatus);

            if (optionExists) {
                statusFilter.value = filterStatus;
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
        sessionStorage.setItem("queuesFirstRun", "false");

        // Remove query parameters from the URL without reloading
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});

async function fetchQueueStatuses(queueName) {
    let response = await fetch(`/queues/${encodeURIComponent(queueName)}/status`);
    let statuses = await response.json();

    let statusFilter = document.getElementById("queue-status-filter");
    statusFilter.innerHTML = '<option value="">All</option>'; // Reset dropdown
    
    statuses.forEach(status => {
        let option = document.createElement("option");
        option.value = status;
        option.textContent = status;
        statusFilter.appendChild(option);
    });
}

let cachedProcessName = null;


async function getProcessName(queueName) {
    try {
        let response = await fetch(`/queues/get_process_name?queue_name=${encodeURIComponent(queueName)}`);
        let data = await response.json();
        if (data.success) {
            return data.process_name;
        } else {
            console.warn(`⚠ No process found for queue: ${queueName}`);
            return null;
        }
    } catch (error) {
        console.error("❌ Error fetching process name:", error);
        return null;
    }
}

function formatDateToISO(dateString, addMinute = false) {
    // Input format: "DD-MM-YYYY HH:MM"
    let [datePart, timePart] = dateString.split(" ");
    let [day, month, year] = datePart.split("-");
    let [hours, minutes] = timePart.split(":");

    // Create a Date object but avoid timezone issues
    let dateObj = new Date(year, month - 1, day, hours, minutes);

    // Add 1 minute if required (without affecting timezone)
    if (addMinute) {
        dateObj.setMinutes(dateObj.getMinutes() + 2);
    }

    // Manually extract and format as YYYY-MM-DDTHH:MM
    let formattedDate = 
        `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, "0")}-${String(dateObj.getDate()).padStart(2, "0")}T` +
        `${String(dateObj.getHours()).padStart(2, "0")}:${String(dateObj.getMinutes()).padStart(2, "0")}`;

    return formattedDate;
}

function statusFormatter(value, row) {
    if (!row.start_date || !row.end_date) {
        return value; // If no start or end date, just return status text
    }

    if (!cachedProcessName) {
        return value; // Return just the status if no process is found
    }

    let startDate = encodeURIComponent(formatDateToISO(row.start_date));
    let endDate = encodeURIComponent(formatDateToISO(row.end_date, true)); // Add +1 minute

    let logsUrl = `/logs/${encodeURIComponent(cachedProcessName)}?start_date=${startDate}&end_date=${endDate}`;

    return `
                <a href="${logsUrl}" title="Show Logs" class="text-decoration-none text-primary">
            <i class="bi bi-file-earmark-text"></i>  <!-- Bootstrap Log Icon -->
        </a>
        ${value} 

    `;
}