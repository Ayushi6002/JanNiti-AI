/**
 * scholarship-predictor.js
 * -------------------------
 * Client logic for the JanNiti AI Scholarship Predictor feature.
 * 
 * Rules:
 * 1. ZERO hardcoded scholarship rules/thresholds in frontend JS.
 *    All eligibility logic is evaluated authoritatively by the backend.
 * 2. Dynamically loads required document list from backend configuration.
 * 3. Handles clean authentication check and draft preservation.
 * 4. Distinguishes rule eligibility status from ML confidence.
 */

const PREDICTOR_DRAFT_KEY = "janniti_predictor_draft";

let activeSchemesConfig = [];
let allDocumentsConfig = [];

document.addEventListener("DOMContentLoaded", async () => {
  initAuthStatusBar();
  await loadPredictorConfig();
  restoreSavedDraft();
  setupEventListeners();
});

/**
 * Format confidence percentage safely without double multiplication.
 * Raw confidence: 0.726 -> Displayed: 72.60%
 * Raw confidence: 0.707 -> Displayed: 70.70%
 * Raw confidence: 0.823 -> Displayed: 82.30%
 */
function formatConfidencePercent(mlPrediction) {
  if (!mlPrediction) return "—";

  if (mlPrediction.confidence_display) {
    return mlPrediction.confidence_display;
  }

  const val =
    mlPrediction.confidence !== undefined
      ? mlPrediction.confidence
      : mlPrediction.confidence_score;

  if (val === undefined || val === null || isNaN(val)) {
    return "—";
  }

  const num = Number(val);
  const pct = num <= 1.0 ? num * 100 : num;

  return pct.toFixed(2) + "%";
}

function getConfidenceWidth(mlPrediction) {
  if (!mlPrediction) return 50;

  const val =
    mlPrediction.confidence !== undefined
      ? mlPrediction.confidence
      : mlPrediction.confidence_score;

  if (val === undefined || val === null || isNaN(val)) {
    return 50;
  }

  const num = Number(val);
  const pct = num <= 1.0 ? num * 100 : num;

  return Math.min(100, Math.max(0, Math.round(pct)));
}

/**
 * Display authentication status in the top notification bar.
 */
function initAuthStatusBar() {
  const statusBar = document.getElementById("auth-status-bar");
  if (!statusBar) return;

  const token = getStoredToken();
  const email = sessionStorage.getItem("janniti_student_email");
  const role = sessionStorage.getItem("janniti_user_role");

  if (token && role === "applicant") {
    statusBar.innerHTML = `
      <div class="notice notice-info" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          👤 Logged in as student <strong>${escapeHtml(email || "Applicant")}</strong>. AI predictions are active.
        </div>
        <a href="user-dashboard.html" style="font-size:0.82rem; font-weight:700; color:var(--navy-700);">Go to Dashboard →</a>
      </div>
    `;
  } else {
    statusBar.innerHTML = `
      <div class="notice notice-info" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          ✨ <strong>Instant Public Estimator:</strong> No login or account required to predict your eligibility.
        </div>
        <a href="user-login.html?redirect=scholarship-predictor.html" id="quick-login-link" style="font-weight:700; color:var(--navy-700);">
          Student Login (to Apply) →
        </a>
      </div>
    `;
  }
}

/**
 * Fetch dynamic configuration from the backend.
 * Obtains the authoritative active scholarship schemes and required document types.
 */
async function loadPredictorConfig() {
  const checklistContainer = document.getElementById("dynamic-doc-checklist");
  if (!checklistContainer) return;

  try {
    const config = await apiGet("/scholarship/predictor-config");
    activeSchemesConfig = config.active_schemes || [];
    allDocumentsConfig = config.all_required_documents || [];

    renderDocumentChecklist(allDocumentsConfig);
  } catch (err) {
    console.warn("Falling back to public schemes endpoint:", err);
    try {
      const schemesRes = await apiGet("/scholarship/schemes");
      const schemes = schemesRes.schemes || [];
      activeSchemesConfig = schemes;

      const docSet = new Set();
      schemes.forEach(s => {
        (s.required_documents || []).forEach(d => docSet.add(d));
      });
      const fallbackDocs = Array.from(docSet).map(d => ({
        type: d,
        label: formatDocLabel(d),
        description: getDocDescription(d),
      }));
      allDocumentsConfig = fallbackDocs;
      renderDocumentChecklist(fallbackDocs);
    } catch (fallbackErr) {
      console.error("Failed to load predictor config:", fallbackErr);
      checklistContainer.innerHTML = `
        <div style="grid-column: 1/-1;" class="notice notice-error">
          Unable to load active scholarship requirements from server. Please refresh or verify the backend service.
        </div>
      `;
    }
  }
}

