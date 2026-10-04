// State
let currentJobId = null;
let currentReport = null;
let activeFilters = new Set(['high', 'medium', 'low']);

// Elements
const views = {
    landing: document.getElementById('landing-view'),
    live: document.getElementById('live-view'),
    results: document.getElementById('results-view')
};

// Theme toggle
const themeBtn = document.getElementById('theme-btn');
themeBtn.addEventListener('click', () => {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
});
if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.body.setAttribute('data-theme', 'dark');
}

function showView(viewName) {
    Object.values(views).forEach(v => v.classList.remove('active'));
    views[viewName].classList.add('active');
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
}

// Tabs
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        e.target.classList.add('active');
        document.getElementById(e.target.dataset.target).classList.add('active');
    });
});

// File input click
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        dropZone.querySelector('p').textContent = e.target.files[0].name;
    }
});
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.style.borderColor = 'var(--primary-color)'; });
dropZone.addEventListener('dragleave', () => dropZone.style.borderColor = 'var(--border-color)');
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border-color)';
    if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        dropZone.querySelector('p').textContent = fileInput.files[0].name;
    }
});

// Start Analysis
document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append('language', document.getElementById('language').value);
    
    if (document.getElementById('file-upload').classList.contains('active')) {
        if (!fileInput.files[0]) { showToast('Please select a file'); return; }
        fd.append('file', fileInput.files[0]);
    } else {
        const text = document.getElementById('text-input').value.trim();
        if (!text) { showToast('Please enter text'); return; }
        fd.append('text', text);
    }
    
    await startJob(fd);
});

document.querySelectorAll('[data-sample]').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const sampleName = e.target.dataset.sample;
        const res = await fetch(`/sample/${sampleName}`);
        const data = await res.json();
        const fd = new FormData();
        fd.append('text', data.text);
        fd.append('language', 'en');
        // Hack: We append the filename to let the backend know it's a sample if needed for demo cache
        fd.append('file', new File([data.text], sampleName, {type: 'text/plain'}));
        await startJob(fd);
    });
});

async function startJob(formData) {
    showView('live');
    document.getElementById('agent-grid').innerHTML = '';
    document.getElementById('feed-list').innerHTML = '';
    
    try {
        const res = await fetch('/analyze', { method: 'POST', body: formData });
        const data = await res.json();
        currentJobId = data.job_id;
        connectSSE(currentJobId);
    } catch (e) {
        showToast('Failed to start analysis.');
        showView('landing');
    }
}

const agentCards = {};
const AGENTS = ["Segmenter", "Profiler", "Readers", "Money Hunter", "Exit Hunter", "Control Hunter", "Rights Hunter", "Gaps Hunter", "Cross-Clause Analyst", "Grounding", "Skeptic", "Advisor"];

function updateAgentCard(agent, status, message) {
    if (!agentCards[agent]) {
        const div = document.createElement('div');
        div.className = 'agent-card';
        div.innerHTML = `
            <div class="status-icon">⏳</div>
            <h4>${agent}</h4>
            <p class="agent-msg text-muted" style="font-size:0.8rem"></p>
        `;
        document.getElementById('agent-grid').appendChild(div);
        agentCards[agent] = div;
    }
    const card = agentCards[agent];
    card.querySelector('.agent-msg').textContent = message || '';
    
    card.classList.remove('working');
    if (status === 'working') {
        card.classList.add('working');
        card.querySelector('.status-icon').textContent = '⚙️';
    } else if (status === 'done') {
        card.querySelector('.status-icon').textContent = '✅';
    }
}

function connectSSE(jobId) {
    const es = new EventSource(`/stream/${jobId}`);
    
    es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const { event, data: payload } = data;
        
        const feed = document.getElementById('feed-list');
        const li = document.createElement('li');
        
        if (event === 'agent_started') {
            updateAgentCard(payload.agent, 'working', 'Starting...');
        } else if (event === 'agent_progress') {
            updateAgentCard(payload.agent, 'working', payload.message);
            li.textContent = `[${payload.agent}] ${payload.message}`;
            feed.appendChild(li);
        } else if (event === 'agent_finished') {
            updateAgentCard(payload.agent, 'done', payload.message);
        } else if (event === 'finding_discovered') {
            li.innerHTML = `<strong>New Finding:</strong> ${payload.finding.title} <em>(by ${payload.finding.agent})</em>`;
            feed.appendChild(li);
        } else if (event === 'finding_verdict') {
            li.innerHTML = `<strong>Skeptic Verdict:</strong> Finding ${payload.id} -> ${payload.verdict}`;
            feed.appendChild(li);
        } else if (event === 'report_ready') {
            es.close();
            fetchReport(jobId);
        } else if (event === 'error') {
            es.close();
            showToast('Error during analysis: ' + payload.message);
            showView('landing');
        }
        
        feed.parentElement.scrollTop = feed.parentElement.scrollHeight;
    };
    
    es.onerror = () => {
        es.close();
        // Assume finished if disconnected
        fetchReport(jobId).catch(() => {});
    };
}

async function fetchReport(jobId) {
    try {
        const res = await fetch(`/report/${jobId}`);
        if (!res.ok) throw new Error('Report not found');
        currentReport = await res.json();
        renderReport();
        showView('results');
    } catch (e) {
        showToast('Failed to load report.');
    }
}

