// Config
const UPLOAD_ENDPOINT = "http://127.0.0.1:8000/upload";
const GRAMMAR_ENDPOINT = "http://127.0.0.1:8000/grammar-check";

// DOM references (matching index.html)
const dropArea = document.getElementById('drop-area');
const resumeFile = document.getElementById('resumeFile');
const analyzeBtn = document.getElementById('analyzeBtn');
const fileNameDisplay = document.getElementById('fileName');
const uploadBtn = document.getElementById('upload-btn');
const loader = document.getElementById('loader');
const progressBar = document.getElementById('progressBar');

const uploadSection = document.getElementById('upload-section');
const resultsSection = document.getElementById('results-section');
const resetBtn = document.getElementById('resetBtn');
const grammarCheckBtn = document.getElementById('grammarCheckBtn');
const grammarLoader = document.getElementById('grammarLoader');
const grammarIssues = document.getElementById('grammarIssues');

// Results
const emailResult = document.getElementById('emailResult');
const phoneResult = document.getElementById('phoneResult');
const skillsResult = document.getElementById('skillsResult');
const atsScoreValue = document.getElementById('atsScoreValue');
const atsFeedback = document.getElementById('atsFeedback');
const wordCountResult = document.getElementById('wordCountResult');
const missingSections = document.getElementById('missingSections');

let fileToUpload = null;
let fullTextExtracted = ""; // store full_text for grammar

// ---------- Drag & drop / file selection ----------
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
    dropArea.addEventListener(evt, preventDefaults, false);
});
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

['dragenter', 'dragover'].forEach(evt => {
    dropArea.addEventListener(evt, () => dropArea.classList.add('highlight'), false);
});
['dragleave', 'drop'].forEach(evt => {
    dropArea.addEventListener(evt, () => dropArea.classList.remove('highlight'), false);
});

dropArea.addEventListener('drop', handleDrop, false);
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        fileToUpload = files[0];
        resumeFile.files = files; // set input files (optional)
        fileNameDisplay.textContent = `File Selected: ${fileToUpload.name}`;
        analyzeBtn.disabled = false;
    }
}

// Browse button opens hidden file input
uploadBtn.addEventListener('click', () => resumeFile.click());

resumeFile.addEventListener('change', () => {
    if (resumeFile.files.length > 0) {
        fileToUpload = resumeFile.files[0];
        fileNameDisplay.textContent = `File Selected: ${fileToUpload.name}`;
        analyzeBtn.disabled = false;
    } else {
        fileToUpload = null;
        fileNameDisplay.textContent = '';
        analyzeBtn.disabled = true;
    }
});

// ---------- Progress simulation helper ----------
function updateProgress(percent, text) {
    progressBar.style.width = `${percent}%`;
    const loadingText = document.querySelector('.loading-text');
    if (loadingText) loadingText.textContent = text || loadingText.textContent;
}

// ---------- Main analyze flow ----------
analyzeBtn.addEventListener('click', async () => {
    if (!fileToUpload) return;
    // UI: hide upload, show loader
    uploadSection.classList.add('hidden');
    loader.style.display = 'block';
    updateProgress(0, "Connecting to API...");

    // Simple staged progress animation for better UX
    const steps = [
        { pct: 15, text: "Connecting to API..." },
        { pct: 35, text: "Uploading file and extracting text..." },
        { pct: 60, text: "Parsing contact & skills..." },
        { pct: 85, text: "Calculating ATS score..." },
        { pct: 98, text: "Finalizing report..." }
    ];

    for (let s of steps) {
        await new Promise(r => setTimeout(r, 400));
        updateProgress(s.pct, s.text);
    }

    // Prepare form data
    const formData = new FormData();
    formData.append('file', fileToUpload);

    try {
        const resp = await fetch(UPLOAD_ENDPOINT, { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail || `Upload failed (status ${resp.status})`);
        }
        const data = await resp.json();

        // Final progress
        updateProgress(100, "Done.");

        // small delay for UX
        await new Promise(r => setTimeout(r, 300));
        loader.style.display = 'none';

        // Show results section
        populateResults(data);
        resultsSection.classList.remove('hidden');
        // Scroll into view
        resultsSection.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        console.error("Upload error:", error);
        alert(`Analysis failed: ${error.message}`);
        // reset UI
        loader.style.display = 'none';
        uploadSection.classList.remove('hidden');
    }
});

