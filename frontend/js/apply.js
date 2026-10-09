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

const applyStageSelect = document.getElementById("select_academic_stage");
const applyDynamicFieldsContainer = document.getElementById("apply-dynamic-academic-fields");

function renderApplyAcademicFields(stage) {
  if (!applyDynamicFieldsContainer) return;

  if (stage === "FIRST_YEAR") {
    applyDynamicFieldsContainer.innerHTML = `
      <div style="background:var(--accent-subtle, #f0fdf4); border:1px solid #bbf7d0; border-radius:8px; padding:12px; margin-bottom:16px;">
        <span style="font-size:1.1rem; margin-right:6px;">ℹ️</span>
        <strong style="color:var(--ink-800);">First-Year / Fresh Admission:</strong>
        <span style="color:var(--ink-600); font-size:0.9rem;">
          Your most recent qualifying examination is used for academic assessment. College attendance is waived / not applicable.
        </span>
      </div>

      <div class="form-grid">
        <div class="form-field">
          <label for="select_qualification_type">Most Recent Completed Qualification *</label>
          <select id="select_qualification_type" name="qualification_type" required>
            <option value="HSC_12TH">HSC / 12th Standard</option>
            <option value="DIPLOMA">Diploma</option>
            <option value="OTHER">Other qualifying examination</option>
          </select>
          <span class="hint">Select the examination qualifying you for college admission.</span>
          <span class="field-error" data-error-for="qualification_type"></span>
        </div>

        <div class="form-field">
          <label id="label_qualifying_score" for="qualifying_score">Qualifying Examination Score (%) *</label>
          <input type="number" id="qualifying_score" name="qualifying_score" min="0" max="100" step="0.1" required placeholder="e.g. 85.0" />
          <span class="hint" id="hint_qualifying_score">HSC / 12th Standard aggregate percentage.</span>
          <span class="field-error" data-error-for="qualifying_score"></span>
        </div>

        <div class="form-field">
          <label for="ssc_score">SSC / 10th Percentage (%)</label>
          <input type="number" id="ssc_score" name="ssc_score" min="0" max="100" step="0.1" placeholder="e.g. 82.0" />
          <span class="hint">Secondary school examination percentage.</span>
          <span class="field-error" data-error-for="ssc_score"></span>
        </div>

        <div class="form-field" style="grid-column: 1/-1;">
          <label>College Attendance</label>
          <div style="padding:10px 14px; background:var(--bg-card-subtle, #f8fafc); border:1px solid var(--border-color, #e2e8f0); border-radius:6px; color:var(--ink-500); font-size:0.9rem;">
            <strong style="color:var(--accent-text, #166534);">Not Applicable — First-Year Admission</strong> (Waived for fresh admission; strictly recorded as NULL)
          </div>
        </div>
      </div>
    `;

    const qualSelect = document.getElementById("select_qualification_type");
    if (qualSelect) {
      qualSelect.addEventListener("change", () => {
        const val = qualSelect.value;
        const lbl = document.getElementById("label_qualifying_score");
        const hnt = document.getElementById("hint_qualifying_score");
        if (lbl) {
          if (val === "DIPLOMA") {
            lbl.textContent = "Diploma Percentage (%) *";
            if (hnt) hnt.textContent = "Aggregate percentage across completed diploma semesters.";
          } else {
            lbl.textContent = "Qualifying Examination Score (%) *";
            if (hnt) hnt.textContent = "HSC / 12th Standard aggregate percentage.";
          }
        }
      });
    }
  } else if (stage === "SECOND_YEAR") {
    applyDynamicFieldsContainer.innerHTML = `
      <div class="form-grid">
        <div class="form-field">
          <label for="first_year_score">First Year College Percentage (%) *</label>
          <input type="number" id="first_year_score" name="first_year_score" min="0" max="100" step="0.1" required placeholder="e.g. 78.5" />
          <span class="hint">Aggregate percentage obtained across 1st & 2nd semesters of college.</span>
          <span class="field-error" data-error-for="first_year_score"></span>
        </div>

        <div class="form-field">
          <label for="qualifying_score">12th / Diploma Percentage (%)</label>
          <input type="number" id="qualifying_score" name="qualifying_score" min="0" max="100" step="0.1" placeholder="e.g. 84.0" />
          <span class="hint">Qualifying score prior to entering college.</span>
          <span class="field-error" data-error-for="qualifying_score"></span>
        </div>

        <div class="form-field">
          <label for="attendance">First Year College Attendance (%) *</label>
          <input type="number" id="attendance" name="attendance" min="0" max="100" step="0.1" required placeholder="e.g. 85.0" />
          <span class="hint">Official attendance record from your first year of college.</span>
          <span class="field-error" data-error-for="attendance"></span>
        </div>
      </div>
    `;
  } else if (stage === "THIRD_YEAR") {
    applyDynamicFieldsContainer.innerHTML = `
      <div class="form-grid">
        <div class="form-field">
          <label for="second_year_score">Second Year College Percentage (%) *</label>
          <input type="number" id="second_year_score" name="second_year_score" min="0" max="100" step="0.1" required placeholder="e.g. 81.0" />
          <span class="hint">Aggregate percentage obtained in your second year of college.</span>
          <span class="field-error" data-error-for="second_year_score"></span>
        </div>

        <div class="form-field">
          <label for="first_year_score">First Year College Percentage (%)</label>
          <input type="number" id="first_year_score" name="first_year_score" min="0" max="100" step="0.1" placeholder="e.g. 78.5" />
          <span class="hint">Aggregate percentage from your first year of college.</span>
          <span class="field-error" data-error-for="first_year_score"></span>
        </div>

        <div class="form-field">
          <label for="attendance">Second Year College Attendance (%) *</label>
          <input type="number" id="attendance" name="attendance" min="0" max="100" step="0.1" required placeholder="e.g. 88.0" />
          <span class="hint">Official college attendance recorded for your second year.</span>
          <span class="field-error" data-error-for="attendance"></span>
        </div>
      </div>
    `;
  } else if (stage === "FOURTH_YEAR") {
    applyDynamicFieldsContainer.innerHTML = `
      <div class="form-grid">
        <div class="form-field">
          <label for="third_year_score">Third Year College Percentage (%) *</label>
          <input type="number" id="third_year_score" name="third_year_score" min="0" max="100" step="0.1" required placeholder="e.g. 83.0" />
          <span class="hint">Aggregate percentage obtained in your third year of college.</span>
          <span class="field-error" data-error-for="third_year_score"></span>
        </div>

        <div class="form-field">
          <label for="second_year_score">Second Year College Percentage (%)</label>
          <input type="number" id="second_year_score" name="second_year_score" min="0" max="100" step="0.1" placeholder="e.g. 81.0" />
          <span class="hint">Aggregate percentage from your second year of college.</span>
          <span class="field-error" data-error-for="second_year_score"></span>
        </div>

        <div class="form-field">
          <label for="attendance">Third Year College Attendance (%) *</label>
          <input type="number" id="attendance" name="attendance" min="0" max="100" step="0.1" required placeholder="e.g. 86.5" />
          <span class="hint">Official college attendance recorded for your third year.</span>
          <span class="field-error" data-error-for="attendance"></span>
        </div>
      </div>
    `;
  } else if (stage === "POSTGRADUATE") {
    applyDynamicFieldsContainer.innerHTML = `
      <div class="form-grid">
        <div class="form-field">
          <label for="ug_score">Undergraduate Final Percentage (%) *</label>
          <input type="number" id="ug_score" name="ug_score" min="0" max="100" step="0.1" required placeholder="e.g. 80.0" />
          <span class="hint">Final overall degree percentage from your undergraduate studies.</span>
          <span class="field-error" data-error-for="ug_score"></span>
        </div>

        <div class="form-field">
          <label for="previous_score">Previous Degree / 12th Percentage (%)</label>
          <input type="number" id="previous_score" name="previous_score" min="0" max="100" step="0.1" placeholder="e.g. 82.0" />
          <span class="hint">Prior qualifying examination or higher secondary score.</span>
          <span class="field-error" data-error-for="previous_score"></span>
        </div>

        <div class="form-field">
          <label for="attendance">Undergraduate Final Attendance (%) *</label>
          <input type="number" id="attendance" name="attendance" min="0" max="100" step="0.1" required placeholder="e.g. 85.0" />
          <span class="hint">Attendance percentage recorded in your undergraduate program.</span>
          <span class="field-error" data-error-for="attendance"></span>
        </div>
      </div>
    `;
  }
}