function renderReport() {
    if (!currentReport) return;
    
    // Header
    const scoreVal = currentReport.score.risk_score;
    document.getElementById('risk-score').textContent = scoreVal;
    document.getElementById('risk-label').textContent = currentReport.score.verdict_label;
    
    // Color gauge based on score
    const gauge = document.getElementById('risk-gauge');
    if (scoreVal < 25) gauge.style.borderColor = 'var(--severity-low)';
    else if (scoreVal < 75) gauge.style.borderColor = 'var(--severity-medium)';
    else gauge.style.borderColor = 'var(--severity-high)';
    
    document.getElementById('executive-summary').innerHTML = `<p>${currentReport.executive_summary}</p>`;
    
    document.getElementById('count-high').textContent = currentReport.score.counts.high || 0;
    document.getElementById('count-medium').textContent = currentReport.score.counts.medium || 0;
    document.getElementById('count-low').textContent = currentReport.score.counts.low || 0;
    document.getElementById('count-rejected').textContent = currentReport.score.counts.rejected || 0;
    
    // Questions
    const qList = document.getElementById('questions-list');
    qList.innerHTML = currentReport.questions_to_ask.map(q => `<li>${q}</li>`).join('');
    
    // Rejected Findings
    const rList = document.getElementById('rejected-list');
    rList.innerHTML = currentReport.rejected_findings.map(f => 
        `<li><strong>${f.title}</strong><br><span class="text-muted">Reason: ${f.skeptic_reason}</span></li>`
    ).join('');
    
    renderDocumentAndFindings();
}

function renderDocumentAndFindings() {
    // Findings List
    const fList = document.getElementById('findings-list');
    fList.innerHTML = '';
    
    const relevantFindings = currentReport.findings.filter(f => activeFilters.has(f.final_severity));
    
    relevantFindings.forEach(f => {
        const div = document.createElement('div');
        div.className = `finding-card ${f.final_severity}`;
        div.id = `finding-${f.id}`;
        div.innerHTML = `
            <div><span class="badge ${f.final_severity}">${f.final_severity.toUpperCase()}</span> 
                 <span class="badge" style="background:#555">Conf: ${(f.final_confidence*100).toFixed(0)}%</span></div>
            <h4>${f.title}</h4>
            <p><strong>What it means:</strong> ${f.plain_explanation || f.why_risky_for_user}</p>
            <details style="margin-top:0.5rem">
                <summary>Why this matters (Skeptic: ${f.verdict})</summary>
                <p>${f.why_risky_for_user}</p>
                <p class="text-muted" style="font-size:0.8rem">Found by: ${f.found_by.join(', ')}</p>
            </details>
            ${f.suggested_counter_clause ? `
                <div style="margin-top:1.5rem; padding:1.25rem; background:var(--bg-color); border: 1px solid var(--border-color); border-radius:8px;">
                    <strong style="color:var(--primary-color)">Ask for this instead:</strong>
                    <p style="margin-top:0.5rem; margin-bottom:1rem">${f.what_to_ask_for}</p>
                    <button class="btn secondary" style="font-size:0.75rem; padding:0.35rem 0.75rem" onclick="navigator.clipboard.writeText('${f.suggested_counter_clause.replace(/'/g, "\\'")}'); showToast('Copied counter-clause!')">Copy Exact Clause</button>
                    <p style="font-size:0.85rem; margin-top:0.75rem; font-family:monospace; padding:0.75rem; background:rgba(128,128,128,0.05); border-radius:4px; border:1px dashed var(--border-color)">${f.suggested_counter_clause}</p>
                </div>
            ` : ''}
        `;
        fList.appendChild(div);
    });
    
    // Document View
    const docView = document.getElementById('document-view');
    let docHTML = "";
    
    // We can map clauses to findings
    const clauseToSeverity = {};
    relevantFindings.forEach(f => {
        f.clause_ids.forEach(cid => {
            const current = clauseToSeverity[cid];
            // highest severity wins highlighting
            if (f.final_severity === 'high') clauseToSeverity[cid] = 'high';
            else if (f.final_severity === 'medium' && current !== 'high') clauseToSeverity[cid] = 'medium';
            else if (f.final_severity === 'low' && current !== 'high' && current !== 'medium') clauseToSeverity[cid] = 'low';
        });
    });

    currentReport.clauses.forEach(c => {
        const sev = clauseToSeverity[c.clause_id];
        if (sev) {
            docHTML += `<div class="clause-highlight highlight-${sev}" id="doc-clause-${c.clause_id}" title="Click to view findings">`;
        } else {
            docHTML += `<div>`;
        }
        
        docHTML += `<strong>[${c.clause_id}] ${c.heading}</strong>\n${c.text}\n</div>\n`;
    });
    
    docView.innerHTML = docHTML;
}

// Filters
document.querySelectorAll('.severity-filters .chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
        const filter = e.target.dataset.filter;
        if (activeFilters.has(filter)) {
            activeFilters.delete(filter);
            e.target.classList.remove('active');
        } else {
            activeFilters.add(filter);
            e.target.classList.add('active');
        }
        renderDocumentAndFindings();
    });
});

// Restart
document.getElementById('btn-analyze-another').addEventListener('click', () => {
    showView('landing');
    currentJobId = null;
    currentReport = null;
    document.getElementById('upload-form').reset();
    document.getElementById('drop-zone').querySelector('p').textContent = 'Drag and drop a PDF or TXT file here, or click to browse.';
});
