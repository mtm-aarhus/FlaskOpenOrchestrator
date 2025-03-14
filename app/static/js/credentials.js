function actionFormatter(value, row, index) {
    return `
        <button class="btn btn-sm btn-primary edit-btn" onclick="openCredentialModal(${index})">
            <i class="bi bi-pencil-square"></i> Edit
        </button>
        <button class="btn btn-sm btn-danger delete-btn" onclick="deleteCredential('${row.name}')">
            <i class="bi bi-trash"></i> Delete
        </button>
    `;
}

function openCredentialModal(index = null) {

    let modal = new bootstrap.Modal(document.getElementById("editCredentialModal"));
    let form = document.getElementById("credentialForm");

    if (index !== null) {
        // Fetch row data from the table
        let row = $("#credentials-table").bootstrapTable("getData")[index];

        document.getElementById("credentialModalTitle").innerText = "Edit Credential";
        document.getElementById("credential_id").value = row.name;
        document.getElementById("credential-name").value = row.name;
        document.getElementById("credential-username").value = row.username;
        document.getElementById("credential-password").value = "••••••••";
        document.getElementById("credential-password").disabled = true;
        document.getElementById("change-password").checked = false;
        document.getElementById("password-eye-btn").style.display = 'inline'
        document.getElementById("change-password").style.display = 'inline'
        document.getElementById("change-password-text").style.display = 'inline'
    } else {
        document.getElementById("credentialModalTitle").innerText = "New Credential";
        form.reset();
        document.getElementById("credential-password").disabled = false; // Enable password field
        document.getElementById("password-eye-btn").style.display = 'none'
        document.getElementById("change-password").style.display = 'none'
        document.getElementById("change-password-text").style.display = 'none'
    }

    modal.show();
}

function saveCredential() {
    let name = document.getElementById("credential-name").value.trim();
    let username = document.getElementById("credential-username").value.trim();
    let password = document.getElementById("credential-password").value.trim();
    let id = document.getElementById("credential_id").value;
    let changePassword = document.getElementById("change-password").checked;

    if (!name || !username || (changePassword && !password)) {
        alert("All fields are required.");
        return false;
    }

    let url = id ? "/credentials/update" : "/credentials/create";

    fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name, username, password, change_password: changePassword })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let modal = bootstrap.Modal.getInstance(document.getElementById("editCredentialModal"));
            modal.hide();
            $("#credentials-table").bootstrapTable("refresh");
        } else {
            alert("Error: " + data.error);
        }
    });

    return false;
}


function deleteCredential(name) {
    if (!confirm(`Are you sure you want to delete credential: ${name}?`)) return;

    fetch("/credentials/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            $("#credentials-table").bootstrapTable("refresh");
        } else {
            alert("Error: " + data.error);
        }
    });
}


function passwordFormatter(value, row) {
    return `
        <button class="btn btn-sm btn-secondary" onclick="askDecryptionKey('${row.name}', 'table')">
            <i class="bi bi-eye"></i> View
        </button>
    `;
}

function askDecryptionKey(name, type) {
    let key = prompt("Enter decryption key:");
    if (!key) return; // If user cancels, do nothing

    promptDecryptPassword(name, key, type);
}

function promptDecryptPassword(name, key, type) {
    fetch("/credentials/decrypt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, key })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let passwordField = document.getElementById("decrypted-password");
            let modalElement = document.getElementById("viewPasswordModal");

            if (!passwordField || !modalElement) {
                console.error("❌ Missing elements for password modal!");
                return;
            }
            if (type === 'table') {
                passwordField.value = data.password; 
                let modal = new bootstrap.Modal(modalElement);
                modal.show();  
            }
            else {
                document.getElementById("credential-password").value = data.password;
            }


        } else {
            alert("Error: " + data.error);
        }
    })
    .catch(error => {
        console.error("Error decrypting password:", error);
        alert("Failed to decrypt password.");
    });
}

function decryptPassword() {
    let key = document.getElementById("decrypt-key").value;
    let name = document.getElementById("decryptPasswordModal").getAttribute("data-name");

    fetch("/credentials/decrypt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, key })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Decrypted password: " + data.password);
        } else {
            alert("Error: " + data.error);
        }
    });
}

function togglePasswordField() {
    let passwordField = document.getElementById("credential-password");
    let changePasswordCheckbox = document.getElementById("change-password");
    let eyeButton = document.getElementById("password-eye-btn");  

    if (changePasswordCheckbox.checked) {
        passwordField.disabled = false;
        passwordField.type =  "password"
        passwordField.value = ""; 
        eyeButton.style.display = "none"; 
    } else {
        passwordField.disabled = true;
        passwordField.value = "••••••••";
        eyeButton.style.display = "inline"; 
    }
}


function togglePasswordVisibility() {
    let passwordField = document.getElementById("credential-password");
    let eyeIcon = document.getElementById("password-eye-icon");

    if (passwordField.type === "password") {
        askDecryptionKey(document.getElementById("credential-name").value)

        passwordField.type = "text";
        eyeIcon.classList.replace("bi-eye", "bi-eye-slash");
    } else {
        passwordField.type = "password";
        eyeIcon.classList.replace("bi-eye-slash", "bi-eye");
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

window.actionEvents = {
    'click .edit-btn': function (e, value, row, index) {
        openCredentialModal(index);
    },
    'click .delete-btn': function (e, value, row, index) {
        deleteCredential(row.name);
    }
};

function updateCredentialTableFilters() {
    let search = document.getElementById("credential-search").value.trim();

    $("#credentials-table").bootstrapTable("refresh", {
        query: { search: search }
    });
}

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


function copyPassword() {
    var passwordField = document.getElementById("decrypted-password");
    passwordField.select();
    passwordField.setSelectionRange(0, 99999); // For mobile devices

    navigator.clipboard.writeText(passwordField.value).then(() => {
        alert("Copied to clipboard!");
        var copyBtn = document.getElementById("copy-password-btn");
        copyBtn.innerHTML = '<i class="bi bi-check-lg"></i> Copied!';
        setTimeout(() => {
            copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy password:', err);
    });
}