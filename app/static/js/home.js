document.addEventListener("DOMContentLoaded", function() {
    fetch("/performance")
        .then(response => response.json())
        .then(data => {
            const ctx = document.getElementById("queuePerformanceChart").getContext("2d");

            function isDarkMode() {
                return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            }

            // Generate day names (including "Today" for the last label)
            const days = data.dates.map((date, index) => {
                const d = new Date(date);
                return (index === data.dates.length - 1) ? "Today" : d.toLocaleDateString('en-US', { weekday: 'long' });
            });

            function getTextColor() {
                return isDarkMode() ? "#ffffff" : "#000000";  // White in dark mode, black in light mode
            }

            // Determine the max value from the datasets
            const maxValue = Math.max(...data.success, ...data.failed);

            // Dynamic step size logic
            function getStepSize(max) {
                if (max <= 10) return 1; // Small numbers, step size of 1
            
                // Calculate step size based on the magnitude of max
                const magnitude = Math.pow(10, Math.floor(Math.log10(max))); 
                return magnitude / 2; // Adjust for better granularity (e.g., 5000 instead of 10000)
            }
            

            // Chart instance
            const chart = new Chart(ctx, {
                type: "bar",
                data: {
                    labels: days, 
                    datasets: [
                        {
                            label: "Successful",
                            data: data.success,
                            backgroundColor: "rgba(0, 200, 0, 0.7)",
                        },
                        {
                            label: "Failed",
                            data: data.failed,
                            backgroundColor: "rgba(200, 0, 0, 0.7)",
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { 
                            position: "top",
                            labels: { color: getTextColor() } // Dynamic legend color
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: getTextColor() } // Dynamic x-axis color
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: getTextColor(), // Dynamic y-axis color
                                stepSize: getStepSize(maxValue), // Dynamic step size
                                precision: 0 // Ensures whole numbers
                            }
                        }
                    }
                }
            });

            // Automatically update colors when theme changes
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                chart.options.plugins.legend.labels.color = getTextColor();
                chart.options.scales.x.ticks.color = getTextColor();
                chart.options.scales.y.ticks.color = getTextColor();
                chart.update();
            });
        })
        .catch(error => console.error("Error loading queue performance data:", error));
});
