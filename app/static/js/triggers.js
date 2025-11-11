function openEditModal(trigger) {

    // Update modal title
    document.getElementById("modalTitle").innerText = "Edit Trigger";

    // Reset validation states
    resetFormValidation();

    // Set common fields
    document.getElementById('trigger_id').value = trigger.id || "";
    document.getElementById('trigger_name').value = trigger.trigger_name || "";
    document.getElementById('process_name').value = trigger.process_name || "";
    document.getElementById('process_path').value = trigger.process_path || "";
    document.getElementById('process_args').value = trigger.process_args || "";
    document.getElementById('is_git_repo').checked = !!trigger.is_git_repo;
    document.getElementById('is_blocking').checked = !!trigger.is_blocking;
    document.getElementById('trigger_type').value = trigger.type;
    document.getElementById("priority").value = trigger.priority || 0;
    const whitelistValues = trigger.scheduler_whitelist || [];
    document.querySelectorAll("#scheduler_whitelist input[type='checkbox']").forEach(cb => {
        cb.checked = whitelistValues.includes(cb.value);
    });

    // Hide all type-specific fields
    document.getElementById("queueTriggerFields").style.display = "none";
    document.getElementById("scheduledTriggerFields").style.display = "none";
    document.getElementById("singleTriggerFields").style.display = "none";

    // Show only the relevant type fields
    if (trigger.type === "QUEUE") {
        document.getElementById("queueTriggerFields").style.display = "block";
        document.getElementById('queue_name').value = trigger.queue_name || "";
        document.getElementById('min_batch_size').value = trigger.min_batch_size || 1;
    } 
    else if (trigger.type === "SCHEDULED") {
        document.getElementById("scheduledTriggerFields").style.display = "block";
        document.getElementById('cron_expr').value = trigger.cron_expr || "";

        if (trigger.scheduled_next_run) {
            document.getElementById("next_run_display").innerText = "Next Run: " + trigger.next_run;
        } else {
            document.getElementById("next_run_display").innerText = "Next Run: N/A";
        }
    } 
    else if (trigger.type === "SINGLE") {
        document.getElementById("singleTriggerFields").style.display = "block";
        let date = new Date(trigger.single_next_run);
        let formattedDate = date.toISOString().slice(0, 16); // Extract YYYY-MM-DDTHH:MM
        document.getElementById('single_next_run').value = formattedDate;
    }

    // Disable irrelevant required fields
    disableIrrelevantFields(trigger.type);

    document.getElementById('editModal').style.display = 'flex';
}

function openNewTriggerModal(type) {
    // Update modal title
    document.getElementById("modalTitle").innerText = "New Trigger";

    // Reset form
    document.getElementById("editTriggerForm").reset();
    document.getElementById('trigger_id').value = ""; // Ensure new trigger
    document.getElementById('trigger_type').value = type; // Store type in a hidden input
    document.getElementById('is_git_repo').checked = true;
    document.getElementById("priority").value = 0;
    document.querySelectorAll("#scheduler_whitelist input[type='checkbox']").forEach(cb => {
        cb.checked = false;
    });
    // Hide all type-specific fields
    document.getElementById("queueTriggerFields").style.display = "none";
    document.getElementById("scheduledTriggerFields").style.display = "none";
    document.getElementById("singleTriggerFields").style.display = "none";

    // Show only the relevant type fields
    if (type === "QUEUE") {
        document.getElementById("queueTriggerFields").style.display = "block";
    } else if (type === "SCHEDULED") {
        document.getElementById("scheduledTriggerFields").style.display = "block";
    } else if (type === "SINGLE") {
        document.getElementById("singleTriggerFields").style.display = "block";
    }

    // Disable irrelevant required fields
    disableIrrelevantFields(type);

    document.getElementById('editModal').style.display = 'flex';
}


// Function to close the modal
function closeModal() {
    document.getElementById('editModal').style.display = 'none';
    resetFormValidation(); // Clear validation when closing
}

