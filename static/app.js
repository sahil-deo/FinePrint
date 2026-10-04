const $ = id => document.getElementById(id);

let currentJobId = null;
let currentReport = null;
let findingsData = {};
let selectedFindingId = null;

// Thematic setup
const themeBtn = $('theme-btn');
themeBtn.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
});
if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark');
}

// Phases
function switchPhase(phaseId) {
    document.querySelectorAll('.phase').forEach(p => p.classList.remove('active'));
    $(phaseId).classList.add('active');
}

// Phase 1 Form
$('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('text-input').value;
    const file = $('file-input').files[0];
    const lang = document.querySelector('input[name="language"]:checked').value;
    
    if (!text && !file) return showToast("Provide text or a file");
    
    const formData = new FormData();
    formData.append('text', text);
    formData.append('language', lang);
    if (file) formData.append('file', file);
    
    const btn = $('btn-analyze');
    btn.textContent = "Connecting...";
    btn.disabled = true;
    
    try {
        const res = await fetch('/analyze', { method: 'POST', body: formData });
        if (!res.ok) throw new Error("Failed to start analysis");
        const data = await res.json();
        currentJobId = data.job_id;
        
        switchPhase('phase-analysis');
        initGraph();
        startSSE(currentJobId);
        
        // Render raw text initially
        if (text) renderDocument(text);
        
    } catch (err) {
        showToast(err.message);
        btn.textContent = "Analyze";
        btn.disabled = false;
    }
});

// Drag and drop overlay
const dropZone = $('drop-zone');
document.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
document.addEventListener('dragleave', e => { if(e.target === dropZone) dropZone.classList.remove('dragover'); });
document.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) {
        $('file-input').files = e.dataTransfer.files;
        showToast(`Loaded ${file.name}`);
        // auto trigger if ready
    }
});
$('file-input').addEventListener('change', e => {
    if (e.target.files[0]) showToast(`Loaded ${e.target.files[0].name}`);
});

document.querySelectorAll('.sample-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
        const sampleName = chip.getAttribute('data-sample');
        try {
            const res = await fetch(`/sample/${sampleName}`);
            if (!res.ok) throw new Error("Failed to load sample");
            const data = await res.json();
            $('text-input').value = data.text;
            showToast(`Loaded ${sampleName}`);
        } catch (err) {
            showToast(err.message);
        }
    });
});

// Graph rendering
const graphNodes = [
    { id: 'Segmenter', x: 80, y: 100, type: 'code', label: 'Segmenter' },
    { id: 'Readers', x: 220, y: 100, type: 'ai', label: 'FullReader' },
    { id: 'Profiler', x: 220, y: 160, type: 'ai', label: 'Profiler' }, // Fake profiler node
    { id: 'Hunters', x: 420, y: 100, type: 'ai', label: 'Risk Hunters' },
    { id: 'Grounding', x: 620, y: 100, type: 'code', label: 'Grounding' },
    { id: 'Skeptic', x: 760, y: 100, type: 'ai', label: 'Skeptic' },
    { id: 'Advisor', x: 900, y: 100, type: 'ai', label: 'Advisor' }
];

const edges = [
    { from: 'Segmenter', to: 'Readers' },
    { from: 'Readers', to: 'Hunters' },
    { from: 'Hunters', to: 'Grounding' },
    { from: 'Grounding', to: 'Skeptic' },
    { from: 'Skeptic', to: 'Advisor' }
];

