function actionFormatter(value, row, index) {
    return `
        <button class="btn btn-sm btn-primary edit-btn" onclick="openConstantModal(${index})">
            <i class="bi bi-pencil-square"></i> Edit
        </button>
        <button class="btn btn-sm btn-danger delete-btn" onclick="deleteConstant('${row.name}')">
            <i class="bi bi-trash"></i> Delete
        </button>
    `;
}

function openConstantModal(index = null) {
    const modal = new bootstrap.Modal(document.getElementById("editConstantModal"));
    const form = document.getElementById("constantForm");

    if (index !== null) {
        let row = $("#constants-table").bootstrapTable('getData')[index];

        document.getElementById("constantModalTitle").innerText = "Edit Constant";
        document.getElementById("constant_id").value = row.name;
        document.getElementById("constant-name").value = row.name;
        document.getElementById("constant-value").value = row.value;
    } else {
        document.getElementById("constantModalTitle").innerText = "New Constant";
        form.reset();
        document.getElementById("constant_id").value = "";
    }

    modal.show();
}

function saveConstant() {
    let name = document.getElementById("constant-name").value.trim();
    let value = document.getElementById("constant-value").value.trim();
    let id = document.getElementById("constant_id").value;

    if (!name || !value) {
        alert("All fields are required.");
        return false;
    }

    let url = id ? "/constants/update" : "/constants/create";
    let method = "POST";

    fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name, value })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let modal = bootstrap.Modal.getInstance(document.getElementById("editConstantModal"));
            modal.hide();
            $("#constants-table").bootstrapTable("refresh");
        } else {
            alert("Error: " + data.error);
        }
    });

    return false;
}

function deleteConstant(name) {
    if (confirm(`Are you sure you want to delete constant: ${name}?`)) {
        fetch("/constants/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                $("#constants-table").bootstrapTable("refresh");
            } else {
                alert("Error: " + data.error);
            }
        });
    }
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

$(document).on("click", "#copyTextBtn", function () {

    let text = $("#modalContent").text().trim();
    
    if (!text) {
        alert("Nothing to copy!");
        return;
    }

    navigator.clipboard.writeText(text).then(() => {
        alert("Copied to clipboard!");
    }).catch(err => {
        console.error("Failed to copy:", err);
        alert("Copy failed.");
    });
});


function truncateText(value, row, index) {
    if (!value) return '-'; // Handle empty values

    let maxLength = 50; // Set fixed truncation length
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



window.actionEvents = {
    'click .edit-btn': function (e, value, row, index) {
        openCredentialModal(index);
    },
    'click .delete-btn': function (e, value, row, index) {
        deleteCredential(row.name);
    }
};

function updateConstantTableFilters() {
    let search = document.getElementById("constant-search").value.trim();

    $("#constants-table").bootstrapTable("refresh", {
        query: { search: search }
    });
}