if (applyStageSelect) {
  renderApplyAcademicFields(applyStageSelect.value || "FIRST_YEAR");
  applyStageSelect.addEventListener("change", () => {
    renderApplyAcademicFields(applyStageSelect.value);
  });
}

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
  const stage = applyStageSelect ? applyStageSelect.value : "FIRST_YEAR";

  if (stage === "FIRST_YEAR") {
    const qscore = parseFloat(document.getElementById("qualifying_score")?.value);
    if (isNaN(qscore) || qscore < 0 || qscore > 100) {
      setFieldError("qualifying_score", "Enter a valid qualifying score between 0 and 100.");
      valid = false;
    }
    const sscVal = document.getElementById("ssc_score")?.value;
    if (sscVal !== undefined && sscVal !== "") {
      const ssc = parseFloat(sscVal);
      if (isNaN(ssc) || ssc < 0 || ssc > 100) {
        setFieldError("ssc_score", "Enter a valid SSC score between 0 and 100.");
        valid = false;
      }
    }
  } else if (stage === "SECOND_YEAR") {
    const fy = parseFloat(document.getElementById("first_year_score")?.value);
    if (isNaN(fy) || fy < 0 || fy > 100) {
      setFieldError("first_year_score", "Enter a first year score between 0 and 100.");
      valid = false;
    }
    const att = parseFloat(document.getElementById("attendance")?.value);
    if (isNaN(att) || att < 0 || att > 100) {
      setFieldError("attendance", "Enter attendance percentage between 0 and 100.");
      valid = false;
    }
  } else if (stage === "THIRD_YEAR") {
    const sy = parseFloat(document.getElementById("second_year_score")?.value);
    if (isNaN(sy) || sy < 0 || sy > 100) {
      setFieldError("second_year_score", "Enter a second year score between 0 and 100.");
      valid = false;
    }
    const att = parseFloat(document.getElementById("attendance")?.value);
    if (isNaN(att) || att < 0 || att > 100) {
      setFieldError("attendance", "Enter attendance percentage between 0 and 100.");
      valid = false;
    }
  } else if (stage === "FOURTH_YEAR") {
    const ty = parseFloat(document.getElementById("third_year_score")?.value);
    if (isNaN(ty) || ty < 0 || ty > 100) {
      setFieldError("third_year_score", "Enter a third year score between 0 and 100.");
      valid = false;
    }
    const att = parseFloat(document.getElementById("attendance")?.value);
    if (isNaN(att) || att < 0 || att > 100) {
      setFieldError("attendance", "Enter attendance percentage between 0 and 100.");
      valid = false;
    }
  } else if (stage === "POSTGRADUATE") {
    const ug = parseFloat(document.getElementById("ug_score")?.value);
    if (isNaN(ug) || ug < 0 || ug > 100) {
      setFieldError("ug_score", "Enter an undergraduate score between 0 and 100.");
      valid = false;
    }
    const att = parseFloat(document.getElementById("attendance")?.value);
    if (isNaN(att) || att < 0 || att > 100) {
      setFieldError("attendance", "Enter attendance percentage between 0 and 100.");
      valid = false;
    }
  }

  const income = parseFloat(document.getElementById("annual_income")?.value);
  if (isNaN(income) || income < 0) {
    setFieldError("annual_income", "Enter a valid, non-negative income.");
    valid = false;
  }

  if (!schemeSelect.value) {
    setFieldError("scholarship_scheme", "Please select a scholarship scheme.");
    valid = false;
  }
  if (!document.getElementById("application_category")?.value) {
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
    decisionKey === "APPROVE" ? "Likely Eligible" : decisionKey === "REJECT" ? "Likely Not Eligible" : "Needs Human Review";

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
          <span class="sub">AI ADVISORY ASSESSMENT</span>
        </div>
        <h2 class="mt-0">Application Evaluation</h2>
        <div class="app-id-box">Application ID: ${result.application_id}</div>

        ${decisionKey === "APPROVE" ? `
        <div class="confidence-meter" style="margin-top:24px;">
          <div class="confidence-meter-label">
            <span>Estimated Approval Probability</span>
            <span>${confidencePct}%</span>
          </div>
          <div class="confidence-meter-track">
            <div class="confidence-meter-fill" style="width:${confidencePct}%;"></div>
          </div>
          <div style="font-size:0.8rem; color:var(--ink-500); margin-top:6px; text-align:left;">
            Estimated probability from the AI model. This is an advisory estimate and does not guarantee approval.
          </div>
        </div>
        ` : `
        <div class="notice notice-info" style="margin-top:20px; text-align:left;">
          ℹ️ <strong>AI Advisory Assessment:</strong> AI-generated assessment for decision support. It does not constitute the final scholarship decision.
        </div>
        `}

        <div class="notice notice-info" style="margin-top:18px; text-align:left;">${summaryText}</div>

        <h3>Top Reasons</h3>
        <ul class="reasons-list">${reasonsHtml}</ul>

        <div class="section-panel" style="text-align:left; margin-top:24px;">
          <div class="section-panel-header"><h3 style="margin:0;">Why did the AI reach this assessment?</h3></div>
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
          AI-generated assessment for decision support. It does not constitute the final scholarship decision.
          Applications are examined through the authorized human review process before a final decision is recorded.
          Save your Application ID to track its status.
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
        `AI Assessment: ${stampLabel}\n` +
        (decisionKey === "APPROVE" ? `Estimated Approval Probability: ${confidencePct}%\n\n` : `\n`) +
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
  const stage = applyStageSelect ? applyStageSelect.value : "FIRST_YEAR";
  fd.append("academic_stage", stage);
  fd.append("annual_income", document.getElementById("annual_income")?.value || "");
  fd.append("application_category", document.getElementById("application_category")?.value || "");
  fd.append("scholarship_scheme", schemeSelect.value);

  if (stage === "FIRST_YEAR") {
    const qtype = document.getElementById("select_qualification_type")?.value || "HSC_12TH";
    const qscore = document.getElementById("qualifying_score")?.value || "";
    const sscScore = document.getElementById("ssc_score")?.value || qscore;
    fd.append("qualification_type", qtype);
    fd.append("qualifying_score", qscore);
    fd.append("ssc_score", sscScore);
    // Canonical mapping for DB & ML
    fd.append("academic_score", qscore);
    fd.append("previous_score", sscScore);
    // Attendance strictly omitted / null for fresh admission
  } else if (stage === "SECOND_YEAR") {
    const fyScore = document.getElementById("first_year_score")?.value || "";
    const qscore = document.getElementById("qualifying_score")?.value || fyScore;
    const att = document.getElementById("attendance")?.value || "";
    fd.append("first_year_score", fyScore);
    fd.append("qualifying_score", qscore);
    fd.append("attendance", att);
    fd.append("academic_score", fyScore);
    fd.append("previous_score", qscore);
  } else if (stage === "THIRD_YEAR") {
    const syScore = document.getElementById("second_year_score")?.value || "";
    const fyScore = document.getElementById("first_year_score")?.value || syScore;
    const att = document.getElementById("attendance")?.value || "";
    fd.append("second_year_score", syScore);
    fd.append("first_year_score", fyScore);
    fd.append("attendance", att);
    fd.append("academic_score", syScore);
    fd.append("previous_score", fyScore);
  } else if (stage === "FOURTH_YEAR") {
    const tyScore = document.getElementById("third_year_score")?.value || "";
    const syScore = document.getElementById("second_year_score")?.value || tyScore;
    const att = document.getElementById("attendance")?.value || "";
    fd.append("third_year_score", tyScore);
    fd.append("second_year_score", syScore);
    fd.append("attendance", att);
    fd.append("academic_score", tyScore);
    fd.append("previous_score", syScore);
  } else if (stage === "POSTGRADUATE") {
    const ugScore = document.getElementById("ug_score")?.value || "";
    const prevScore = document.getElementById("previous_score")?.value || ugScore;
    const att = document.getElementById("attendance")?.value || "";
    fd.append("ug_score", ugScore);
    fd.append("previous_score", prevScore);
    fd.append("attendance", att);
    fd.append("academic_score", ugScore);
  }

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