function initGraph() {
    const svg = $('agent-graph');
    svg.setAttribute('viewBox', '0 0 1000 200');
    let html = '';
    
    // Draw edges
    edges.forEach(e => {
        const from = graphNodes.find(n => n.id === e.from);
        const to = graphNodes.find(n => n.id === e.to);
        const path = `M ${from.x} ${from.y} C ${(from.x + to.x)/2} ${from.y}, ${(from.x + to.x)/2} ${to.y}, ${to.x} ${to.y}`;
        html += `<g class="edge" id="edge-${from.id}-${to.id}"><path d="${path}" /></g>`;
    });
    
    // Draw nodes
    graphNodes.forEach(n => {
        html += `<g class="node" id="node-${n.id}" transform="translate(${n.x}, ${n.y})">`;
        if (n.type === 'ai') {
            html += `<circle cx="0" cy="0" r="16" />`;
        } else {
            html += `<rect x="-14" y="-14" width="28" height="28" rx="4" />`;
        }
        html += `<text class="label" y="32">${n.label}</text>`;
        html += `<text class="count" id="count-${n.id}" y="4">0</text>`;
        html += `</g>`;
    });
    
    svg.innerHTML = html;
}

function updateNode(agentName, status) {
    // Map backend agent names to our graph
    let nodeId = agentName;
    if (agentName.includes("Hunter") || agentName === "Cross-Clause Analyst" || agentName === "FullRiskAnalyst" || agentName === "Money Hunter") {
        nodeId = 'Hunters';
    }
    const g = $(`node-${nodeId}`);
    if (!g) return;
    
    g.classList.remove('active', 'done');
    if (status === 'started' || status === 'progress') g.classList.add('active');
    if (status === 'finished') g.classList.add('done');
    
    // Update edges
    if (status === 'finished') {
        edges.filter(e => e.from === nodeId).forEach(e => {
            const edgeEl = $(`edge-${e.from}-${e.to}`);
            if (edgeEl) { edgeEl.classList.add('active'); }
        });
        edges.filter(e => e.to === nodeId).forEach(e => {
            const edgeEl = $(`edge-${e.from}-${e.to}`);
            if (edgeEl) { edgeEl.classList.remove('active'); edgeEl.classList.add('done'); }
        });
    }
}

// SSE Connection
function startSSE(jobId) {
    const es = new EventSource(`/stream/${jobId}`);
    
    es.onmessage = (e) => {
        const payload = JSON.parse(e.data);
        const { event, data } = payload;
        
        if (event === 'agent_started' || event === 'agent_progress' || event === 'agent_finished') {
            updateNode(data.agent, event.split('_')[1]);
        }
        else if (event === 'finding_discovered') {
            const f = data.finding;
            findingsData[f.title] = { title: f.title, status: 'reviewing', agent: f.agent };
            addFindingCard(f);
            
            // Increment counter on Hunters
            const cEl = $('count-Hunters');
            if(cEl) cEl.textContent = parseInt(cEl.textContent) + 1;
        }
        else if (event === 'finding_verdict') {
            const { id, verdict, reason } = data;
            updateFindingCard(id, verdict, reason);
        }
        else if (event === 'report_ready') {
            es.close();
            fetchReport(jobId);
        }
        else if (event === 'error') {
            es.close();
            showToast("Pipeline error: " + data.message);
        }
    };
    es.onerror = () => { es.close(); fetchReport(jobId).catch(()=>{}); };
}

async function fetchReport(jobId) {
    try {
        $('live-status').textContent = "Finalizing report...";
        $('live-dot').style.animation = "none";
        
        const res = await fetch(`/report/${jobId}`);
        if (!res.ok) throw new Error("Report not found");
        currentReport = await res.json();
        
        transitionToReview();
    } catch(err) {
        showToast(err.message);
    }
}

function transitionToReview() {
    $('graph-container').classList.add('collapsed');
    $('review-header').style.display = 'block';
    $('live-status').textContent = "Analysis complete";
    
    // Fill stats
    const score = currentReport.score;
    $('score-number').textContent = score.risk_score;
    $('verdict-sentence').textContent = score.verdict_label + ". " + currentReport.findings.length + " issues found.";
    
    let high = 0, med = 0, low = 0;
    currentReport.findings.forEach(f => {
        if (f.severity === 'high') high++;
        else if (f.severity === 'medium') med++;
        else low++;
    });
    const elHigh = $('c-high'); if (elHigh) elHigh.textContent = high;
    const elMed = $('c-medium'); if (elMed) elMed.textContent = med;
    const elLow = $('c-low'); if (elLow) elLow.textContent = low;
    
    // Render document highlights
    if (currentReport.document_text) {
        renderDocument(currentReport.document_text, currentReport.findings);
    }
}