function resetFormValidation() {

    // Reset all form inputs
    document.querySelectorAll("#editTriggerForm input").forEach(input => {
        input.classList.remove("is-invalid", "is-valid");
    });

    // Clear any displayed error messages
    document.getElementById("next_run_display").innerText = "";
}
function disableIrrelevantFields(triggerType) {
    // Define field groups
    const queueFields = ["queue_name", "min_batch_size"];
    const scheduledFields = ["cron_expr"];
    const singleFields = ["single_next_run"];

    // Function to toggle 'required' attributes
    function toggleValidation(fields, shouldDisable) {
        fields.forEach(fieldId => {
            let field = document.getElementById(fieldId);
            if (field) {
                if (shouldDisable) {
                    field.removeAttribute("required");
                } else {
                    field.setAttribute("required", "true");
                }
            }
        });
    }

    // Disable fields that do not belong to the selected trigger type
    if (triggerType === "QUEUE") {
        toggleValidation(scheduledFields, true);
        toggleValidation(singleFields, true);
        toggleValidation(queueFields, false);
    } else if (triggerType === "SCHEDULED") {
        toggleValidation(queueFields, true);
        toggleValidation(singleFields, true);
        toggleValidation(scheduledFields, false);
    } else if (triggerType === "SINGLE") {
        toggleValidation(queueFields, true);
        toggleValidation(scheduledFields, true);
        toggleValidation(singleFields, false);
    }
}

// Function to validate the form before submission
function validateForm() {
    let isValid = true;

    // Validate the form
    const form = document.getElementById("editTriggerForm");
    if (!form.checkValidity()) {
        isValid = false;
    }

    return isValid;
}



function updateNextRun() {
    const cronField = document.getElementById("cron_expr");
    const nextRunDisplay = document.getElementById("next_run_display");


    const cronValue = cronField.value.trim();

    if (!cronValue) {
        nextRunDisplay.innerText = "Invalid Cron Expression";
        cronField.classList.add("is-invalid");
        cronField.classList.remove("is-valid");
        return;
    }

    // Send cron expression to Flask
    fetch("/triggers/get_next_run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cron_expr: cronValue })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }

        // Update the UI with the calculated next run time
        nextRunDisplay.innerText = "Next Run: " + data.next_run;
        cronField.classList.remove("is-invalid");
        cronField.classList.add("is-valid");

    })
    .catch(error => {
        nextRunDisplay.innerText = "Invalid Cron Expression";
        cronField.classList.add("is-invalid");
        cronField.classList.remove("is-valid");

    });
}

function confirmDeleteTrigger(triggerId, triggerName) {
    if (confirm(`Are you sure you want to delete "${triggerName}"?`)) {
        deleteTrigger(triggerId);
    }
}

function deleteTrigger(triggerId) {
    fetch(`/triggers/delete`, {
        method: "POST",  // Change to DELETE if needed
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: triggerId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Trigger deleted successfully!");
            // Remove deleted row from the table dynamically
            $('#trigger-table').bootstrapTable("refresh"); 
        } else {
            alert("Failed to delete trigger: " + data.error);
        }
    })
    .catch(error => console.error("Error deleting trigger:", error));
}


function formatActionButtons(value, row) {
    return `
        <button class="btn btn-primary btn-sm" data-trigger='${JSON.stringify(row)}' onclick="openEditModalFromButton(this)">
            <i class="bi bi-pencil"></i> Edit
        </button>
        <button class="btn btn-danger btn-sm" onclick="confirmDeleteTrigger('${row.id}', '${row.trigger_name}')">
            <i class="bi bi-trash"></i> Delete
        </button>
    `;
}



function formatStatusButton(value, row) {
    let iconClass = "";
    let textColor = "";
    let tooltip = "";
    let newStatus = ""; // The status we will change to on click
    let customStyle = ""; // Custom CSS for precise color

    if (row.process_status === "PAUSED") {
        iconClass = "bi-pause-circle"; // Bootstrap pause icon
        textColor = "text-warning"; // Yellow color
        tooltip = "Paused - Click to Start";
        newStatus = "IDLE"; // Change to IDLE when clicked
    } else if (row.process_status === "FAILED") {
        iconClass = "bi-x-circle"; // Bootstrap error icon
        textColor = "text-danger"; // Red color
        tooltip = "Failed - Click to Restart";
        newStatus = "IDLE"; // Allow restarting
    } else if (row.type === "SINGLE" && row.process_status === "DONE") {
        iconClass = "bi-play-circle"; // Bootstrap play icon
        textColor = "text-primary"; // Blue for play button
        tooltip = "Ready to Run - Click to Start";
        newStatus = "IDLE";
    } else {
        iconClass = "bi-power"; // Generic power icon for active triggers
        textColor = ""; // No default Bootstrap color (we use a custom one)
        customStyle = "color: rgb(0, 255, 137);"; // Exact green color
        tooltip = "Active - Click to Pause";
        newStatus = "PAUSED"; // Change to PAUSED when clicked
    }

    return `
        <button class="btn btn-link ${textColor}" style="border: none; background: transparent; ${customStyle}"
                onclick="toggleStatus('${row.id}', '${newStatus}')" title="${tooltip}">
            <i class="bi ${iconClass} fs-4"></i>
        </button>`;
}

