/* apply.js */

const DOC_LABELS = {
  marksheet: "Marksheet / Academic Transcript",
  income_certificate: "Income Certificate",
  id_proof: "Identity Proof (Aadhar / PAN / Government ID)",
  category_certificate: "Category / Caste Certificate",
};

const form = document.getElementById("application-form");
const schemeSelect = document.getElementById("scholarship_scheme");
const docFieldsContainer = document.getElementById("doc-upload-fields");
const resultArea = document.getElementById("result-area");
const formNotice = document.getElementById("form-notice");
const submitBtn = document.getElementById("submit-btn");
const userStatusBar = document.getElementById("user-status-bar");

let activeSchemesByName = {};

function updateUserStatus() {
  if (!userStatusBar) return;

  const isLoggedIn = sessionStorage.getItem("janniti_student_logged_in") === "true";
  const email = sessionStorage.getItem("janniti_student_email");

  if (isLoggedIn && email) {
    userStatusBar.classList.remove("hidden");
    userStatusBar.innerHTML = `Signed in as <strong>${email}</strong> · <a href="user-login.html" style="color: var(--navy-800); font-weight:700;">Change account</a>`;
  } else {
    userStatusBar.classList.remove("hidden");
    userStatusBar.innerHTML = 'You are not signed in yet. <a href="user-login.html?redirect=apply.html" style="color: var(--navy-800); font-weight:700;">Login as a student</a> to continue with a personalized application flow.';
  }
}

