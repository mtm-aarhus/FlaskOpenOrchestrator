// Measure the fixed footer's actual height and expose it as a CSS variable so
// fixed-position elements (e.g. .bulk-actions-bar) can sit flush above it.
function syncFooterHeightVar() {
    const footer = document.querySelector("footer.footer-fixed");
    if (!footer) return;
    // Use sub-pixel precision (no rounding) so the bulk bar sits flush with
    // the footer at any browser zoom level (75% etc. produce fractional heights).
    const h = footer.getBoundingClientRect().height;
    document.documentElement.style.setProperty("--footer-height", `${h}px`);
}
document.addEventListener("DOMContentLoaded", () => {
    syncFooterHeightVar();
    // The footer's scheduler chips load asynchronously and can change height;
    // re-measure once after a short delay, plus on resize.
    setTimeout(syncFooterHeightVar, 1500);
    window.addEventListener("resize", syncFooterHeightVar);
});

// Toast notifications. Replaces blocking alert() everywhere.
//   showToast("Saved", "success")
//   showToast("Failed: " + err, "error")
//   showToast("Heads up", "warning")
//   showToast("Did the thing", "info")    // default
window.showToast = function (message, kind) {
    kind = kind || "info";
    const palette = {
        success: { cls: "text-bg-success", icon: "bi-check-circle-fill" },
        error:   { cls: "text-bg-danger",  icon: "bi-x-octagon-fill" },
        warning: { cls: "text-bg-warning", icon: "bi-exclamation-triangle-fill" },
        info:    { cls: "text-bg-primary", icon: "bi-info-circle-fill" },
    };
    const p = palette[kind] || palette.info;
    const container = document.getElementById("toast-container");
    if (!container || typeof bootstrap === "undefined") {
        // Fallback before bootstrap is loaded — use console + alert for errors only.
        console[kind === "error" ? "error" : "log"]("[toast]", message);
        if (kind === "error") alert(message);
        return;
    }
    const id = "toast-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);
    const html = `
        <div id="${id}" class="toast align-items-center ${p.cls} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body"><i class="bi ${p.icon} me-2"></i>${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>`;
    container.insertAdjacentHTML("beforeend", html);
    const el = document.getElementById(id);
    const t = new bootstrap.Toast(el, { delay: kind === "error" ? 6000 : 3000 });
    t.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
};

// Briefly flash a row when something about it changes during a silent refresh.
//   flashRow("#trigger-table", "<row-id>")
window.flashRow = function (tableSelector, rowId) {
    if (rowId == null) return;
    const $row = $(`${tableSelector} tr[data-uniqueid='${rowId}']`);
    if (!$row.length) return;
    $row.addClass("flash-row");
    setTimeout(() => $row.removeClass("flash-row"), 1500);
};

// Watch a bootstrap-table for per-row changes between refreshes. The fingerprint
// callback returns a value (e.g. row.process_status) that, if changed since the
// previous render, triggers a flash on that row.
//   watchRowChanges("#trigger-table", row => row.process_status);
// The table must have data-unique-id="id".
window.watchRowChanges = function (tableSelector, fingerprint) {
    let prev = new Map();
    let firstRender = true;
    $(document).on("post-body.bs.table", tableSelector, function () {
        const rows = $(this).bootstrapTable("getData");
        const next = new Map();
        rows.forEach(r => next.set(r.id, fingerprint(r)));
        if (!firstRender) {
            for (const [id, fp] of next) {
                if (prev.has(id) && prev.get(id) !== fp) {
                    window.flashRow(tableSelector, id);
                }
            }
        }
        prev = next;
        firstRender = false;
    });
};

// Polite auto-refresh helper. Pages opt in via window.startAutoRefresh(...).
//
// Refresh is paused while:
//   - the tab is hidden (document.visibilityState === 'hidden')
//   - any Bootstrap modal is open
//   - any input/textarea/select inside the page has focus (don't yank what the user is typing into)
window.startAutoRefresh = function (intervalMs, doRefresh) {
    function shouldRefresh() {
        if (document.visibilityState === "hidden") return false;
        if (document.querySelector(".modal.show")) return false;
        const focused = document.activeElement;
        if (focused && /^(INPUT|TEXTAREA|SELECT)$/.test(focused.tagName)) return false;
        return true;
    }
    setInterval(() => {
        if (shouldRefresh()) {
            try { doRefresh(); } catch (_) { /* swallow */ }
        }
    }, intervalMs);
};