function toggleStatus(triggerId, newStatus) {
    fetch(`/triggers/update_status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: triggerId, new_status: newStatus })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Find the row for the updated trigger
            let $row = $(`button[onclick="toggleStatus('${triggerId}', '${newStatus}')"]`).closest("tr");
            
            // Update process_status in the table
            let newStatusText = newStatus; // Update UI text representation
            let newButton = formatStatusButton(newStatus, { id: triggerId, process_status: newStatus });

            // Update the button in the table without refreshing the whole page
            $row.find("td").eq(0).html(newButton); // Assuming status button is in the first column
            
        } else {
            alert("Failed to update status.");
        }
    })
    .catch(error => console.error("Error updating status:", error));
}



function openEditModalFromButton(button) {
    try {
        let jsonText = button.getAttribute('data-trigger');
        let trigger = JSON.parse(jsonText);
        console.log("Opening modal for:", trigger);
        openEditModal(trigger);
    } catch (error) {
        console.error("Error parsing JSON:", error);
    }
}


document.addEventListener("DOMContentLoaded", function () {
    // Attach event listener to cron input field
    const cronField = document.getElementById("cron_expr");
    if (cronField) {
        cronField.addEventListener("input", updateNextRun);
    }

    const form = document.getElementById("editTriggerForm");


    fetch("/triggers/get_scheduler_list")
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById("scheduler_whitelist");
            container.innerHTML = "";

            (data.schedulers || []).forEach(name => {
                const id = `scheduler_${name.replace(/\s+/g, "_")}`;
                const wrapper = document.createElement("div");
                wrapper.classList.add("form-check", "mb-1");
                wrapper.innerHTML = `
                    <input class="form-check-input" type="checkbox" id="${id}" value="${name}">
                    <label class="form-check-label" for="${id}">${name}</label>
                `;
                container.appendChild(wrapper);
            });
        })
        .catch(err => console.error("Error loading schedulers:", err));
    
        // Ensure only one event listener is attached to the form
    form.removeEventListener("submit", handleTriggerFormSubmit); // Remove existing listener
    form.addEventListener("submit", handleTriggerFormSubmit); // Add a single event listener
});

// Function to handle trigger form submission
function handleTriggerFormSubmit(event) {
    event.preventDefault();

    let triggerData = {
        id: document.getElementById('trigger_id').value,
        trigger_name: document.getElementById('trigger_name').value,
        process_name: document.getElementById('process_name').value,
        process_path: document.getElementById('process_path').value,
        process_args: document.getElementById('process_args').value,
        is_git_repo: document.getElementById('is_git_repo').checked,
        is_blocking: document.getElementById('is_blocking').checked,
        type: document.getElementById("trigger_type").value,
        priority: parseInt(document.getElementById('priority').value) || 0,
        scheduler_whitelist: Array.from(
            document.querySelectorAll("#scheduler_whitelist input[type='checkbox']:checked")
        ).map(cb => cb.value)
    };

    if (triggerData.type === "QUEUE") {
        triggerData.queue_name = document.getElementById('queue_name').value;
        triggerData.min_batch_size = document.getElementById('min_batch_size').value;
    } else if (triggerData.type === "SCHEDULED") {
        triggerData.cron_expr = document.getElementById('cron_expr').value;
        triggerData.scheduled_next_run = document.getElementById('next_run_display').innerText.replace("Next Run: ", "");
    } else if (triggerData.type === "SINGLE") {
        triggerData.single_next_run = document.getElementById('single_next_run').value;
    }

    // Detect if it's a new trigger
    let url = triggerData.id ? "/triggers/edit" : "/triggers/create";

    fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(triggerData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeModal();
            location.reload();
        } else {
            alert(`Failed to ${triggerData.id ? "update" : "create"} trigger.`);
        }
    })
    .catch(error => console.error("Error submitting form:", error));
}

function queryParams(params) {
    return {
        limit: params.limit,
        offset: params.offset,
        sort: params.sort,
        order: params.order,
        search: params.search
    };
}

function responseHandler(res) {
    return {
        total: res.total,
        rows: res.rows
    };
}
function updateTriggerTableFilters() {
    let search = document.getElementById("trigger-search").value.trim();

    $("#trigger-table").bootstrapTable("refresh", {
        query: { search: search }
    });
}
