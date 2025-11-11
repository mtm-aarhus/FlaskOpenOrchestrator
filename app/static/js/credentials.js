let hasDecryptionAccess = null;

if (sessionStorage.getItem("hasAccess") === "true") {
    hasDecryptionAccess = true;
}

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

let challengeInProgress = false;

async function askDecryptionKey(name, type) {
    if (challengeInProgress) return;
    challengeInProgress = true;

    try {
        // Step 1️⃣: request challenge from server
        const res = await fetch("/credentials/check_access_challenge");
        const { challenge } = await res.json();
        if (!challenge) throw new Error("No challenge received");

        // Step 2️⃣: Try to decrypt a locally stored encrypted key (if exists)
        let key = null;
        if (localStorage.getItem("EncryptedOpenOrchestratorKey")) {
            key = await decryptStoredKey("browser-session"); // your encryption password
        }

        // Step 3️⃣: If not available, ask user for key and encrypt for next time
        if (!key) {
            key = prompt("Enter decryption key:");
            if (!key) return;
            await encryptKey(key, "browser-session"); // store encrypted key
        }

        // Step : Compute hash(challenge + key)
        const hashBuffer = await crypto.subtle.digest(
            "SHA-256",
            new TextEncoder().encode(challenge + key)
        );
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");

        // Step 5️⃣: Verify with server
        const verifyRes = await fetch("/credentials/check_access_challenge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hash: hashHex })
        });

        const verifyData = await verifyRes.json();

        if (verifyData.authorized) {
            hasDecryptionAccess = true;
            sessionStorage.setItem("hasAccess", "true");
            console.log("Key verified and stored securely.");
            promptDecryptPassword(name, key, type);
        } else {
            alert("Invalid key, please try again.");
            // optional: clear corrupted cache
            localStorage.removeItem("EncryptedOpenOrchestratorKey");
        }

    } catch (err) {
        console.error("Key verification failed:", err);
        alert("Key verification failed.");
    } finally {
        challengeInProgress = false;
    }
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
            if (type === "table") {
                let passwordField = document.getElementById("decrypted-password");
                passwordField.value = data.password; 
                new bootstrap.Modal(document.getElementById("viewPasswordModal")).show();
            } else {
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



async function encryptKey(plainKey, password) {
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        "raw",
        enc.encode(password),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
    );

    const salt = crypto.getRandomValues(new Uint8Array(16));
    const derivedKey = await crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: 100000,
            hash: "SHA-256",
        },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
    );

    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv },
        derivedKey,
        enc.encode(plainKey)
    );

    // Store everything together (salt + iv + ciphertext)
    const encryptedData = {
        salt: Array.from(salt),
        iv: Array.from(iv),
        data: Array.from(new Uint8Array(ciphertext))
    };
    localStorage.setItem("EncryptedOpenOrchestratorKey", JSON.stringify(encryptedData));
}

async function decryptStoredKey(password) {
    const stored = localStorage.getItem("EncryptedOpenOrchestratorKey");
    if (!stored) return null;

    const { salt, iv, data } = JSON.parse(stored);
    const enc = new TextEncoder();
    const dec = new TextDecoder();

    const keyMaterial = await crypto.subtle.importKey(
        "raw",
        enc.encode(password),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
    );

    const derivedKey = await crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: new Uint8Array(salt),
            iterations: 100000,
            hash: "SHA-256",
        },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        true,
        ["decrypt"]
    );

    try {
        const decrypted = await crypto.subtle.decrypt(
            { name: "AES-GCM", iv: new Uint8Array(iv) },
            derivedKey,
            new Uint8Array(data)
        );
        return dec.decode(decrypted);
    } catch {
        alert("Failed to decrypt stored key — wrong password?");
        return null;
    }
}