async function loadScholarshipSchemes() {
  schemeSelect.innerHTML = '<option value="">Loading available schemes...</option>';
  try {
    const data = await apiGet("/scholarship-schemes");
    const schemes = (data && data.schemes) ? data.schemes : [];
    if (!schemes.length) {
      schemeSelect.innerHTML = '<option value="">No active scholarship schemes available</option>';
      return;
    }

    activeSchemesByName = {};
    schemeSelect.innerHTML = '<option value="">Select a scholarship scheme</option>';
    schemes.forEach((s) => {
      activeSchemesByName[s.scheme_name] = s;
      const opt = document.createElement("option");
      opt.value = s.scheme_name;
      opt.textContent = s.scheme_name;
      schemeSelect.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to load scholarship schemes:", err);
    schemeSelect.innerHTML = '<option value="">Failed to load scholarship schemes</option>';
    formNotice.innerHTML = '<div class="notice notice-error">Could not load active scholarship schemes from the server. Please check your connection and refresh.</div>';
  }
}

function getSelectedSchemeRequiredDocs(schemeName) {
  const scheme = activeSchemesByName[schemeName];
  if (scheme && Array.isArray(scheme.required_documents)) {
    return scheme.required_documents;
  }
  return [];
}

function renderDocFields(schemeName) {
  docFieldsContainer.innerHTML = "";
  const docs = getSelectedSchemeRequiredDocs(schemeName);

  if (docs.length === 0) {
    docFieldsContainer.innerHTML = `<p class="hint">Select a scheme above to see required documents.</p>`;
    return;
  }

  docs.forEach((docType) => {
    const label = DOC_LABELS[docType] || docType.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    const wrapper = document.createElement("div");
    wrapper.className = "form-field full";
    wrapper.style.marginBottom = "6px";
    wrapper.innerHTML = `
      <label for="doc_${docType}">${label} <span style="color:var(--red-700)">*</span></label>
      <div class="file-upload" id="upload_${docType}">
        <span class="file-upload-icon">📄</span>
        <input type="file" id="doc_${docType}" data-doctype="${docType}" accept=".pdf" required />
        <span class="file-upload-name"></span>
      </div>
      <span class="hint">PDF only. The file must contain text relevant to this document type.</span>
      <span class="field-error" data-error-for="doc_${docType}"></span>
    `;
    docFieldsContainer.appendChild(wrapper);
  });

  // wire up file-picked feedback
  docs.forEach((docType) => {
    const input = document.getElementById(`doc_${docType}`);
    if (input) {
      input.addEventListener("change", () => {
        const box = document.getElementById(`upload_${docType}`);
        const nameSpan = box.querySelector(".file-upload-name");
        if (input.files.length > 0) {
          box.classList.add("has-file");
          box.classList.remove("has-error");
          nameSpan.textContent = input.files[0].name;
        } else {
          box.classList.remove("has-file");
          nameSpan.textContent = "";
        }
      });
    }
  });
}

schemeSelect.addEventListener("change", () => {
  renderDocFields(schemeSelect.value);
});

function clearErrors() {
  document.querySelectorAll(".field-error").forEach((el) => (el.textContent = ""));
  formNotice.innerHTML = "";
}

function setFieldError(fieldName, message) {
  const el = document.querySelector(`[data-error-for="${fieldName}"]`);
  if (el) el.textContent = message;
}

function validateClientSide() {
  let valid = true;
  const numericFields = ["academic_score", "previous_score", "attendance"];

  numericFields.forEach((f) => {
    const val = parseFloat(document.getElementById(f).value);
    if (isNaN(val) || val < 0 || val > 100) {
      setFieldError(f, "Enter a value between 0 and 100.");
      valid = false;
    }
  });

  const income = parseFloat(document.getElementById("annual_income").value);
  if (isNaN(income) || income < 0) {
    setFieldError("annual_income", "Enter a valid, non-negative income.");
    valid = false;
  }

  if (!schemeSelect.value) {
    setFieldError("scholarship_scheme", "Please select a scholarship scheme.");
    valid = false;
  }
  if (!document.getElementById("application_category").value) {
    setFieldError("application_category", "Please select a category.");
    valid = false;
  }

  const docs = getSelectedSchemeRequiredDocs(schemeSelect.value);
  docs.forEach((docType) => {
    const input = document.getElementById(`doc_${docType}`);
    if (!input || input.files.length === 0) {
      setFieldError(`doc_${docType}`, "This document is required.");
      const box = document.getElementById(`upload_${docType}`);
      if (box) box.classList.add("has-error");
      valid = false;
    }
  });

  return valid;
}

function renderResult(result) {
  const decisionKey = result.decision;
  const stampClass =
    decisionKey === "APPROVE" ? "approve" : decisionKey === "REJECT" ? "reject" : "review";
  const stampLabel =
    decisionKey === "APPROVE" ? "Approved" : decisionKey === "REJECT" ? "Rejected" : "Needs Human Review";

  const confidencePct = Math.round(result.confidence * 100);

  const explanation = result.explanation || {};
  const readableReasons = explanation.readable_reasons || result.top_reasons.map((r) => `Feature ${r.feature.replace(/_/g, " ")} ${r.direction} the likelihood of this outcome.`);
  const positiveReasons = explanation.why_approved || [];
  const negativeReasons = explanation.why_rejected || [];

  let reasonsHtml = "";
  result.top_reasons.forEach((r) => {
    const isUp = r.direction === "increased";
    reasonsHtml += `
      <li>
        <span class="reason-arrow ${isUp ? "up" : "down"}">${isUp ? "▲" : "▼"}</span>
        <span><strong>${r.feature.replace(/_/g, " ")}</strong> ${r.direction} the likelihood of this outcome.</span>
      </li>`;
  });

  let featureBreakdownHtml = "";
  if (explanation.feature_breakdown && explanation.feature_breakdown.length) {
    featureBreakdownHtml = `
      <div class="section-panel" style="text-align:left; margin-top:24px;">
        <div class="section-panel-header"><h3 style="margin:0;">Feature impact breakdown</h3></div>
        <div class="section-panel-body">
          ${explanation.feature_breakdown.map((item) => `
            <div style="margin-bottom:12px;">
              <div style="display:flex; justify-content:space-between; gap:12px; margin-bottom:6px; font-size:0.9rem; color:var(--ink-700);">
                <span>${item.feature}</span>
                <strong>${item.impact > 0 ? "+" : ""}${item.impact}</strong>
              </div>
              <div class="meter"><span style="width:${Math.min(Math.abs(item.impact) * 100, 100)}%"></span></div>
            </div>
          `).join("")}
        </div>
      </div>`;
  }

  let docTableHtml = "";
  if (result.document_verification) {
    const perDoc = result.document_verification.per_document;
    docTableHtml = `
      <div class="section-panel" style="text-align:left; margin-top:24px;">
        <div class="section-panel-header"><h3 style="margin:0;">Document Verification Detail</h3></div>
        <div class="section-panel-body">
          ${Object.entries(perDoc).map(([docType, detail]) => `
            <div class="doc-status-row">
              <span>${DOC_LABELS[docType] || docType}</span>
              <span class="pill ${detail.status === "VERIFIED" ? "pill-approve" : detail.status === "MISSING" || detail.status === "MISMATCH" ? "pill-reject" : "pill-review"}">${detail.status.replace(/_/g, " ")}</span>
            </div>
          `).join("")}
        </div>
      </div>`;
  }

  let overrideNote = "";
  if (result.override_applied) {
    overrideNote = `<div class="notice notice-warn" style="text-align:left; margin-top:20px;">
      <strong>Note:</strong> ${result.override_applied}
    </div>`;
  }

  // Feature 3: Document Anomaly & Fraud Assessment
  let anomalySectionHtml = "";
  if (result.anomaly_assessment) {
    const a = result.anomaly_assessment;
    const aRisk = (a.risk_level || "LOW").toUpperCase();
    const aScore = Math.round(Number(a.anomaly_score) || 0);
    const aStatus = a.status || "CLEAN";
    const isClean = aStatus === "CLEAN";
    const riskPill = aRisk === "HIGH" ? "pill-risk-high" : aRisk === "MEDIUM" || aRisk === "MED" ? "pill-risk-medium" : "pill-risk-low";
    const reasons = a.reasons || [];

    const issuesList = reasons.length ? `
      <div class="anomaly-cards-grid" style="margin-top:12px;">
        ${reasons.map((r) => `
          <div class="anomaly-card-item sev-${(r.severity || "medium").toLowerCase()}">
            <div class="anomaly-item-header">
              <span class="anomaly-type-title">${(r.type || "Document Inconsistency").replace(/_/g, " ")}</span>
              <span class="pill ${r.severity === "HIGH" ? "pill-risk-high" : r.severity === "LOW" ? "pill-risk-low" : "pill-risk-medium"}">${r.severity || "MEDIUM"}</span>
            </div>
            ${r.document_type ? `<div class="anomaly-item-doc">Document: ${r.document_type.replace(/_/g, " ")}</div>` : ""}
            <p class="anomaly-item-msg">${r.message || "Potential discrepancy detected."}</p>
          </div>
        `).join("")}
      </div>
    ` : `<div class="notice notice-info" style="margin-top:12px;">All documents verified with zero detected anomalies.</div>`;

    anomalySectionHtml = `
      <div class="anomaly-panel" style="margin-top:24px; text-align:left;">
        <div class="anomaly-panel-header">
          <h3 class="anomaly-panel-title">🛡️ Document Verification & Risk Assessment</h3>
          <span class="pill ${riskPill}">${aRisk} RISK (${aScore}/100)</span>
        </div>
        <div class="anomaly-panel-body">
          <div class="risk-meter">
            <div class="risk-meter-label">
              <span>Document Risk Score</span>
              <span>${aScore} / 100 (${aRisk} Risk)</span>
            </div>
            <div class="risk-meter-track">
              <div class="risk-meter-fill ${aRisk.toLowerCase()}" style="width:${Math.max(5, Math.min(100, aScore))}%;"></div>
            </div>
          </div>
          <div class="detail-row"><span class="k">Anomaly Status</span><span class="v">${aStatus.replace(/_/g, " ")}</span></div>
          <div class="detail-row"><span class="k">Evaluator Review</span><span class="v">${a.human_review_required ? "Human Review Required" : "Automated Check Clear"}</span></div>
          ${isClean ? `<div class="notice notice-info" style="margin-top:12px;">✅ No discrepancies detected across application and documents.</div>` : issuesList}
          <div style="margin-top:12px; font-size:0.8rem; color:var(--ink-500);">
            ℹ️ Advisory Note: Document anomaly scores route to human evaluators for fair verification; they never cause automatic rejection.
          </div>
        </div>
      </div>
    `;
  }

  const summaryText = explanation.simple_explanation || "This recommendation was generated using the current scholarship rule set and model output.";

  resultArea.innerHTML = `
    <div class="decision-certificate">
      <div class="decision-certificate-body">
        <div class="decision-stamp ${stampClass}">
          <span class="label">${stampLabel}</span>
          <span class="sub">AI RECOMMENDATION</span>
        </div>
        <h2 class="mt-0">Application Decision</h2>
        <div class="app-id-box">Application ID: ${result.application_id}</div>

        <div class="confidence-meter" style="margin-top:24px;">
          <div class="confidence-meter-label">
            <span>Model Confidence</span>
            <span>${confidencePct}%</span>
          </div>
          <div class="confidence-meter-track">
            <div class="confidence-meter-fill" style="width:${confidencePct}%;"></div>
          </div>
        </div>

        <div class="notice notice-info" style="margin-top:18px; text-align:left;">${summaryText}</div>

        <h3>Top Reasons</h3>
        <ul class="reasons-list">${reasonsHtml}</ul>

        <div class="section-panel" style="text-align:left; margin-top:24px;">
          <div class="section-panel-header"><h3 style="margin:0;">Why this decision was made</h3></div>
          <div class="section-panel-body">
            <div style="display:grid; gap:14px;">
              <div>
                <strong>Why approved</strong>
                <ul class="reasons-list" style="margin-top:8px;">
                  ${(positiveReasons.length ? positiveReasons : ["No strong positive factors detected."]).map((item) => `<li><span class="reason-arrow up">▲</span><span>${item}</span></li>`).join("")}
                </ul>
              </div>
              <div>
                <strong>Why rejected</strong>
                <ul class="reasons-list" style="margin-top:8px;">
                  ${(negativeReasons.length ? negativeReasons : ["No strong negative factors detected."]).map((item) => `<li><span class="reason-arrow down">▼</span><span>${item}</span></li>`).join("")}
                </ul>
              </div>
            </div>
          </div>
        </div>

        ${featureBreakdownHtml}
        ${overrideNote}
        ${docTableHtml}
        ${anomalySectionHtml}

        <div style="margin-top:22px; display:flex; gap:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" id="download-report-btn">Download Explanation Report</button>
          <a href="user-dashboard.html" class="btn btn-secondary">View in Student Dashboard</a>
        </div>

        <p style="margin-top:24px; font-size:0.85rem; color:var(--ink-500);">
          This is an AI-generated recommendation. Applications marked "Needs Human Review" are
          examined by an evaluator before a final decision is recorded. Save your Application ID
          to track its status.
        </p>
      </div>
    </div>
  `;

  const downloadButton = document.getElementById("download-report-btn");
  if (downloadButton) {
    downloadButton.addEventListener("click", () => {
      const report = explanation.report || {
        decision: result.decision,
        confidence: result.confidence,
        summary: summaryText,
        reasons: readableReasons,
      };

      const blob = new Blob([
        `Janniti AI Explanation Report\n\n` +
        `Application ID: ${result.application_id}\n` +
        `Decision: ${formatDecisionLabel(result.decision)}\n` +
        `Confidence: ${confidencePct}%\n\n` +
        `Summary:\n${report.summary}\n\n` +
        `Reasons:\n${(report.reasons || readableReasons).map((r) => `- ${r}`).join('\n')}`
      ], { type: "text/plain;charset=utf-8" });

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `janniti-ai-report-${result.application_id}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });
  }
  resultArea.scrollIntoView({ behavior: "smooth", block: "start" });
}

const ensureStudentLoginBeforeSubmit = () => {
  const token = sessionStorage.getItem("janniti_auth_token");
  const isLoggedIn = sessionStorage.getItem("janniti_student_logged_in") === "true" && !!token;
  if (!isLoggedIn) {
    window.location.href = "user-login.html?redirect=apply.html";
    return false;
  }
  return true;
};

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!ensureStudentLoginBeforeSubmit()) {
    return;
  }

  clearErrors();
  resultArea.innerHTML = "";

  if (!validateClientSide()) {
    formNotice.innerHTML = `<div class="notice notice-error">Please fix the highlighted fields before submitting.</div>`;
    return;
  }

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span> Submitting...`;

  const fd = new FormData();
  fd.append("academic_score", document.getElementById("academic_score").value);
  fd.append("previous_score", document.getElementById("previous_score").value);
  fd.append("attendance", document.getElementById("attendance").value);
  fd.append("annual_income", document.getElementById("annual_income").value);
  fd.append("application_category", document.getElementById("application_category").value);
  fd.append("scholarship_scheme", schemeSelect.value);

  const docs = getSelectedSchemeRequiredDocs(schemeSelect.value);
  docs.forEach((docType) => {
    const input = document.getElementById(`doc_${docType}`);
    if (input && input.files && input.files[0]) {
      fd.append(docType, input.files[0]);
    }
  });

  try {
    const token = sessionStorage.getItem("janniti_auth_token");
    const result = await apiPost("/submit-application-full", fd, true, token);
    renderResult(result);
    form.classList.add("hidden");
  } catch (err) {
    formNotice.innerHTML = `<div class="notice notice-error">Could not submit application: ${err.message}. Make sure the backend server is running at ${API_BASE}.</div>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit Application";
  }
});

// Immediate Auth Guard on page load
(async function initApplyPage() {
  let session = null;
  try {
    if (typeof getSupabaseSession === "function") {
      session = await getSupabaseSession();
    }
  } catch (err) {
    console.warn("Supabase session check error:", err);
  }

  const storedToken = sessionStorage.getItem("janniti_auth_token");
  const isLoggedInFlag = sessionStorage.getItem("janniti_student_logged_in") === "true";

  // Check Supabase session first, or valid stored auth token
  const isAuthenticated = Boolean((session && session.access_token) || (isLoggedInFlag && storedToken));

  if (!isAuthenticated) {
    window.location.href = "user-login.html?redirect=apply.html";
    return;
  }

  // If Supabase returned a session but session storage is missing tokens, sync them
  if (session && session.user && !storedToken) {
    try {
      if (typeof fetchCurrentStudentProfile === "function" && typeof persistSupabaseAuth === "function") {
        const profile = await fetchCurrentStudentProfile(session.access_token);
        persistSupabaseAuth(session, session.user, profile || {});
      }
    } catch (e) {
      console.warn("Session sync error:", e);
    }
  }

  if (form) {
    form.style.display = "";
  }
  updateUserStatus();
  await loadScholarshipSchemes();
})();