/**
 * Render checkboxes dynamically based on authoritative configuration.
 */
function renderDocumentChecklist(docs) {
  const container = document.getElementById("dynamic-doc-checklist");
  if (!container) return;

  if (!docs || docs.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; color:var(--ink-500); font-size:0.85rem;">
        No specific documents are mandated by active schemes.
      </div>
    `;
    return;
  }

  container.innerHTML = docs.map(doc => {
    return `
      <label class="doc-check-card" for="doc-chk-${escapeHtml(doc.type)}">
        <input type="checkbox" id="doc-chk-${escapeHtml(doc.type)}" name="doc_${escapeHtml(doc.type)}" value="${escapeHtml(doc.type)}" />
        <div class="doc-check-info">
          <strong>${escapeHtml(doc.label || formatDocLabel(doc.type))}</strong>
          <span>${escapeHtml(doc.description || "Required official document")}</span>
        </div>
      </label>
    `;
  }).join("");

  // Add click toggle styling
  container.querySelectorAll(".doc-check-card").forEach(card => {
    const chk = card.querySelector('input[type="checkbox"]');
    chk.addEventListener("change", () => {
      card.classList.toggle("checked", chk.checked);
    });
  });
}

function formatDocLabel(type) {
  const map = {
    marksheet: "Academic Marksheet",
    income_certificate: "Income Certificate",
    id_proof: "Government ID Proof",
    category_certificate: "Category / Caste Certificate",
  };
  return map[type] || type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function getDocDescription(type) {
  const map = {
    marksheet: "Marksheet of previous qualifying exam",
    income_certificate: "Authorized family income certificate",
    id_proof: "Aadhaar, Voter ID, or College Photo ID",
    category_certificate: "OBC / SC / ST / EWS community certificate",
  };
  return map[type] || "Required supporting document";
}

/**
 * Setup form submission, reset, and live validation.
 */
function setupEventListeners() {
  const form = document.getElementById("scholarship-predictor-form");
  if (form) {
    form.addEventListener("submit", handlePredictSubmit);
  }

  const resetBtn = document.getElementById("reset-form-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      form.reset();
      document.querySelectorAll(".doc-check-card").forEach(c => c.classList.remove("checked"));
      sessionStorage.removeItem(PREDICTOR_DRAFT_KEY);
      const resultsSection = document.getElementById("results-section");
      if (resultsSection) resultsSection.style.display = "none";
      showNotice("", "clear");
    });
  }

  // Preserve draft on input changes
  form.addEventListener("input", saveDraftToStorage);
  form.addEventListener("change", saveDraftToStorage);
}

function gatherFormData() {
  const academicScore = parseFloat(document.getElementById("input-academic-score").value);
  const previousScore = parseFloat(document.getElementById("input-previous-score").value);
  const attendance = parseFloat(document.getElementById("input-attendance").value);
  const annualIncome = parseFloat(document.getElementById("input-annual-income").value);
  const category = document.getElementById("input-category").value;

  const documents = {};
  const chks = document.querySelectorAll('#dynamic-doc-checklist input[type="checkbox"]');
  chks.forEach(chk => {
    documents[chk.value] = chk.checked;
  });

  return {
    academic_score: academicScore,
    previous_score: previousScore,
    attendance: attendance,
    annual_income: annualIncome,
    application_category: category,
    documents: documents,
  };
}

function saveDraftToStorage() {
  try {
    const data = gatherFormData();
    sessionStorage.setItem(PREDICTOR_DRAFT_KEY, JSON.stringify(data));
  } catch (err) {
    // Ignore storage issues
  }
}

function restoreSavedDraft() {
  try {
    const draftJson = sessionStorage.getItem(PREDICTOR_DRAFT_KEY);
    if (!draftJson) return;
    const data = JSON.parse(draftJson);

    if (data.academic_score !== undefined && !isNaN(data.academic_score)) {
      document.getElementById("input-academic-score").value = data.academic_score;
    }
    if (data.previous_score !== undefined && !isNaN(data.previous_score)) {
      document.getElementById("input-previous-score").value = data.previous_score;
    }
    if (data.attendance !== undefined && !isNaN(data.attendance)) {
      document.getElementById("input-attendance").value = data.attendance;
    }
    if (data.annual_income !== undefined && !isNaN(data.annual_income)) {
      document.getElementById("input-annual-income").value = data.annual_income;
    }
    if (data.application_category) {
      document.getElementById("input-category").value = data.application_category;
    }

    if (data.documents && typeof data.documents === "object") {
      Object.entries(data.documents).forEach(([type, checked]) => {
        const chk = document.getElementById(`doc-chk-${type}`);
        if (chk) {
          chk.checked = !!checked;
          const card = chk.closest(".doc-check-card");
          if (card) card.classList.toggle("checked", !!checked);
        }
      });
    }
  } catch (err) {
    console.warn("Could not restore draft:", err);
  }
}

/**
 * Handle form submission and trigger prediction API.
 */
async function handlePredictSubmit(e) {
  e.preventDefault();
  showNotice("", "clear");

  const formData = gatherFormData();

  // Client-side numerical validation
  if (isNaN(formData.academic_score) || formData.academic_score < 0 || formData.academic_score > 100) {
    showNotice("Academic score must be a number between 0 and 100.", "error");
    document.getElementById("input-academic-score").focus();
    return;
  }
  if (isNaN(formData.previous_score) || formData.previous_score < 0 || formData.previous_score > 100) {
    showNotice("Previous academic score must be a number between 0 and 100.", "error");
    document.getElementById("input-previous-score").focus();
    return;
  }
  if (isNaN(formData.attendance) || formData.attendance < 0 || formData.attendance > 100) {
    showNotice("Attendance must be a number between 0 and 100.", "error");
    document.getElementById("input-attendance").focus();
    return;
  }
  if (isNaN(formData.annual_income) || formData.annual_income < 0) {
    showNotice("Annual family income must be a valid positive number.", "error");
    document.getElementById("input-annual-income").focus();
    return;
  }

  const submitBtn = document.getElementById("btn-predict-submit");
  const origBtnContent = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span> <span>Analyzing Profile...</span>`;

  try {
    const response = await apiPost("/scholarship/predict", formData);
    renderPredictionResults(response);
  } catch (err) {
    console.error("Prediction error:", err);
    showNotice(err.message || "Failed to process prediction. Please check your network or try again.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = origBtnContent;
  }
}

/**
 * Render the prediction results in the impressive results section.
 */
function renderPredictionResults(res) {
  const section = document.getElementById("results-section");
  if (!section) return;

  section.style.display = "block";
  section.scrollIntoView({ behavior: "smooth", block: "start" });

  document.getElementById("res-total-schemes").textContent = res.total_evaluated || (res.schemes ? res.schemes.length : 3);

  // 1. Render Best Match
  const bestMatch = res.best_match;
  const bestContainer = document.getElementById("best-match-container");

  if (bestMatch) {
    bestContainer.style.display = "block";
    document.getElementById("best-match-title").textContent = bestMatch.scheme_name || bestMatch.scheme_code;
    document.getElementById("best-match-desc").textContent = bestMatch.description || "Recommended scholarship scheme matching your academic and financial profile.";

    const badgeContainer = document.getElementById("best-match-status-badge");
    badgeContainer.innerHTML = renderStatusPill(bestMatch.eligibility_status);

    // ML Indicators
    const mlPred = (bestMatch.ml_prediction && bestMatch.ml_prediction.prediction) || "NEEDS_HUMAN_REVIEW";
    const mlConf = formatConfidencePercent(bestMatch.ml_prediction);

    document.getElementById("best-match-ml-pred").textContent = formatDecisionLabel(mlPred);
    document.getElementById("best-match-ml-conf").textContent = mlConf;
    document.getElementById("best-match-ml-conf-text").textContent = mlConf;

    const fillWidth = getConfidenceWidth(bestMatch.ml_prediction);
    document.getElementById("best-match-confidence-fill").style.width = `${fillWidth}%`;

    const advisoryEl = document.getElementById("best-match-advisory-note");
    if (advisoryEl) {
      if (bestMatch.eligibility_status === "NOT_ELIGIBLE" && (mlPred === "APPROVE" || bestMatch.ml_prediction?.decision === "APPROVE")) {
        advisoryEl.style.display = "block";
        advisoryEl.innerHTML = `<em>ℹ️ ${escapeHtml(bestMatch.ml_prediction?.advisory_note || "The AI model's prediction is an advisory signal based on historical training data. Current scholarship eligibility rules take precedence.")}</em>`;
      } else {
        advisoryEl.style.display = "none";
      }
    }

    // Criteria Lists
    const passedList = document.getElementById("best-match-passed-list");
    const failedList = document.getElementById("best-match-failed-list");
    const failedBox = document.getElementById("best-match-failed-box");

    const passedCriteria = bestMatch.passed_criteria || [];
    const failedCriteria = bestMatch.failed_criteria || [];
    const missingDocs = bestMatch.missing_documents || [];

    passedList.innerHTML = passedCriteria.length > 0
      ? passedCriteria.map(c => `<li><span style="color:var(--green-700); font-weight:700;">✓</span> <span>${escapeHtml(c.message || c.rule_type)}</span></li>`).join("")
      : `<li><span style="color:var(--ink-500);">No specific criteria passed</span></li>`;

    if (failedCriteria.length > 0 || missingDocs.length > 0) {
      failedBox.style.display = "block";
      const failedItemsHtml = [
        ...failedCriteria.map(c => `<li><span style="color:var(--red-700); font-weight:700;">✗</span> <span>${escapeHtml(c.message || c.rule_type)}</span></li>`),
        ...missingDocs.map(d => `<li><span style="color:var(--amber-700); font-weight:700;">⚠</span> <span>Missing required document: <strong>${escapeHtml(formatDocLabel(d))}</strong></span></li>`),
      ].join("");
      failedList.innerHTML = failedItemsHtml;
    } else {
      failedBox.style.display = "none";
      failedList.innerHTML = "";
    }

  } else {
    bestContainer.style.display = "none";
  }

  // 2. Render All Evaluated Schemes
  const otherGrid = document.getElementById("other-schemes-grid");
  const schemes = res.schemes || [];

  otherGrid.innerHTML = schemes.map(sch => {
    const isBest = bestMatch && sch.scheme_code === bestMatch.scheme_code;
    const cardStatusClass = sch.eligibility_status === "ELIGIBLE"
      ? "card-eligible"
      : sch.eligibility_status === "NEEDS_VERIFICATION"
        ? "card-needs-verification"
        : "card-not-eligible";

    const mlConfPercent = formatConfidencePercent(sch.ml_prediction);
    const hasDisagreement = sch.eligibility_status === "NOT_ELIGIBLE" &&
      (sch.ml_prediction?.prediction === "APPROVE" || sch.ml_prediction?.decision === "APPROVE");

    return `
      <div class="scheme-card ${cardStatusClass}">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
            <h4 style="margin:0; font-size:1.05rem; color:var(--navy-900);">
              ${escapeHtml(sch.scheme_name || sch.scheme_code)}
              ${isBest ? `<span style="font-size:0.7rem; background:var(--gold-600); color:var(--navy-950); padding:2px 6px; border-radius:4px; margin-left:6px; font-weight:800;">BEST</span>` : ""}
            </h4>
            ${renderStatusPill(sch.eligibility_status)}
          </div>
          <p style="font-size:0.8rem; color:var(--ink-500); margin:6px 0 10px;">
            ${escapeHtml(sch.description || "")}
          </p>

          <div style="background:#f8fafc; border-radius:6px; padding:8px 12px; margin-bottom:10px; font-size:0.78rem;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <span>AI Model Assessment:</span>
              <strong style="color:var(--navy-900);">${escapeHtml(formatDecisionLabel(sch.ml_prediction?.prediction || "REVIEW"))}</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span>Model Confidence:</span>
              <strong style="color:var(--teal-600);">${mlConfPercent}</strong>
            </div>
            ${hasDisagreement ? `
              <div style="margin-top:6px; font-size:0.74rem; color:var(--ink-500); line-height:1.35; border-top:1px dashed var(--hairline); padding-top:4px;">
                <em>ℹ️ ${escapeHtml(sch.ml_prediction?.advisory_note || "The AI model's prediction is an advisory signal based on historical training data. Current scholarship eligibility rules take precedence.")}</em>
              </div>
            ` : ""}
          </div>

          <div style="font-size:0.8rem; line-height:1.45;">
            ${sch.eligibility_status === "ELIGIBLE"
        ? `<div style="color:var(--green-700);">✓ Meets academic & financial thresholds</div>`
        : sch.failed_criteria && sch.failed_criteria.length > 0
          ? `<div style="color:var(--red-700);">✗ ${escapeHtml(sch.failed_criteria[0].message)}</div>`
          : sch.missing_documents && sch.missing_documents.length > 0
            ? `<div style="color:var(--amber-700);">⚠ Missing ${escapeHtml(formatDocLabel(sch.missing_documents[0]))}</div>`
            : `<div style="color:var(--ink-500);">${escapeHtml(sch.qualification_reason || "")}</div>`
      }
          </div>
        </div>

        <div style="border-top:1px dashed var(--hairline); padding-top:10px; font-size:0.75rem; color:var(--ink-500); display:flex; justify-content:space-between;">
          <span>Passed Rules: <strong>${sch.passed_rules_count || 0}</strong></span>
          <span>Failed: <strong>${sch.failed_rules_count || 0}</strong></span>
        </div>
      </div>
    `;
  }).join("");

  // 3. Render Document Readiness
  const readiness = res.document_readiness || {};
  const readyList = readiness.provided || [];
  const missingList = readiness.missing || [];
  const totalDocs = readyList.length + missingList.length;

  const docSummaryBadge = document.getElementById("doc-readiness-summary-badge");
  docSummaryBadge.innerHTML = `
    <span class="status-pill ${readiness.complete ? "status-eligible" : "status-needs-verification"}">
      ${readyList.length} of ${totalDocs} Documents Ready
    </span>
  `;

  const pillsContainer = document.getElementById("doc-readiness-pills");
  const readyPillsHtml = readyList.map(d => `
    <span class="doc-status-pill ready">
      ✓ ${escapeHtml(formatDocLabel(d))} (Available)
    </span>
  `);
  const missingPillsHtml = missingList.map(d => `
    <span class="doc-status-pill missing">
      ✗ ${escapeHtml(formatDocLabel(d))} (Missing)
    </span>
  `);

  pillsContainer.innerHTML = [...readyPillsHtml, ...missingPillsHtml].join("") || `<span style="color:var(--ink-500);">No specific documents tracked.</span>`;

  // 4. Update Disclaimer
  if (res.disclaimer) {
    document.getElementById("disclaimer-text").textContent = res.disclaimer;
  }

  // 5. Render SHAP TreeExplainer Model Explainability
  const bestShap = (bestMatch && bestMatch.ml_prediction && bestMatch.ml_prediction.shap_explanation) || res.shap_explanation;
  renderShapExplanation(bestShap);
}

/**
 * Render the SHAP explainability panel for the evaluated prediction.
 */
function renderShapExplanation(shapData) {
  const panel = document.getElementById("best-match-shap-panel");
  if (!panel) return;

  if (!shapData) {
    panel.style.display = "none";
    return;
  }

  if (shapData.status === "unavailable") {
    panel.style.display = "block";
    const summaryEl = document.getElementById("shap-summary-text");
    if (summaryEl) {
      summaryEl.innerHTML = `<span style="color:var(--amber-800); background:#fffbeb; padding:6px 10px; border-radius:4px; display:inline-block;">ℹ️ ${escapeHtml(shapData.message || "AI prediction is available, but detailed explanation could not be generated.")}</span>`;
    }
    const posList = document.getElementById("shap-positive-factors-list");
    const negList = document.getElementById("shap-negative-factors-list");
    if (posList) posList.innerHTML = `<span style="font-size:0.8rem; color:var(--ink-500);">Explanation unavailable</span>`;
    if (negList) negList.innerHTML = `<span style="font-size:0.8rem; color:var(--ink-500);">Explanation unavailable</span>`;
    const inspector = document.getElementById("shap-feature-inspector");
    if (inspector) inspector.style.display = "none";
    return;
  }

  if (shapData.status !== "success" || !shapData.explanation) {
    panel.style.display = "none";
    return;
  }

  panel.style.display = "block";
  const exp = shapData.explanation;
  const features = exp.features || [];

  // Update base value
  const baseEl = document.getElementById("shap-base-value");
  if (baseEl) {
    const baseNum = Number(exp.base_value);
    baseEl.textContent = isNaN(baseNum) ? "0.33" : (baseNum >= 0 ? `+${baseNum.toFixed(3)}` : baseNum.toFixed(3));
  }

  // Update summary
  const summaryEl = document.getElementById("shap-summary-text");
  if (summaryEl) {
    summaryEl.textContent = exp.summary || "The following factors from your profile influenced the machine learning model's prediction.";
  }

  // Split into positive and negative
  const posFeatures = features.filter(f => f.direction === "positive");
  const negFeatures = features.filter(f => f.direction === "negative");
  const neuFeatures = features.filter(f => f.direction === "neutral");

  // Determine scale for horizontal bars (normalize to largest absolute shap value, min 0.30)
  const maxAbsShap = Math.max(0.30, ...features.map(f => Math.abs(f.shap_value || 0)));

  const renderFactorRow = (feat) => {
    const shapVal = Number(feat.shap_value || 0);
    const absVal = Math.abs(shapVal);
    const fillPercent = Math.min(100, Math.max(4, Math.round((absVal / maxAbsShap) * 100)));
    const isPos = feat.direction === "positive";
    const isNeg = feat.direction === "negative";
    const badgeClass = isPos ? "positive" : isNeg ? "negative" : "neutral";
    const fillClass = isPos ? "shap-bar-fill-pos" : isNeg ? "shap-bar-fill-neg" : "shap-bar-fill-neu";
    const signPrefix = shapVal > 0 ? "+" : "";
    const formattedVal = `${signPrefix}${shapVal.toFixed(3)}`;
    const formattedInput = formatFeatureDisplayValue(feat.feature, feat.input_value);

    return `
      <div class="shap-bar-row" data-feature="${escapeHtml(feat.feature)}" role="button" tabindex="0" title="Click to inspect ${escapeHtml(feat.display_name)}">
        <div class="shap-feat-meta">
          <span class="shap-feat-name">${escapeHtml(feat.display_name)}</span>
          <span class="shap-feat-input">Input: ${escapeHtml(formattedInput)}</span>
        </div>
        <div class="shap-bar-track">
          <div class="${fillClass}" style="width: ${fillPercent}%;"></div>
        </div>
        <div class="shap-val-badge ${badgeClass}">
          ${formattedVal}
        </div>
      </div>
    `;
  };

  const posList = document.getElementById("shap-positive-factors-list");
  if (posList) {
    if (posFeatures.length > 0) {
      posList.innerHTML = posFeatures.map(renderFactorRow).join("");
    } else {
      posList.innerHTML = `<div style="font-size:0.78rem; color:var(--ink-500); padding:4px 0;">No strong positive influences detected for this prediction.</div>`;
    }
  }

  const negList = document.getElementById("shap-negative-factors-list");
  if (negList) {
    const combinedNeg = [...negFeatures, ...neuFeatures];
    if (combinedNeg.length > 0) {
      negList.innerHTML = combinedNeg.map(renderFactorRow).join("");
    } else {
      negList.innerHTML = `<div style="font-size:0.78rem; color:var(--ink-500); padding:4px 0;">No negative influences detected for this prediction.</div>`;
    }
  }

  // Setup click-to-inspect interactivity
  const inspector = document.getElementById("shap-feature-inspector");
  const allRows = panel.querySelectorAll(".shap-bar-row");

  allRows.forEach(row => {
    const featKey = row.getAttribute("data-feature");
    const featObj = features.find(f => f.feature === featKey);
    if (!featObj) return;

    const activateRow = () => {
      allRows.forEach(r => r.classList.remove("active-inspected"));
      row.classList.add("active-inspected");

      if (inspector) {
        inspector.style.display = "block";
        document.getElementById("inspector-feat-title").textContent = featObj.display_name;

        const badgeEl = document.getElementById("inspector-feat-impact-badge");
        if (badgeEl) {
          badgeEl.textContent = `${(featObj.impact || "medium").toUpperCase()} IMPACT`;
          badgeEl.className = `inspector-badge ${featObj.direction === "positive" ? "pos" : featObj.direction === "negative" ? "neg" : "neu"}`;
        }

        const inputEl = document.getElementById("inspector-feat-input");
        if (inputEl) {
          inputEl.textContent = formatFeatureDisplayValue(featObj.feature, featObj.input_value);
        }

        const shapEl = document.getElementById("inspector-feat-shap");
        if (shapEl) {
          const sVal = Number(featObj.shap_value || 0);
          shapEl.textContent = `${sVal > 0 ? "+" : ""}${sVal.toFixed(3)}`;
          shapEl.style.color = featObj.direction === "positive" ? "var(--green-700)" : featObj.direction === "negative" ? "var(--red-700)" : "var(--ink-700)";
        }

        const dirEl = document.getElementById("inspector-feat-direction");
        if (dirEl) {
          dirEl.textContent = featObj.direction.charAt(0).toUpperCase() + featObj.direction.slice(1);
        }

        const expEl = document.getElementById("inspector-feat-explanation");
        if (expEl) {
          expEl.textContent = featObj.explanation || "";
        }

        inspector.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    };

    row.addEventListener("click", activateRow);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activateRow();
      }
    });
  });

  // Setup close inspector button
  const closeBtn = document.getElementById("close-inspector-btn");
  if (closeBtn) {
    closeBtn.onclick = () => {
      if (inspector) inspector.style.display = "none";
      allRows.forEach(r => r.classList.remove("active-inspected"));
    };
  }
}