// Per-table view preferences — stored in this browser only (localStorage).
// Loaded BEFORE bootstrap-table inits, so the saved page size is respected on
// first render. There is NO automatic save on user interaction; prefs change
// only via the Preferences modal in the navbar.

(function () {
    const PREFIX = "tablePref:";
    const k = (id, name) => `${PREFIX}${id}:${name}`;

    // Friendly labels per table id, in nav order. Added entries here automatically
    // appear in the Preferences modal.
    const TABLES = [
        { id: "trigger-table",         label: "Triggers" },
        { id: "queues-overview-table", label: "Queues (overview)" },
        { id: "queues-table",          label: "Queue elements (per queue)" },
        { id: "logs-overview-table",   label: "Logs (overview by process)" },
        { id: "logs-table",            label: "Log entries (per process / all)" },
        { id: "jobs-table",            label: "Jobs" },
        { id: "job-logs-table",        label: "Job logs (per job)" },
        { id: "scheduler-table",       label: "Schedulers" },
        { id: "constants-table",       label: "Constants" },
        { id: "credentials-table",     label: "Credentials" },
    ];

    const PAGE_SIZE_CHOICES = ["default", 10, 25, 50, 100, 1000, "all"];

    // Apply stored prefs BEFORE bootstrap-table auto-inits. Mutating
    // data-page-size on the <table> means bootstrap-table picks it up natively.
    $(function () {
        $("table[data-toggle='table']").each(function () {
            if (!this.id) return;
            const ps = localStorage.getItem(k(this.id, "pageSize"));
            if (ps && ps !== "default") this.setAttribute("data-page-size", ps);
        });
    });

    // Expose helpers for the Preferences modal.
    window.openPrefsModal = function () {
        const tbody = document.getElementById("prefs-table-body");
        if (!tbody) return;
        tbody.innerHTML = TABLES.map(t => {
            const stored = localStorage.getItem(k(t.id, "pageSize")) || "default";
            const opts = PAGE_SIZE_CHOICES.map(c => {
                const label = c === "default" ? "Default" : (c === "all" ? "All" : c);
                const value = c === "default" ? "" : String(c);
                return `<option value="${value}" ${String(stored) === String(value) || (stored === "default" && c === "default") ? "selected" : ""}>${label}</option>`;
            }).join("");
            return `
                <tr data-table-id="${t.id}">
                    <td>${t.label}</td>
                    <td>
                        <select class="form-select form-select-sm pref-pagesize">
                            ${opts}
                        </select>
                    </td>
                </tr>`;
        }).join("");
    };

    window.savePrefs = function () {
        document.querySelectorAll("#prefs-table-body tr").forEach(tr => {
            const id = tr.dataset.tableId;
            const sel = tr.querySelector(".pref-pagesize");
            if (!sel) return;
            const val = sel.value;
            if (val) {
                localStorage.setItem(k(id, "pageSize"), val);
            } else {
                localStorage.removeItem(k(id, "pageSize"));
            }
        });
        const modal = bootstrap.Modal.getInstance(document.getElementById("prefsModal"));
        if (modal) modal.hide();
        // The new defaults take effect on the next page load. Reload now so it's
        // immediately visible if the user is on a table page.
        location.reload();
    };

    window.resetAllPrefs = function () {
        if (!confirm("Clear all saved table preferences?")) return;
        Object.keys(localStorage)
            .filter(key => key.startsWith(PREFIX))
            .forEach(key => localStorage.removeItem(key));
        // Also clean up the older prefix used in earlier versions.
        Object.keys(localStorage)
            .filter(key => key.startsWith("tableSetting:"))
            .forEach(key => localStorage.removeItem(key));
        const modal = bootstrap.Modal.getInstance(document.getElementById("prefsModal"));
        if (modal) modal.hide();
        location.reload();
    };

    // Populate modal contents whenever it's about to be shown.
    document.addEventListener("DOMContentLoaded", function () {
        const modal = document.getElementById("prefsModal");
        if (modal) modal.addEventListener("show.bs.modal", openPrefsModal);
    });
})();