function addFindingCard(f) {
    // Generate an ID based on title for pre-verdict tracking
    const tempId = 'fc-' + Math.random().toString(36).substr(2, 9);
    findingsData[f.title].id = tempId;
    
    const div = document.createElement('div');
    div.className = 'finding-card';
    div.id = tempId;
    div.innerHTML = `
        <div class="fc-header">
            <h4 class="fc-title">${f.title}</h4>
            <span class="fc-clause-chip">Reviewing...</span>
        </div>
        <p class="fc-desc">Found by ${f.agent}</p>
        <span class="fc-status reviewing">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
            Skeptic review
        </span>
    `;
    $('findings-list').prepend(div);
}

function updateFindingCard(id, verdict, reason) {
    // We only have the real ID now, let's find the matching finding in report if available, or just update DOM
    // The backend sends `finding_verdict` with the `id`. We need to match it.
    // Wait, `finding_discovered` only sent title and agent. We might not have the ID until `finding_verdict`.
    // Let's just find a finding card that is 'reviewing' and update it.
    const cards = document.querySelectorAll('.fc-status.reviewing');
    if(cards.length > 0) {
        const card = cards[cards.length-1].closest('.finding-card');
        card.id = `finding-${id}`;
        
        let vClass = 'low'; let vLabel = 'Confirmed'; let icon = '<polyline points="20 6 9 17 4 12"></polyline>';
        if (verdict === 'rejected') {
            card.classList.add('rejected');
            $('rejected-list').appendChild(card);
            $('rejected-group').style.display = 'block';
            $('c-rejected').textContent = parseInt($('c-rejected').textContent) + 1;
            return; // Move to rejected
        } else if (verdict === 'downgraded') {
            vClass = 'medium'; vLabel = 'Downgraded';
        }
        
        card.classList.add(vClass);
        const statusEl = card.querySelector('.fc-status');
        statusEl.className = 'fc-status'; // remove reviewing
        statusEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${icon}</svg> ${vLabel}`;
        
        const chipEl = card.querySelector('.fc-clause-chip');
        if (chipEl) chipEl.remove();
        
        // Add click handler for details
        card.addEventListener('click', () => showFindingDetail(id));
    }
}

function showFindingDetail(id) {
    if (!currentReport) return;
    const f = currentReport.findings.find(x => x.id === id);
    if (!f) return;
    
    // Highlight in doc
    document.querySelectorAll('.highlight').forEach(el => el.classList.remove('active'));
    const docSpan = document.getElementById(`hl-${id}`);
    if (docSpan) {
        docSpan.classList.add('active');
        docSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // Slide panel
    const detail = $('slide-content');
    detail.innerHTML = `
        <h2 style="font-family:var(--font-display); font-size:24px; font-weight:400; margin:0 0 16px">${f.title}</h2>
        <div class="detail-section">
            <h4>Severity & Verdict</h4>
            <div style="display:flex; gap:8px">
                <span class="chip ${f.severity}"><span class="pip ${f.severity}"></span> ${f.severity}</span>
                <span class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg> ${f.verdict}</span>
            </div>
        </div>
        
        <div class="detail-section" style="margin-top:24px">
            <h4>Quote</h4>
            <div class="detail-quote">${f.evidence_quotes[0] || 'No quote provided.'}</div>
        </div>
        
        <div class="detail-section" style="margin-top:24px">
            <h4>Why this matters</h4>
            <p>${f.plain_explanation || f.why_risky_for_user}</p>
        </div>
        
        ${f.suggested_counter_clause ? `
        <div class="counter-clause-box" style="margin-top:32px">
            <h4>Ask for this instead</h4>
            <p>${f.suggested_counter_clause}</p>
            <button class="icon-btn copy-btn" onclick="navigator.clipboard.writeText('${f.suggested_counter_clause.replace(/'/g, "\\'")}'); showToast('Copied!')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
        </div>
        ` : ''}
    `;
    
    $('detail-overlay').classList.add('open');
}

$('close-detail').addEventListener('click', () => $('detail-overlay').classList.remove('open'));

// Simple renderer parsing pseudo-paragraphs and adding IDs
function renderDocument(text, findings = []) {
    const lines = text.split('\n').filter(l => l.trim().length > 0);
    let html = '';
    
    lines.forEach((line, i) => {
        let content = line;
        // If findings exist, highlight text
        if (findings.length > 0) {
            findings.forEach(f => {
                f.evidence_quotes.forEach(q => {
                    if (q.length > 10 && content.includes(q)) {
                        content = content.replace(q, `<span class="highlight ${f.severity}" id="hl-${f.id}">${q}</span>`);
                    }
                });
            });
        }
        
        const isHeading = /^\d+(\.\d+)*\s+[A-Z]/.test(line);
        if (isHeading) {
            html += `<div class="doc-clause"><h3>${content}</h3></div>`;
        } else {
            html += `<div class="doc-clause"><span class="clause-number">§${i+1}</span>${content}</div>`;
        }
    });
    
    $('doc-content').innerHTML = html;
}

// Utils
function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'toast'; t.textContent = msg;
    $('toast-container').appendChild(t);
    setTimeout(() => t.remove(), 3300);
}

// Keyboard
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') $('detail-overlay').classList.remove('open');
});

// Export report
$('btn-export').addEventListener('click', () => {
    if (!currentReport) return showToast("No report to export");
    
    let reportHtml = `
        <html>
        <head>
            <title>FinePrint Report - ${currentReport.document_name}</title>
            <style>
                body { font-family: sans-serif; line-height: 1.6; padding: 40px; color: #333; max-width: 800px; margin: 0 auto; }
                h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }
                .finding { margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 8px; page-break-inside: avoid; }
                .finding h3 { margin-top: 0; }
                .severity-high { color: #d32f2f; }
                .severity-medium { color: #f57c00; }
                .severity-low { color: #388e3c; }
                .quote { background: #f9f9f9; padding: 10px; font-style: italic; border-left: 4px solid #ccc; margin-bottom: 15px; }
            </style>
        </head>
        <body>
            <h1>FinePrint Analysis Report</h1>
            <p><strong>Document:</strong> ${currentReport.document_name}</p>
            <p><strong>Risk Score:</strong> ${currentReport.score.risk_score} / 100 (${currentReport.score.verdict_label})</p>
            <p><strong>Summary:</strong> ${currentReport.executive_summary || 'No summary available.'}</p>
            <h2>Findings (${currentReport.findings.length})</h2>
    `;
    
    currentReport.findings.forEach(f => {
        reportHtml += `
            <div class="finding">
                <h3 class="severity-${f.severity}">${f.title} (${f.severity.toUpperCase()})</h3>
                <div class="quote">"${f.evidence_quotes[0] || 'No quote'}"</div>
                <p><strong>Why this matters:</strong> ${f.plain_explanation || f.why_risky_for_user}</p>
                ${f.suggested_counter_clause ? `<p><strong>Suggested change:</strong> ${f.suggested_counter_clause}</p>` : ''}
            </div>
        `;
    });
    
    reportHtml += `</body></html>`;
    
    const printWindow = window.open('', '_blank');
    if (!printWindow) return showToast("Pop-up blocked. Please allow pop-ups to export.");
    printWindow.document.write(reportHtml);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
        printWindow.print();
    }, 250);
});