function formatFeatureDisplayValue(feature, val) {
  if (val === undefined || val === null) return "N/A";
  if (feature === "annual_income") {
    const num = Number(val);
    return isNaN(num) ? String(val) : `₹${num.toLocaleString("en-IN")}`;
  }
  if (feature === "academic_score" || feature === "previous_score" || feature === "attendance") {
    const num = Number(val);
    return isNaN(num) ? String(val) : `${num}%`;
  }
  return String(val);
}

function renderStatusPill(status) {
  if (status === "ELIGIBLE") {
    return `<span class="status-pill status-eligible">✓ ELIGIBLE</span>`;
  }
  if (status === "NEEDS_VERIFICATION") {
    return `<span class="status-pill status-needs-verification">⚠ NEEDS VERIFICATION</span>`;
  }
  return `<span class="status-pill status-not-eligible">✗ NOT ELIGIBLE</span>`;
}

function showNotice(msg, type = "info") {
  const box = document.getElementById("notice-box");
  if (!box) return;

  if (type === "clear" || !msg) {
    box.innerHTML = "";
    return;
  }

  const cssClass = type === "error" ? "notice-error" : type === "success" ? "notice-success" : "notice-info";
  box.innerHTML = `
    <div class="notice ${cssClass}" style="margin-bottom:18px;">
      ${escapeHtml(msg)}
    </div>
  `;
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
