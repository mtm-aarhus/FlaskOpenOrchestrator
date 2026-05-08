document.addEventListener("DOMContentLoaded", function () {
  fetch("/performance")
    .then((r) => r.json())
    .then((data) => {
      function isDarkMode() {
        return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      }
      function getTextColor() {
        return isDarkMode() ? "#ffffff" : "#000000";
      }

      const days = (data.dates || []).map((date, index) => {
        const d = new Date(date);
        return index === data.dates.length - 1 ? "Today" : d.toLocaleDateString("en-US", { weekday: "long" });
      });

      function niceStep(rawStep) {
        if (rawStep <= 0) return 1;
        const exp = Math.floor(Math.log10(rawStep));
        const base = Math.pow(10, exp);
        const frac = rawStep / base;

        let niceFrac;
        if (frac <= 1) niceFrac = 1;
        else if (frac <= 2) niceFrac = 2;
        else if (frac <= 5) niceFrac = 5;
        else niceFrac = 10;

        return niceFrac * base;
      }

      function computeAxis(values, { targetTicks = 6, bufferFactor = 1.15 } = {}) {
        const maxVal = Math.max(0, ...values.map((v) => Number(v) || 0));
        const buffered = maxVal === 0 ? 1 : Math.ceil(maxVal * bufferFactor);
        const step = niceStep(buffered / (targetTicks - 1));
        const max = Math.ceil(buffered / step) * step;
        return { step, max };
      }

      function makeChart(canvasId, label, series, rgba, kind /* "failed" | "success" */) {
        const el = document.getElementById(canvasId);
        if (!el) return null;

        const { step, max } = computeAxis(series);

        return new Chart(el.getContext("2d"), {
          type: "bar",
          data: {
            labels: days,
            datasets: [{ label, data: series, backgroundColor: rgba }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            // Drill into the queue overview for the clicked day, filtered by status.
            onClick: (_evt, elements) => {
              if (!elements.length) return;
              const idx = elements[0].index;
              const dayIso = (data.dates || [])[idx];
              if (!dayIso) return;
              const params = new URLSearchParams({
                start_date: `${dayIso}T00:00`,
                end_date:   `${dayIso}T23:59`,
                has_failed: kind === "failed" ? "true" : "false",
                has_done:   kind === "success" ? "true" : "false",
              });
              window.location.href = `/queues/?${params.toString()}`;
            },
            onHover: (evt, elements) => {
              evt.native.target.style.cursor = elements.length ? "pointer" : "default";
            },
            plugins: {
              legend: { position: "top", labels: { color: getTextColor() } },
            },
            scales: {
              x: { ticks: { color: getTextColor() } },
              y: {
                beginAtZero: true,
                max,
                ticks: { color: getTextColor(), stepSize: step, precision: 0 },
              },
            },
          },
        });
      }

      const failedChart = makeChart(
        "queuePerformanceFailedChart",
        "Failed",
        data.failed || [],
        "rgba(200, 0, 0, 0.7)",
        "failed"
      );

      const successChart = makeChart(
        "queuePerformanceSuccessChart",
        "Successful",
        data.success || [],
        "rgba(0, 200, 0, 0.7)",
        "success"
      );

      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        [failedChart, successChart].forEach((chart) => {
          if (!chart) return;
          chart.options.plugins.legend.labels.color = getTextColor();
          chart.options.scales.x.ticks.color = getTextColor();
          chart.options.scales.y.ticks.color = getTextColor();
          chart.update();
        });
      });
    })
    .catch((e) => console.error("Error loading queue performance data:", e));

  // Auto-refresh every 30s so the failure / done KPIs stay current.
  // The shared helper (tables.js) pauses while a modal is open, the tab is hidden,
  // or any input has focus — so a casual scroll won't get yanked away.
  if (typeof window.startAutoRefresh === "function") {
      window.startAutoRefresh(30000, () => location.reload());
  }
});
