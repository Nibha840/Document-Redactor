document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const fileCard = document.getElementById('file-card');
    const selectedFileName = document.getElementById('selected-file-name');
    const selectedFileSize = document.getElementById('selected-file-size');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const processBtn = document.getElementById('process-btn');
    const redactNonPiiInput = document.getElementById('redact-non-pii');
    
    const controlPanel = document.querySelector('.control-panel');
    const loadingState = document.getElementById('loading-state');
    const loadingMsg = document.getElementById('loading-msg');
    const progressFill = document.getElementById('progress-fill');
    const loadingLogs = document.getElementById('loading-logs');
    
    const resultsPanel = document.getElementById('results-panel');
    const statTotal = document.getElementById('stat-total');
    const statTypes = document.getElementById('stat-types');
    const statTime = document.getElementById('stat-time');
    const barChart = document.getElementById('bar-chart');
    const auditTableBody = document.getElementById('audit-table-body');
    const auditSearch = document.getElementById('audit-search');
    
    const downloadDocBtn = document.getElementById('download-doc-btn');
    const downloadJsonBtn = document.getElementById('download-json-btn');
    const resetAppBtn = document.getElementById('reset-app-btn');

    let currentFile = null;
    let serverResponse = null;

    // --- File Drag & Drop Events ---
    // Make the entire drop zone clickable
    dropZone.addEventListener('click', (e) => {
        if (e.target !== fileInput) {
            fileInput.click();
        }
    });
    fileInput.addEventListener('change', (e) => handleFileSelection(e.target.files[0]));

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'));
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    removeFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetFileSelection();
    });

    function handleFileSelection(file) {
        if (!file) return;
        
        // Validate file extension
        if (!file.name.endsWith('.docx')) {
            alert('Invalid file format. Please upload a Microsoft Word (.docx) document.');
            return;
        }

        currentFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        
        dropZone.style.display = 'none';
        fileCard.style.display = 'flex';
    }

    function resetFileSelection() {
        currentFile = null;
        fileInput.value = '';
        dropZone.style.display = 'flex';
        fileCard.style.display = 'none';
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // --- Redaction Processing ---
    processBtn.addEventListener('click', async () => {
        if (!currentFile) return;

        // Transition: Hide inputs, show loader
        controlPanel.style.display = 'none';
        loadingState.style.display = 'flex';
        resultsPanel.style.display = 'none';
        
        // Reset loader elements
        progressFill.style.width = '5%';
        loadingLogs.innerHTML = '';
        addLog('Uploading document to server...');

        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('redact_non_pii', redactNonPiiInput.checked);

        // Simulation logs intervals
        const simulatedLogs = [
            { t: 800, text: 'Initializing NLP detection pipeline (Regex + spaCy)...', progress: 15 },
            { t: 1500, text: 'Loading Microsoft Presidio Analyzer Engine...', progress: 30 },
            { t: 2200, text: 'Running Layer 1 & 2 detection models over text runs...', progress: 45 },
            { t: 3000, text: 'Merging multi-layer entity outputs and resolving overlaps...', progress: 60 },
            { t: 3800, text: 'Parsing DOCX structure (paragraphs, tables, cells)...', progress: 75 },
            { t: 4500, text: 'Replacing sensitive text with consistent fake values...', progress: 90 },
            { t: 5200, text: 'Finalizing formatting preservation checks...', progress: 95 }
        ];

        simulatedLogs.forEach(item => {
            setTimeout(() => {
                if (loadingState.style.display !== 'none') {
                    addLog(item.text);
                    progressFill.style.width = `${item.progress}%`;
                }
            }, item.t);
        });

        try {
            const response = await fetch('/redact', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Server error occurred during redaction');
            }

            serverResponse = await response.json();
            
            // Set progress to complete
            progressFill.style.width = '100%';
            addLog('Successfully redacted document!', true);
            
            setTimeout(() => {
                renderDashboard(serverResponse);
            }, 500);

        } catch (err) {
            console.error(err);
            addLog(`Error: ${err.message}`, false, true);
            loadingMsg.textContent = 'Process Failed';
            progressFill.style.backgroundColor = 'var(--red)';
            
            // Show reset button in loader to return
            const resetBtn = document.createElement('button');
            resetBtn.className = 'btn btn-primary btn-full';
            resetBtn.style.marginTop = '1.5rem';
            resetBtn.innerHTML = '<i class="fa-solid fa-arrow-left"></i> Go Back';
            resetBtn.addEventListener('click', () => {
                controlPanel.style.display = 'block';
                loadingState.style.display = 'none';
                resetBtn.remove();
                progressFill.style.backgroundColor = '';
            });
            loadingState.appendChild(resetBtn);
        }
    });

    function addLog(text, isSuccess = false, isError = false) {
        const div = document.createElement('div');
        let icon = '<i class="fa-solid fa-angle-right"></i>';
        if (isSuccess) {
            icon = '<i class="fa-solid fa-check" style="color: var(--green)"></i>';
            div.style.color = 'var(--green)';
        } else if (isError) {
            icon = '<i class="fa-solid fa-triangle-exclamation" style="color: var(--red)"></i>';
            div.style.color = 'var(--red)';
        }
        div.innerHTML = `${icon} <span>${text}</span>`;
        loadingLogs.appendChild(div);
        loadingLogs.scrollTop = loadingLogs.scrollHeight;
    }

    // --- Render Results Dashboard ---
    function renderDashboard(data) {
        loadingState.style.display = 'none';
        resultsPanel.style.display = 'block';

        // Stats
        statTotal.textContent = data.stats.total_entities;
        statTypes.textContent = Object.keys(data.stats.by_label).length;
        statTime.textContent = `${data.stats.elapsed_time.toFixed(1)}s`;

        // Configure Download Buttons
        downloadDocBtn.href = `/download/${data.output_filename}`;
        
        // Setup Client JSON Download
        downloadJsonBtn.onclick = () => {
            const blob = new Blob([JSON.stringify(data.mapping_log, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${data.output_filename.replace('.docx', '')}_mapping.json`;
            a.click();
            URL.revokeObjectURL(url);
        };

        // Render visual bar chart
        barChart.innerHTML = '';
        const counts = data.stats.by_label;
        const maxCount = Math.max(...Object.values(counts), 1);

        Object.entries(counts)
            .sort((a, b) => b[1] - a[1])
            .forEach(([label, count]) => {
                const percentage = (count / maxCount) * 100;
                const row = document.createElement('div');
                row.className = 'chart-row';
                row.innerHTML = `
                    <div class="chart-label-wrapper">
                        <span class="chart-label">${label}</span>
                        <span class="chart-count">${count}</span>
                    </div>
                    <div class="chart-bar-bg">
                        <div class="chart-bar-fill" style="width: ${percentage}%;"></div>
                    </div>
                `;
                barChart.appendChild(row);
            });

        // Render audit table mapping
        renderAuditTable(data.mapping_log);
    }

    function renderAuditTable(mappings) {
        auditTableBody.innerHTML = '';
        if (mappings.length === 0) {
            auditTableBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No PII entities detected.</td></tr>`;
            return;
        }

        mappings.forEach(item => {
            const tr = document.createElement('tr');
            
            // Badge style according to type
            let badgeClass = 'badge-person';
            if (item.label === 'EMAIL') badgeClass = 'badge-email';
            else if (item.label === 'PHONE') badgeClass = 'badge-phone';
            else if (item.label === 'ORG') badgeClass = 'badge-org';
            else if (item.label === 'ADDRESS') badgeClass = 'badge-address';
            else if (item.label === 'CREDIT_CARD') badgeClass = 'badge-card';
            else if (item.label === 'SSN') badgeClass = 'badge-ssn';
            else if (item.label === 'DOB') badgeClass = 'badge-dob';
            else if (item.label === 'IP_ADDRESS') badgeClass = 'badge-ip';

            tr.innerHTML = `
                <td><span class="badge-label ${badgeClass}">${item.label}</span></td>
                <td>${escapeHTML(item.original)}</td>
                <td>${escapeHTML(item.fake)}</td>
            `;
            auditTableBody.appendChild(tr);
        });
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }

    // --- Audit Log Search Filtering ---
    auditSearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const rows = auditTableBody.querySelectorAll('tr');

        rows.forEach(row => {
            if (row.cells.length < 3) return; // skip "No entities" row
            const piiType = row.cells[0].textContent.toLowerCase();
            const originalVal = row.cells[1].textContent.toLowerCase();
            const fakeVal = row.cells[2].textContent.toLowerCase();

            if (piiType.includes(query) || originalVal.includes(query) || fakeVal.includes(query)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });

    // --- Reset App to Upload Another Document ---
    resetAppBtn.addEventListener('click', () => {
        resultsPanel.style.display = 'none';
        controlPanel.style.display = 'block';
        resetFileSelection();
        loadingLogs.innerHTML = '';
        progressFill.style.width = '0%';
    });
});
