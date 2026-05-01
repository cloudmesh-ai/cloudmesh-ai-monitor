window.MonitorTableConfig = {
    // Formatter for metrics to apply color based on thresholds
    metricFormatter: function(cell) {
        const val = cell.getValue();
        if (val === "N/A" || val === null) return `<span class="text-gray-400 dark:text-gray-600">${val}</span>`;
        
        const formatValue = (v) => {
            const num = parseFloat(v);
            if (isNaN(num)) return v;

            let colorClass = "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
            if (num > 85) {
                colorClass = "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 font-bold";
            } else if (num > 70) {
                colorClass = "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 font-semibold";
            }
            return `<span class="${colorClass} px-1.5 py-0.5 rounded-full text-[10px] font-medium mr-1">${v}</span>`;
        };

        if (Array.isArray(val)) {
            return val.map(v => formatValue(v)).join('');
        }

        if (typeof val === 'string' && val.includes(',')) {
            return val.split(',').map(v => formatValue(v.trim())).join('');
        }
        
        return formatValue(val);
    },

    getColumns: function() {
        return [
            { 
                title: "Actions", 
                width: 100, 
                hozAlign: "center", 
                headerSort: false,
                formatter: function(cell) {
                    const data = cell.getData();
                    const label = data.label;
                    const active = data.active;
                    return `
                        <div class="flex justify-center items-center gap-2">
                                <input type="checkbox" ${active ? 'checked' : ''} 
                                        onclick="event.stopPropagation()"
                                        onchange="window.MonitorTableConfig.toggleHostActive('${label}', this.checked)" 
                                        class="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer" 
                                        title="Active">
                            <button onclick="window.MonitorTableConfig.refreshHost('${label}')" class="p-1 hover:text-blue-500 transition-colors" title="Refresh">
                                 <i class="fa-solid fa-rotate"></i>
                            </button>
                            <button onclick="window.MonitorTableConfig.openTerminal('${label}')" class="p-1 hover:text-green-500 transition-colors" title="Terminal">
                                 <i class="fa-solid fa-terminal"></i>
                            </button>
                        </div>
                    `;
                }
            },
            { 
                title: "Status", 
                field: "last_probe_success", 
                width: 80, 
                hozAlign: "center", 
                formatter: function(cell) {
                    const val = cell.getValue();
                    return `<span class="status-circle ${val ? 'status-downloaded' : 'status-not-downloaded'}"></span>`;
                }
            },
            { title: "Label", field: "label", width: 180, formatter: (cell) => `<b>${cell.getValue()}</b>` },
            { title: "Hostname", field: "hostname", width: 220 },
            { title: "Who", field: "who", width: 280 },
            { 
                title: "Interval", 
                field: "refresh_interval", 
                width: 120, 
                hozAlign: "right", 
                editor: "number",
                formatter: (cell) => `${cell.getValue()}s`,
            },
            { title: "GPU Usage (%)", field: "gpu_usage", width: 200, hozAlign: "right", formatter: this.metricFormatter },
            { title: "GPU Temp", field: "gpu_temp", width: 200, hozAlign: "right", formatter: this.metricFormatter },
            { title: "Mem Usage (%)", field: "mem_usage", width: 200, hozAlign: "right", formatter: this.metricFormatter },
            { title: "CPU Usage (%)", field: "cpu_usage", width: 150, hozAlign: "right", formatter: this.metricFormatter },
            { title: "CPU Temp", field: "cpu_temp", width: 150, hozAlign: "right", formatter: this.metricFormatter },
            { title: "Last Updated", field: "last_updated", width: 220, hozAlign: "right" },
        ];
    },

    refreshHost: async function(label) {
        console.log(`[Monitor] Refreshing host: ${label}`);
        try {
            const res = await fetch(`/api/plugin/monitor/refresh_host?label=${encodeURIComponent(label)}`);
            const data = await res.json();
            if (data.success) {
                console.log(`[Monitor] Refresh successful for ${label}: ${data.message}`);
                // Trigger the panel to re-fetch data and update the table
                window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
            } else {
                console.error(`[Monitor] Refresh failed for ${label}: ${data.error}`);
                alert(`Refresh failed for ${label}: ${data.error}`);
            }
        } catch (e) {
            console.error(`[Monitor] Network error refreshing host ${label}:`, e);
            alert(`Network error while refreshing ${label}`);
        }
    },

    addHost: function() {
        if (window.openAddHostModal) {
            window.openAddHostModal();
        } else {
            console.error("[Monitor] openAddHostModal not found on window object");
            alert("Add Host modal is not available.");
        }
    },

    editHost: function(hostData) {
        if (window.openEditHostModal) {
            window.openEditHostModal(hostData);
        } else {
            console.error("[Monitor] openEditHostModal not found on window object");
            alert("Edit Host modal is not available.");
        }
    },

    toggleHostActive: async function(label, active) {
        const activeVal = active ? "true" : "false";
        console.log(`[Monitor] Toggling host ${label} active status to ${activeVal}`);
        try {
            const res = await fetch(`/api/plugin/monitor/update_host_active?label=${encodeURIComponent(label)}&active=${activeVal}`);
            if (!res.ok) {
                throw new Error(`Server responded with ${res.status}`);
            }
            const data = await res.json();
            if (!data.success) {
                console.error(`[Monitor] Failed to toggle active status for ${label}:`, data);
                alert(`Error: ${data.error || 'Unknown server error'}`);
                window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
            }
        } catch (e) {
            console.error(`[Monitor] Network error toggling active status for ${label}:`, e);
            alert(`Network error while updating active status: ${e.message}`);
            window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
        }
    },

    editHostsYaml: async function() {
        console.log(`[Monitor] Requesting to edit hosts.yaml`);
        try {
            const res = await fetch(`/api/plugin/monitor/edit_hosts`);
            const data = await res.json();
            if (data.success) {
                console.log(`[Monitor] hosts.yaml opened for editing: ${data.message}`);
            } else {
                console.error(`[Monitor] Failed to open hosts.yaml: ${data.error || 'Unknown error'}`);
                alert(`Error: ${data.error || 'Could not open hosts.yaml'}`);
            }
        } catch (e) {
            console.error(`[Monitor] Network error opening hosts.yaml:`, e);
            alert(`Failed to connect to server: ${e.message}`);
        }
    },

    openTerminal: async function(label) {
        console.log(`[Monitor] Requesting terminal for: ${label}`);
        try {
            const res = await fetch(`/api/plugin/monitor/open_terminal?label=${encodeURIComponent(label)}`);
            const data = await res.json();
            if (data.success) {
                console.log(`[Monitor] Terminal opened successfully: ${data.message}`);
            } else {
                console.error(`[Monitor] Failed to open terminal: ${data.error || 'Unknown error'}`);
                alert(`Error: ${data.error || 'Could not open terminal'}`);
            }
        } catch (e) {
            console.error(`[Monitor] Failed to request terminal for ${label}:`, e);
            alert(`Failed to connect to server: ${e.message}`);
        }
    },

    render: function(elementId, data) {
        try {
            if (typeof Tabulator === 'undefined') {
                throw new Error("Tabulator library is not loaded");
            }

            const container = document.querySelector(elementId);
            if (!container) throw new Error(`Element ${elementId} not found`);
            
            container.innerHTML = ''; 
            
            // Create Filter Bar
            const filterBar = document.createElement('div');
            filterBar.className = 'flex gap-4 p-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700';
            filterBar.innerHTML = `
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Search:</span>
                    <input type="text" id="monitor-search" class="px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white" placeholder="Filter hosts...">
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Exclude:</span>
                    <input type="text" id="monitor-exclude" class="px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white" placeholder="Exclude patterns...">
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Interval (s):</span>
                    <input type="number" id="monitor-interval" class="px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white w-20" placeholder="10">
                </div>
                <div class="ml-auto flex items-center gap-2">
                    <button onclick="window.MonitorTableConfig.addHost()" class="flex items-center gap-1 px-3 py-1 bg-primary text-white rounded text-xs font-bold hover:bg-blue-700 transition-colors">
                        <i class="fa-solid fa-plus"></i> Add Host
                    </button>
                    <button onclick="window.MonitorTableConfig.editHostsYaml()" class="flex items-center gap-1 px-3 py-1 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-xs font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors">
                        <i class="fa-solid fa-file-pen"></i> Edit hosts.yaml
                    </button>
                </div>
            `;
            
            const tableEl = document.createElement('div');
            tableEl.className = 'flex-1 h-full';
            
            container.appendChild(filterBar);
            container.appendChild(tableEl);
            
            const table = new Tabulator(tableEl, {
                data: data,
                layout: "fitDataFill",
                height: "100%",
                columns: this.getColumns(),
                rowClick: function(e, row) {
                    const label = row.getData().label;
                    if (window.showHostDetail) {
                        window.showHostDetail(label);
                    }
                },
                cellEdited: async (cell) => {
                    const field = cell.getField();
                    if (field === 'refresh_interval') {
                        const label = cell.getData().label;
                        const value = cell.getValue();
                        console.log(`[Monitor] Updating interval for ${label} to ${value}s`);
                        try {
                            const res = await fetch(`/api/plugin/monitor/update_host_interval?label=${encodeURIComponent(label)}&interval=${value}`);
                            if (res.ok) {
                                console.log(`[Monitor] Host interval updated successfully`);
                            }
                        } catch (e) {
                            console.error(`[Monitor] Failed to update host interval:`, e);
                        }
                    }
                },
            });

            const applyFilters = () => {
                const searchVal = document.getElementById('monitor-search')?.value || '';
                const excludeVal = document.getElementById('monitor-exclude')?.value || '';
                
                table.setFilter(function(data) {
                    const label = (data.label || '').toLowerCase();
                    const hostname = (data.hostname || '').toLowerCase();
                    const search = searchVal.toLowerCase();
                    const exclude = excludeVal.toLowerCase();
                    
                    if (exclude && (label.includes(exclude) || hostname.includes(exclude))) {
                        return false;
                    }
                    if (search && !(label.includes(search) || hostname.includes(search))) {
                        return false;
                    }
                    return true;
                });
            };

            container.addEventListener('input', async (e) => {
                if (e.target.id === 'monitor-search' || e.target.id === 'monitor-exclude') {
                    applyFilters();
                } else if (e.target.id === 'monitor-interval') {
                    const interval = e.target.value;
                    if (interval && !isNaN(interval)) {
                        try {
                            const res = await fetch(`/api/plugin/monitor/update_interval?interval=${interval}`);
                            if (res.ok) {
                                console.log(`[Monitor] Interval updated to ${interval}s`);
                                // Trigger a data refresh by calling the panel's loadMonitor if available
                                // Since we are in a config object, we can't easily call the Vue method, 
                                // but we can dispatch a custom event or just let the user know.
                                window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
                            }
                        } catch (err) {
                            console.error("[Monitor] Failed to update interval:", err);
                        }
                    }
                }
            });

            return table;
        } catch (e) {
            console.error("[MonitorTableConfig] Render error:", e);
            throw e;
        }
    }
};