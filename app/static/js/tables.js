// Persist per-table view settings (page size, sort) in localStorage.
// Keyed by table id. Loaded BEFORE bootstrap-table so $(document).ready runs first.
(function () {
    const PREFIX = "tableSetting:";
    const k = (id, name) => `${PREFIX}${id}:${name}`;

    // Apply stored settings BEFORE bootstrap-table auto-inits.
    // We mutate data-page-size etc. attributes on the <table> so bootstrap-table
    // picks them up natively when it initializes.
    $(function () {
        $("table[data-toggle='table']").each(function () {
            if (!this.id) return;
            const ps = localStorage.getItem(k(this.id, "pageSize"));
            if (ps) this.setAttribute("data-page-size", ps);
            const sn = localStorage.getItem(k(this.id, "sortName"));
            const so = localStorage.getItem(k(this.id, "sortOrder"));
            if (sn) this.setAttribute("data-sort-name", sn);
            if (so) this.setAttribute("data-sort-order", so);
        });
    });

    // Save changes (delegated, so it works regardless of when tables init).
    $(document).on("page-change.bs.table", "table[data-toggle='table']", function (_e, _page, size) {
        if (this.id) localStorage.setItem(k(this.id, "pageSize"), String(size));
    });

    $(document).on("sort.bs.table", "table[data-toggle='table']", function (_e, name, order) {
        if (!this.id) return;
        localStorage.setItem(k(this.id, "sortName"), name);
        localStorage.setItem(k(this.id, "sortOrder"), order);
    });
})();