// ---------- Populate results (map backend fields) ----------
function populateResults(data) {
    emailResult.textContent = data.email || "N/A";
    phoneResult.textContent = data.phone || "N/A";
    wordCountResult.textContent = (typeof data.word_count !== 'undefined') ? data.word_count : "N/A";

    // Skills
    skillsResult.innerHTML = '';
    if (Array.isArray(data.skills) && data.skills.length) {
        data.skills.forEach(s => {
            const span = document.createElement('span');
            span.className = 'skill-tag';
            span.textContent = s;
            skillsResult.appendChild(span);
        });
    } else {
        skillsResult.innerHTML = '<span class="skill-tag">No relevant skills found.</span>';
    }

    // Missing sections (list)
    if (Array.isArray(data.missing_sections) && data.missing_sections.length) {
        const ul = document.createElement('ul');
        ul.className = 'missing-list';
        data.missing_sections.forEach(ms => {
            const li = document.createElement('li');
            li.textContent = ms;
            ul.appendChild(li);
        });
        missingSections.innerHTML = '';
        missingSections.appendChild(ul);
    } else {
        missingSections.innerHTML = '<div class="missing-ok">All core sections detected ✅</div>';
    }

    // ATS score (display and conic gradient)

    const score = data.ats_score || 0;
    atsScoreValue.textContent = score;
    atsFeedback.textContent = getAtsFeedback(score);

    // progress bar
    const bar = document.getElementById("atsBarFill");
    bar.style.width = score + "%";

    // Store full_text for grammar checks
    fullTextExtracted = data.full_text || "";
}

// ---------- ATS feedback helper ----------
function getAtsFeedback(score) {
    if (score >= 80) return "Excellent — very competitive.";
    if (score >= 60) return "Good — a few improvements suggested.";
    return "Needs improvement. Add keywords & details.";
}

// ---------- Grammar check ----------
grammarCheckBtn.addEventListener('click', async () => {
    if (!fullTextExtracted || fullTextExtracted.trim() === "") {
        alert("No extracted text available. Please analyze a resume first.");
        return;
    }

    grammarCheckBtn.disabled = true;
    grammarLoader.classList.remove('hidden');
    grammarIssues.innerHTML = '';

    try {
        const resp = await fetch(GRAMMAR_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: fullTextExtracted })
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Grammar check failed' }));
            throw new Error(err.detail || `Grammar check failed (status ${resp.status})`);
        }

        const res = await resp.json();
        renderGrammar(res.errors || []);
    } catch (err) {
        console.error("Grammar error:", err);
        alert(`Grammar check failed: ${err.message}`);
    } finally {
        grammarLoader.classList.add('hidden');
        grammarCheckBtn.disabled = false;
    }
});

function renderGrammar(errors) {
    grammarIssues.innerHTML = '';
    if (!errors || !errors.length) {
        const p = document.createElement('p');
        p.textContent = "🎉 No grammar issues found!";
        grammarIssues.appendChild(p);
        return;
    }
    errors.forEach((e, idx) => {
        const div = document.createElement('div');
        div.className = 'grammar-issues-item';
        div.innerHTML = `<p><strong>Incorrect:</strong> ${escapeHtml(e.incorrect)}</p>
                        <p><strong>Suggestion:</strong> ${escapeHtml(e.suggestion)}</p>
                        <p>${escapeHtml(e.message)}</p>`;
        grammarIssues.appendChild(div);
    });
}
function escapeHtml(s) { return String(s).replace(/[&<>"'\/]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '/': '&#x2F;' })[c]; }); }

// ---------- Reset / Start over ----------
resetBtn.addEventListener('click', () => {
    // Reset UI and state
    fileToUpload = null;
    fullTextExtracted = "";
    resumeFile.value = '';
    fileNameDisplay.textContent = '';
    analyzeBtn.disabled = true;
    resultsSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');

    // clear results
    emailResult.textContent = "N/A";
    phoneResult.textContent = "N/A";
    skillsResult.innerHTML = '';
    wordCountResult.textContent = 'N/A';
    missingSections.innerHTML = 'N/A';
    grammarIssues.innerHTML = '';
    atsScoreValue.textContent = '--';
    document.querySelector('.score-circle-outer').style.background = `conic-gradient(var(--secondary-color) 0deg, var(--primary-color) 0deg, #eee 0deg)`;
});

// ---------- small niceties ----------
document.addEventListener('DOMContentLoaded', () => {
    analyzeBtn.disabled = true;
    loader.style.display = 'none';
    grammarLoader.classList.add('hidden');
});
