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
                width: 140, 
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
                            <div class="flex items-center">
                                <button onclick="window.MonitorTableConfig.refreshHost('${label}')" class="p-1 hover:text-blue-500 transition-colors" title="Refresh">
                                     <i class="fa-solid fa-rotate"></i>
                                </button>
                            </div>
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
                    const data = cell.getData();
                    if (data.probing) {
                        return `
                            <div class="flex justify-center items-center">
                                <span class="probe-pulse" title="Probing now..."></span>
                            </div>`;
                    }
                    
                    const lastUpdated = data.last_updated;
                    if (!lastUpdated || lastUpdated === "N/A") {
                        return `<span class="status-circle status-stale"></span>`;
                    }

                    try {
                        const lastDate = new Date(lastUpdated);
                        const now = new Date();
                        const diffSeconds = (now - lastDate) / 1000;
                        const statusClass = diffSeconds <= 10 ? 'status-fresh' : 'status-stale';
                        return `<span class="status-circle ${statusClass}"></span>`;
                    } catch (e) {
                        return `<span class="status-circle status-stale"></span>`;
                    }
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
            { 
                title: "Last Updated", 
                field: "last_updated", 
                width: 220, 
                hozAlign: "right",
                formatter: function(cell) {
                    const val = cell.getValue();
                    return `
                        <div class="flex justify-end items-center gap-1">
                            <span>${val}</span>
                        </div>
                    `;
                }
            },
        ];
    },

    refreshHost: async function(label) {
        this.log(`Refreshing host: ${label}`);
        try {
            const res = await fetch(`/api/plugin/monitor/refresh_host?label=${encodeURIComponent(label)}`);
            const data = await res.json();
            if (data.success) {
                this.log(`Refresh successful for ${label}: ${data.message}`);
                // Trigger the panel to re-fetch data and update the table
                window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
            } else {
                this.log(`Refresh failed for ${label}: ${data.error}`, 'error');
            }
        } catch (e) {
            this.log(`Network error refreshing host ${label}: ${e.message}`, 'error');
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
        this.log(`Toggling host ${label} active status to ${activeVal}`);
        try {
            const res = await fetch(`/api/plugin/monitor/update_host_active?label=${encodeURIComponent(label)}&active=${activeVal}`);
            if (!res.ok) {
                throw new Error(`Server responded with ${res.status}`);
            }
            const data = await res.json();
            if (!data.success) {
                this.log(`Failed to toggle active status for ${label}: ${data.error || 'Unknown server error'}`, 'error');
                window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
            }
        } catch (e) {
            this.log(`Network error toggling active status for ${label}: ${e.message}`, 'error');
            window.dispatchEvent(new CustomEvent('monitor-interval-updated'));
        }
    },

    editHostsYaml: async function() {
        this.log(`Requesting to edit hosts.yaml`);
        try {
            const res = await fetch(`/api/plugin/monitor/edit_hosts`);
            const data = await res.json();
            if (data.success) {
                this.log(`hosts.yaml opened for editing: ${data.message}`);
            } else {
                this.log(`Failed to open hosts.yaml: ${data.error || 'Unknown error'}`, 'error');
            }
        } catch (e) {
            this.log(`Network error opening hosts.yaml: ${e.message}`, 'error');
        }
    },

    openTerminal: async function(label) {
        this.log(`Requesting terminal for: ${label}`);
        try {
            const res = await fetch(`/api/plugin/monitor/open_terminal?label=${encodeURIComponent(label)}`);
            const data = await res.json();
            if (data.success) {
                this.log(`Terminal opened successfully: ${data.message}`);
            } else {
                this.log(`Failed to open terminal: ${data.error || 'Unknown error'}`, 'error');
            }
        } catch (e) {
            this.log(`Network error opening terminal for ${label}: ${e.message}`, 'error');
        }
    },

    // Store original console methods to avoid infinite recursion during monkey-patching
    _originalLog: console.log,
    _originalError: console.error,

    toggleErrorPanel: function() {
        const panel = document.getElementById('monitor-error-panel');
        const logs = document.getElementById('monitor-error-logs');
        const icon = document.getElementById('monitor-error-toggle-icon');
        
        if (!panel || !logs || !icon) return;

        const isMinimized = logs.classList.toggle('hidden');
        
        if (isMinimized) {
            panel.className = 'h-auto overflow-hidden bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono text-xs p-2 border-t border-gray-200 dark:border-gray-700';
            icon.className = 'fa-solid fa-chevron-down text-gray-400 dark:text-gray-500 transition-transform';
        } else {
            panel.className = 'h-40 overflow-y-auto bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono text-xs p-2 border-t border-gray-200 dark:border-gray-700';
            icon.className = 'fa-solid fa-chevron-up text-gray-400 dark:text-gray-500 transition-transform';
        }
    },

    log: function(message, level = 'info') {
        const logsContainer = document.getElementById('monitor-error-logs');
        
        const timestamp = new Date().toLocaleTimeString();
        const colorClass = level === 'error' ? 'text-red-500 dark:text-red-400' : 'text-gray-600 dark:text-gray-300';
        const levelLabel = level === 'error' ? '[ERROR]' : '[INFO]';
        
        if (logsContainer) {
            const logEntry = document.createElement('div');
            logEntry.className = `mb-1 ${colorClass}`;
            logEntry.innerHTML = `<span class="text-gray-400 mr-2">${timestamp}</span><span class="font-bold mr-2">${levelLabel}</span>${message}`;
            logsContainer.appendChild(logEntry);
            
            // Keep only the last 100 messages
            while (logsContainer.children.length > 100) {
                logsContainer.removeChild(logsContainer.firstChild);
            }
            
            const panel = document.getElementById('monitor-error-panel');
            if (panel) panel.scrollTop = panel.scrollHeight;
        }

        if (level === 'error') {
            this._originalError(`[Monitor] ${message}`);
        } else {
            this._originalLog(`[Monitor] ${message}`);
        }
    },

    pollLogs: async function() {
        try {
            const res = await fetch('/api/plugin/monitor/logs');
            if (!res.ok) return;
            const logs = await res.json();
            
            if (!logs || logs.length === 0) return;

            const panel = document.getElementById('monitor-error-panel');
            if (!panel) return;

            // If panel only has the header, just add all current logs
            if (panel.children.length <= 1) {
                logs.forEach(log => {
                    const level = log.toLowerCase().includes('error') || log.toLowerCase().includes('fail') ? 'error' : 'info';
                    this.log(log, level);
                });
                return;
            }

            // Get the text of the last log entry
            const lastEl = panel.lastElementChild;
            const lastLogContent = lastEl.lastChild ? lastEl.lastChild.textContent : "";

            // Find the index of the last log content in the server logs
            // We use a simple includes check because server logs might not have the exact same formatting as UI logs
            const startIndex = logs.findIndex(log => log.includes(lastLogContent) && lastLogContent !== "");
            
            let newLogs = [];
            if (startIndex === -1) {
                // If we can't find the last log, it might be a server restart or buffer wrap.
                // Append only the most recent logs to avoid duplicating the entire history.
                newLogs = logs.slice(-10); 
            } else {
                newLogs = logs.slice(startIndex + 1);
            }

            newLogs.forEach(log => {
                const level = log.toLowerCase().includes('error') || log.toLowerCase().includes('fail') ? 'error' : 'info';
                this.log(log, level);
            });
        } catch (e) {
            // Silently fail polling
        }
    },

    render: function(elementId, data) {
        try {
            if (typeof Tabulator === 'undefined') {
                throw new Error("Tabulator library is not loaded");
            }

            const container = document.querySelector(elementId);
            if (!container) throw new Error(`Element ${elementId} not found`);
            
            // 1. Ensure the persistent layout exists
            let mainWrapper = container.querySelector('.monitor-main-wrapper');
            if (!mainWrapper) {
                container.innerHTML = ''; 
                mainWrapper = document.createElement('div');
                mainWrapper.className = 'monitor-main-wrapper flex flex-col h-full w-full';
                container.appendChild(mainWrapper);
                
                // Start polling only once
                setInterval(() => this.pollLogs(), 2000);
            }

            // Ensure the Error Panel exists and has the toggle mechanism
            let errorPanel = document.getElementById('monitor-error-panel');
            if (!errorPanel) {
                errorPanel = document.createElement('div');
                errorPanel.id = 'monitor-error-panel';
                errorPanel.className = 'h-40 overflow-y-auto bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono text-xs p-2 border-t border-gray-200 dark:border-gray-700';
                mainWrapper.appendChild(errorPanel);
            }

            if (!document.getElementById('monitor-error-header')) {
                // Clear existing content to rebuild with header/container structure
                errorPanel.innerHTML = '';
                
                const header = document.createElement('div');
                header.id = 'monitor-error-header';
                header.className = 'flex items-center justify-between cursor-pointer mb-1 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors';
                header.onclick = () => this.toggleErrorPanel();
                header.innerHTML = `
                    <span class="text-gray-500 dark:text-gray-400 font-semibold uppercase text-[10px] tracking-wider">System logs</span>
                    <i id="monitor-error-toggle-icon" class="fa-solid fa-chevron-up text-gray-400 dark:text-gray-500 transition-transform"></i>
                `;
                
                const logsContainer = document.createElement('div');
                logsContainer.id = 'monitor-error-logs';
                
                errorPanel.appendChild(header);
                errorPanel.appendChild(logsContainer);
            }

            // 2. Update the Content Wrapper (Table + Filter)
            let contentWrapper = mainWrapper.querySelector('.monitor-content-wrapper');
            if (contentWrapper) {
                contentWrapper.remove();
            }
            contentWrapper = document.createElement('div');
            contentWrapper.className = 'monitor-content-wrapper flex-1 overflow-hidden flex flex-col';

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
            
            contentWrapper.appendChild(filterBar);
            contentWrapper.appendChild(tableEl);
            
            // Always insert contentWrapper at the top of mainWrapper
            mainWrapper.prepend(contentWrapper);
            
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

// Monkey-patch console.log and console.error to duplicate output to the Error Panel
(function() {
    const originalLog = window.MonitorTableConfig._originalLog;
    const originalError = window.MonitorTableConfig._originalError;

    console.log = function(...args) {
        const message = args.map(arg => 
            typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
        ).join(' ');
        
        if (window.MonitorTableConfig && window.MonitorTableConfig.log) {
            window.MonitorTableConfig.log(message, 'info');
        }
        originalLog.apply(console, args);
    };

    console.error = function(...args) {
        const message = args.map(arg => 
            typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
        ).join(' ');
        
        if (window.MonitorTableConfig && window.MonitorTableConfig.log) {
            window.MonitorTableConfig.log(message, 'error');
        }
        originalError.apply(console, args);
    };
})();
