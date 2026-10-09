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
  initAcademicStage();
  restoreSavedDraft();
  setupEventListeners();
});

/**
 * Maps ML prediction keys to user-facing AI Assessment labels.
 * If window.formatAIAssessmentLabel is globally provided by api.js, delegates to it.
 * // AI Model Assessment mapping
 */
function formatAIAssessmentLabel(prediction) {
  if (typeof window !== "undefined" && typeof window.formatAIAssessmentLabel === "function" && window.formatAIAssessmentLabel !== formatAIAssessmentLabel) {
    return window.formatAIAssessmentLabel(prediction);
  }
  const map = {
    APPROVE: "Likely Eligible",
    REJECT: "Likely Not Eligible",
    NEEDS_HUMAN_REVIEW: "Needs Human Review",
    ML_PROCESSING_PENDING: "ML Processing Pending",
  };
  return map[prediction] || prediction;
}

if (typeof window !== "undefined" && !window.formatAIAssessmentLabel) {
  window.formatAIAssessmentLabel = formatAIAssessmentLabel;
}

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
 * Setup Academic Stage selector and dynamic field rendering.
 */
function initAcademicStage() {
  const stageSelect = document.getElementById("select-academic-stage");
  if (!stageSelect) return;

  // Render initial academic fields
  renderAcademicFields(stageSelect.value || "FIRST_YEAR");

  stageSelect.addEventListener("change", () => {
    // Re-rendering clears stale inputs from old stage to prevent accidental submission of hidden data
    renderAcademicFields(stageSelect.value);
    saveDraftToStorage();
  });
}

/**
 * Dynamically render tailored academic fields based on chosen Academic Stage.
 * Ensures data integrity:
 * - First-year applicants do NOT provide current college metrics or college attendance.
 * - Continuing years provide tailored, logically named prior year and attendance records.
 */
function renderAcademicFields(stage) {
  const container = document.getElementById("dynamic-academic-fields");
  if (!container) return;

  if (stage === "FIRST_YEAR") {
    container.innerHTML = `
      <div class="stage-notice-callout">
        <span>ℹ️</span>
        <div>
          <strong>First-Year / Fresh Admission:</strong> Since you are applying for first-year admission, your most recent completed qualification is used for academic assessment.
        </div>
      </div>

      <div class="form-grid-2" style="margin-bottom:18px;">
        <div class="form-field">
          <label for="select-qualification-type">Most Recent Completed Qualification *</label>
          <select id="select-qualification-type" name="qualification_type" required>
            <option value="HSC">HSC / 12th Standard</option>
            <option value="DIPLOMA">Diploma</option>
            <option value="OTHER">Other qualifying examination</option>
          </select>
          <div class="field-hint">Select the examination qualifying you for college admission.</div>
        </div>
      </div>

      <div class="form-grid-3">
        <div class="form-field">
          <label id="label-qualifying-score" for="input-qualifying-score">Qualifying Examination Score (%) *</label>
          <input type="number" id="input-qualifying-score" name="qualifying_score" min="0" max="100" step="0.1" required
            placeholder="e.g. 85.0" />
          <div class="field-hint" id="hint-qualifying-score">HSC / 12th Standard aggregate percentage.</div>
        </div>
        <div class="form-field">
          <label for="input-ssc-score">SSC / 10th Percentage (%)</label>
          <input type="number" id="input-ssc-score" name="ssc_score" min="0" max="100" step="0.1"
            placeholder="e.g. 82.0" />
          <div class="field-hint">Secondary school examination percentage.</div>
        </div>
        <div class="attendance-na-card">
          <div class="attendance-na-label">College Attendance</div>
          <div class="attendance-na-badge">Not applicable — first-year admission</div>
          <p class="attendance-na-desc">
            You have not started your college program yet, so current college attendance is not available. Waived for fresh admission.
          </p>
        </div>
      </div>
    `;

    const qualSelect = document.getElementById("select-qualification-type");
    if (qualSelect) {
      qualSelect.addEventListener("change", () => {
        updateQualLabels(qualSelect.value);
        saveDraftToStorage();
      });
    }
  } else if (stage === "SECOND_YEAR") {
    container.innerHTML = `
      <div class="form-grid-3">
        <div class="form-field">
          <label for="input-first-year-score">First Year College Percentage (%) *</label>
          <input type="number" id="input-first-year-score" name="first_year_score" min="0" max="100" step="0.1" required
            placeholder="e.g. 78.5" />
          <div class="field-hint">Aggregate percentage obtained across 1st & 2nd semesters of college.</div>
        </div>
        <div class="form-field">
          <label for="input-qualifying-score">12th / Diploma Percentage (%)</label>
          <input type="number" id="input-qualifying-score" name="qualifying_score" min="0" max="100" step="0.1"
            placeholder="e.g. 84.0" />
          <div class="field-hint">Qualifying score prior to entering college.</div>
        </div>
        <div class="form-field">
          <label for="input-attendance">First Year College Attendance (%) *</label>
          <input type="number" id="input-attendance" name="attendance" min="0" max="100" step="0.1" required
            placeholder="e.g. 85.0" />
          <div class="field-hint">Official attendance record from your first year of college.</div>
        </div>
      </div>
    `;
  } else if (stage === "THIRD_YEAR") {
    container.innerHTML = `
      <div class="form-grid-3">
        <div class="form-field">
          <label for="input-second-year-score">Second Year College Percentage (%) *</label>
          <input type="number" id="input-second-year-score" name="second_year_score" min="0" max="100" step="0.1" required
            placeholder="e.g. 81.0" />
          <div class="field-hint">Aggregate percentage obtained in your second year of college.</div>
        </div>
        <div class="form-field">
          <label for="input-first-year-score">First Year College Percentage (%)</label>
          <input type="number" id="input-first-year-score" name="first_year_score" min="0" max="100" step="0.1"
            placeholder="e.g. 78.5" />
          <div class="field-hint">Aggregate percentage from your first year of college.</div>
        </div>
        <div class="form-field">
          <label for="input-attendance">Second Year College Attendance (%) *</label>
          <input type="number" id="input-attendance" name="attendance" min="0" max="100" step="0.1" required
            placeholder="e.g. 88.0" />
          <div class="field-hint">Official college attendance recorded for your second year.</div>
        </div>
      </div>
    `;
  } else if (stage === "FOURTH_YEAR") {
    container.innerHTML = `
      <div class="form-grid-3">
        <div class="form-field">
          <label for="input-third-year-score">Third Year College Percentage (%) *</label>
          <input type="number" id="input-third-year-score" name="third_year_score" min="0" max="100" step="0.1" required
            placeholder="e.g. 83.0" />
          <div class="field-hint">Aggregate percentage obtained in your third year of college.</div>
        </div>
        <div class="form-field">
          <label for="input-second-year-score">Second Year College Percentage (%)</label>
          <input type="number" id="input-second-year-score" name="second_year_score" min="0" max="100" step="0.1"
            placeholder="e.g. 81.0" />
          <div class="field-hint">Aggregate percentage from your second year of college.</div>
        </div>
        <div class="form-field">
          <label for="input-attendance">Third Year College Attendance (%) *</label>
          <input type="number" id="input-attendance" name="attendance" min="0" max="100" step="0.1" required
            placeholder="e.g. 86.5" />
          <div class="field-hint">Official college attendance recorded for your third year.</div>
        </div>
      </div>
    `;
  } else if (stage === "POSTGRADUATE") {
    container.innerHTML = `
      <div class="form-grid-3">
        <div class="form-field">
          <label for="input-ug-score">Undergraduate Final Percentage (%) *</label>
          <input type="number" id="input-ug-score" name="ug_score" min="0" max="100" step="0.1" required
            placeholder="e.g. 80.0" />
          <div class="field-hint">Final overall degree percentage from your undergraduate studies.</div>
        </div>
        <div class="form-field">
          <label for="input-previous-score">Previous Degree / 12th Percentage (%)</label>
          <input type="number" id="input-previous-score" name="previous_score" min="0" max="100" step="0.1"
            placeholder="e.g. 82.0" />
          <div class="field-hint">Prior qualifying examination or higher secondary score.</div>
        </div>
        <div class="form-field">
          <label for="input-attendance">Undergraduate Final Attendance (%) *</label>
          <input type="number" id="input-attendance" name="attendance" min="0" max="100" step="0.1" required
            placeholder="e.g. 85.0" />
          <div class="field-hint">Attendance percentage recorded in your undergraduate program.</div>
        </div>
      </div>
    `;
  }
}

function updateQualLabels(qualType) {
  const labelEl = document.getElementById("label-qualifying-score");
  const hintEl = document.getElementById("hint-qualifying-score");
  if (!labelEl) return;
  if (qualType === "DIPLOMA") {
    labelEl.textContent = "Diploma Percentage (%) *";
    if (hintEl) hintEl.textContent = "Aggregate percentage across all completed diploma semesters.";
  } else if (qualType === "HSC") {
    labelEl.textContent = "Qualifying Examination Score (%) *";
    if (hintEl) hintEl.textContent = "HSC / 12th Standard aggregate percentage.";
  } else {
    labelEl.textContent = "Qualifying Examination Score (%) *";
    if (hintEl) hintEl.textContent = "Qualifying entrance or equivalent board aggregate percentage.";
  }
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
      const stageSelect = document.getElementById("select-academic-stage");
      if (stageSelect) stageSelect.value = "FIRST_YEAR";
      renderAcademicFields("FIRST_YEAR");
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
  const stage = document.getElementById("select-academic-stage")?.value || "FIRST_YEAR";
  const annualIncome = parseFloat(document.getElementById("input-annual-income")?.value);
  const category = document.getElementById("input-category")?.value;

  const documents = {};
  const chks = document.querySelectorAll('#dynamic-doc-checklist input[type="checkbox"]');
  chks.forEach(chk => {
    documents[chk.value] = chk.checked;
  });

  const payload = {
    academic_stage: stage,
    annual_income: annualIncome,
    application_category: category,
    documents: documents,
  };

  if (stage === "FIRST_YEAR") {
    const qualType = document.getElementById("select-qualification-type")?.value || "HSC";
    const qualScore = parseFloat(document.getElementById("input-qualifying-score")?.value);
    const sscScoreRaw = document.getElementById("input-ssc-score")?.value;
    const sscScore = sscScoreRaw !== undefined && sscScoreRaw !== "" ? parseFloat(sscScoreRaw) : qualScore;

    payload.qualification_type = qualType;
    payload.qualifying_score = isNaN(qualScore) ? null : qualScore;
    payload.ssc_score = isNaN(sscScore) ? null : sscScore;
    // Canonical mapping for ML & rules
    payload.academic_score = payload.qualifying_score;
    payload.previous_score = payload.ssc_score;
    payload.attendance = null; // Strictly null: never 0 or 75
  } else if (stage === "SECOND_YEAR") {
    const fyScore = parseFloat(document.getElementById("input-first-year-score")?.value);
    const qualScoreRaw = document.getElementById("input-qualifying-score")?.value;
    const qualScore = qualScoreRaw !== undefined && qualScoreRaw !== "" ? parseFloat(qualScoreRaw) : fyScore;
    const att = parseFloat(document.getElementById("input-attendance")?.value);

    payload.first_year_score = isNaN(fyScore) ? null : fyScore;
    payload.qualifying_score = isNaN(qualScore) ? null : qualScore;
    payload.attendance = isNaN(att) ? null : att;
    // Canonical mapping
    payload.academic_score = payload.first_year_score;
    payload.previous_score = payload.qualifying_score;
  } else if (stage === "THIRD_YEAR") {
    const syScore = parseFloat(document.getElementById("input-second-year-score")?.value);
    const fyScoreRaw = document.getElementById("input-first-year-score")?.value;
    const fyScore = fyScoreRaw !== undefined && fyScoreRaw !== "" ? parseFloat(fyScoreRaw) : syScore;
    const att = parseFloat(document.getElementById("input-attendance")?.value);

    payload.second_year_score = isNaN(syScore) ? null : syScore;
    payload.first_year_score = isNaN(fyScore) ? null : fyScore;
    payload.attendance = isNaN(att) ? null : att;
    // Canonical mapping
    payload.academic_score = payload.second_year_score;
    payload.previous_score = payload.first_year_score;
  } else if (stage === "FOURTH_YEAR") {
    const tyScore = parseFloat(document.getElementById("input-third-year-score")?.value);
    const syScoreRaw = document.getElementById("input-second-year-score")?.value;
    const syScore = syScoreRaw !== undefined && syScoreRaw !== "" ? parseFloat(syScoreRaw) : tyScore;
    const att = parseFloat(document.getElementById("input-attendance")?.value);

    payload.third_year_score = isNaN(tyScore) ? null : tyScore;
    payload.second_year_score = isNaN(syScore) ? null : syScore;
    payload.attendance = isNaN(att) ? null : att;
    // Canonical mapping
    payload.academic_score = payload.third_year_score;
    payload.previous_score = payload.second_year_score;
  } else if (stage === "POSTGRADUATE") {
    const ugScore = parseFloat(document.getElementById("input-ug-score")?.value);
    const prevScoreRaw = document.getElementById("input-previous-score")?.value;
    const prevScore = prevScoreRaw !== undefined && prevScoreRaw !== "" ? parseFloat(prevScoreRaw) : ugScore;
    const att = parseFloat(document.getElementById("input-attendance")?.value);

    payload.ug_score = isNaN(ugScore) ? null : ugScore;
    payload.previous_score = isNaN(prevScore) ? null : prevScore;
    payload.attendance = isNaN(att) ? null : att;
    // Canonical mapping
    payload.academic_score = payload.ug_score;
  }

  return payload;
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

    if (data.academic_stage) {
      const stageSelect = document.getElementById("select-academic-stage");
      if (stageSelect) {
        stageSelect.value = data.academic_stage;
        renderAcademicFields(data.academic_stage);
      }
    }

    if (data.qualification_type) {
      const qualSelect = document.getElementById("select-qualification-type");
      if (qualSelect) {
        qualSelect.value = data.qualification_type;
        updateQualLabels(data.qualification_type);
      }
    }

    // Populate stage-specific inputs if present
    if (data.qualifying_score !== undefined && data.qualifying_score !== null) {
      const el = document.getElementById("input-qualifying-score");
      if (el) el.value = data.qualifying_score;
    }
    if (data.ssc_score !== undefined && data.ssc_score !== null) {
      const el = document.getElementById("input-ssc-score");
      if (el) el.value = data.ssc_score;
    }
    if (data.first_year_score !== undefined && data.first_year_score !== null) {
      const el = document.getElementById("input-first-year-score");
      if (el) el.value = data.first_year_score;
    }
    if (data.second_year_score !== undefined && data.second_year_score !== null) {
      const el = document.getElementById("input-second-year-score");
      if (el) el.value = data.second_year_score;
    }
    if (data.third_year_score !== undefined && data.third_year_score !== null) {
      const el = document.getElementById("input-third-year-score");
      if (el) el.value = data.third_year_score;
    }
    if (data.ug_score !== undefined && data.ug_score !== null) {
      const el = document.getElementById("input-ug-score");
      if (el) el.value = data.ug_score;
    }
    if (data.previous_score !== undefined && data.previous_score !== null) {
      const el = document.getElementById("input-previous-score");
      if (el) el.value = data.previous_score;
    }
    if (data.attendance !== undefined && data.attendance !== null) {
      const el = document.getElementById("input-attendance");
      if (el) el.value = data.attendance;
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

  // Stage-aware numerical validation
  if (formData.academic_stage === "FIRST_YEAR") {
    if (formData.qualifying_score === null || isNaN(formData.qualifying_score) || formData.qualifying_score < 0 || formData.qualifying_score > 100) {
      showNotice("Qualifying examination score must be a number between 0 and 100.", "error");
      document.getElementById("input-qualifying-score")?.focus();
      return;
    }
    if (formData.ssc_score !== null && (isNaN(formData.ssc_score) || formData.ssc_score < 0 || formData.ssc_score > 100)) {
      showNotice("SSC / 10th percentage must be a number between 0 and 100.", "error");
      document.getElementById("input-ssc-score")?.focus();
      return;
    }
  } else {
    // Continuing years (Second, Third, Fourth, Postgraduate)
    if (formData.academic_score === null || isNaN(formData.academic_score) || formData.academic_score < 0 || formData.academic_score > 100) {
      showNotice("Primary academic score must be a number between 0 and 100.", "error");
      const primaryInput = document.getElementById("input-first-year-score")
        || document.getElementById("input-second-year-score")
        || document.getElementById("input-third-year-score")
        || document.getElementById("input-ug-score");
      primaryInput?.focus();
      return;
    }
    if (formData.previous_score !== null && (isNaN(formData.previous_score) || formData.previous_score < 0 || formData.previous_score > 100)) {
      showNotice("Previous academic score must be a number between 0 and 100.", "error");
      return;
    }
    if (formData.attendance === null || isNaN(formData.attendance) || formData.attendance < 0 || formData.attendance > 100) {
      showNotice("Attendance percentage must be a number between 0 and 100.", "error");
      document.getElementById("input-attendance")?.focus();
      return;
    }
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
    const assessmentLabel = formatAIAssessmentLabel(mlPred);
    const isNotEligible = bestMatch.eligibility_status === "NOT_ELIGIBLE";
    const isEligible = bestMatch.eligibility_status === "ELIGIBLE";
    const hasDisagreement = isNotEligible && (mlPred === "APPROVE" || bestMatch.ml_prediction?.decision === "APPROVE");

    const assessmentTitleEl = document.getElementById("best-match-assessment-title");
    if (assessmentTitleEl) {
      assessmentTitleEl.textContent = isNotEligible ? "AI Model Signal" : "AI Assessment";
    }

    const mlPredEl = document.getElementById("best-match-ml-pred");
    if (mlPredEl) {
      mlPredEl.textContent = assessmentLabel;
      mlPredEl.style.color = mlPred === "APPROVE" ? "var(--green-700)" : mlPred === "REJECT" ? "var(--red-700)" : "var(--amber-700)";
    }

    const probStatEl = document.getElementById("best-match-prob-stat");
    const probMeterEl = document.getElementById("best-match-prob-meter");
    const mlConfEl = document.getElementById("best-match-ml-conf");
    const mlConfTextEl = document.getElementById("best-match-ml-conf-text");
    const fillEl = document.getElementById("best-match-confidence-fill");
    const probDisclaimerEl = document.getElementById("best-match-prob-disclaimer");

    if (isNotEligible) {
      // IF deterministic eligibility = NOT_ELIGIBLE:
      // DO NOT display an "Estimated Approval Probability" percentage.
      // Instead display:
      // Estimated Approval Probability: Not applicable
      // Current eligibility rules are not satisfied.
      if (probStatEl) {
        probStatEl.style.display = "block";
        if (mlConfEl) {
          mlConfEl.textContent = "Not applicable";
          mlConfEl.style.color = "var(--ink-500)";
          mlConfEl.style.fontSize = "0.95rem";
        }
      }
      if (probMeterEl) {
        probMeterEl.style.display = "block";
        if (mlConfTextEl) mlConfTextEl.textContent = "Not applicable";
        if (fillEl) fillEl.style.width = "0%";
        if (probDisclaimerEl) {
          probDisclaimerEl.innerHTML = `<span style="color:var(--red-700); font-weight:600;">Current eligibility rules are not satisfied.</span>`;
        }
      }
    } else if (isEligible && mlPred === "APPROVE") {
      // IF deterministic eligibility = ELIGIBLE and AI is APPROVE:
      // Estimated Approval Probability: XX.X%
      if (probStatEl) {
        probStatEl.style.display = "block";
        if (mlConfEl) {
          mlConfEl.textContent = mlConf;
          mlConfEl.style.color = "var(--teal-600)";
          mlConfEl.style.fontSize = "1.15rem";
        }
      }
      if (probMeterEl) {
        probMeterEl.style.display = "block";
        if (mlConfTextEl) mlConfTextEl.textContent = mlConf;
        const fillWidth = getConfidenceWidth(bestMatch.ml_prediction);
        if (fillEl) fillEl.style.width = `${fillWidth}%`;
        if (probDisclaimerEl) {
          probDisclaimerEl.textContent = "Estimated probability of the APPROVE outcome from the AI model. This is an advisory estimate and does not guarantee approval.";
        }
      }
    } else {
      // Eligible with NEEDS_HUMAN_REVIEW or REJECT, or NEEDS_VERIFICATION without APPROVE:
      // No misleading approval probability!
      if (probStatEl) {
        probStatEl.style.display = "block";
        if (mlConfEl) {
          mlConfEl.textContent = "Not applicable";
          mlConfEl.style.color = "var(--ink-500)";
          mlConfEl.style.fontSize = "0.95rem";
        }
      }
      if (probMeterEl) {
        probMeterEl.style.display = "none";
      }
    }

    const advisoryEl = document.getElementById("best-match-advisory-note");
    if (advisoryEl) {
      if (hasDisagreement) {
        advisoryEl.style.display = "block";
        advisoryEl.innerHTML = `<strong>⚠️ AI and eligibility rules differ. Human review is recommended.</strong><br/><span style="margin-top:4px; display:inline-block;">This means the applicant's historical feature pattern resembles cases the model associated with approval; it does NOT override current scholarship eligibility rules.</span>`;
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
    const schIsNotEligible = sch.eligibility_status === "NOT_ELIGIBLE";
    const schIsEligible = sch.eligibility_status === "ELIGIBLE";
    const schPred = sch.ml_prediction?.prediction || sch.ml_prediction?.decision;
    const schHasDisagreement = schIsNotEligible && schPred === "APPROVE";

    let probDisplayHtml = "";
    if (schIsNotEligible) {
      probDisplayHtml = `
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span>Estimated Approval Probability:</span>
          <strong style="color:var(--ink-500);">Not applicable</strong>
        </div>
        <div style="font-size:0.72rem; color:var(--red-700); margin-bottom:6px;">
          Current eligibility rules are not satisfied.
        </div>
      `;
    } else if (schIsEligible && schPred === "APPROVE") {
      probDisplayHtml = `
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span>Estimated Approval Probability:</span>
          <strong style="color:var(--teal-600);">${mlConfPercent}</strong>
        </div>
        <div style="font-size:0.7rem; color:var(--ink-500); margin-bottom:6px;">
          Estimated probability of the APPROVE outcome from the AI model. This is an advisory estimate and does not guarantee approval.
        </div>
      `;
    } else {
      probDisplayHtml = `
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span>Estimated Approval Probability:</span>
          <strong style="color:var(--ink-500);">Not applicable</strong>
        </div>
        <div style="font-size:0.7rem; color:var(--ink-500); margin-bottom:6px;">
          ${schPred === "APPROVE" ? "Subject to document verification." : "Outcome is non-approval; approval probability is not applicable."}
        </div>
      `;
    }

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
              <span>${schIsNotEligible ? "AI Model Signal:" : "AI Assessment:"}</span>
              <strong style="color:${(schPred === 'APPROVE') ? 'var(--green-700)' : (schPred === 'REJECT') ? 'var(--red-700)' : 'var(--amber-700)'};">${escapeHtml(formatAIAssessmentLabel(schPred || "REVIEW"))}</strong>
            </div>
            ${probDisplayHtml}
            ${schHasDisagreement ? `
              <div style="margin-top:6px; font-size:0.74rem; color:var(--amber-900); background:#fffbeb; padding:6px 8px; border-radius:4px; line-height:1.35; border:1px solid #fde68a;">
                <strong>⚠️ AI and eligibility rules differ. Human review is recommended.</strong><br/>
                <span style="display:inline-block; margin-top:2px;">This means the applicant's historical feature pattern resembles cases the model associated with approval; it does NOT override current scholarship eligibility rules.</span>
              </div>
            ` : ""}
            <div style="margin-top:4px; font-size:0.7rem; color:var(--ink-500); line-height:1.3;">
              AI-generated assessment for decision support. It does not constitute the final scholarship decision.
            </div>
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
 * Render the Two-Layer SHAP explainability panel for the evaluated prediction.
 * Layer 1: User-Friendly SHAP Explanation (feature name, actual value, direction, human strength, plain language explanation)
 * Layer 2: Technical Collapsible Section (TreeSHAP contribution value, baseline output, clear definitions)
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
  const baseNum = Number(exp.base_value);
  const baseDisplay = isNaN(baseNum) ? "0.33" : (baseNum >= 0 ? `+${baseNum.toFixed(3)}` : baseNum.toFixed(3));
  if (baseEl) {
    baseEl.textContent = baseDisplay;
  }

  // Update summary intro
  const summaryEl = document.getElementById("shap-summary-text");
  if (summaryEl) {
    summaryEl.textContent = exp.intro || "These factors show which parts of your application influenced the AI's assessment and whether they pushed it toward or away from the predicted outcome.";
  }

  // Split into positive and negative
  const posFeatures = features.filter(f => f.direction === "positive");
  const negFeatures = features.filter(f => f.direction === "negative");
  const neuFeatures = features.filter(f => f.direction === "neutral");

  const renderTwoLayerCard = (feat) => {
    const shapVal = Number(feat.shap_value || 0);
    const signPrefix = shapVal > 0 ? "+" : "";
    const formattedShap = `${signPrefix}${shapVal.toFixed(3)}`;
    const formattedInput = feat.formatted_input || formatFeatureDisplayValue(feat.feature, feat.input_value);

    const isPos = feat.direction === "positive";
    const isNeg = feat.direction === "negative";
    const badgeColor = isPos ? "#065f46" : isNeg ? "#991b1b" : "#475569";
    const badgeBg = isPos ? "#d1fae5" : isNeg ? "#fee2e2" : "#f1f5f9";
    const icon = isPos ? "🟢" : isNeg ? "🔴" : "⚪";

    // Human-readable strength
    const humanStrength = feat.human_strength || (
      isPos ? (Math.abs(shapVal) >= 0.15 ? "Strong positive influence" : Math.abs(shapVal) >= 0.05 ? "Moderate positive influence" : "Small positive influence")
      : isNeg ? (Math.abs(shapVal) >= 0.15 ? "Strong negative influence" : Math.abs(shapVal) >= 0.05 ? "Moderate negative influence" : "Small negative influence")
      : "Minimal or neutral influence"
    );

    // Plain-language explanation
    const plainExp = feat.plain_explanation || (
      isPos ? `Your ${feat.display_name.toLowerCase()} supported the AI's assessment.`
      : isNeg ? `Your ${feat.display_name.toLowerCase()} moved the AI assessment away from Likely Eligible.`
      : `Your ${feat.display_name.toLowerCase()} had minimal influence on this assessment.`
    );

    return `
      <div class="shap-two-layer-card" data-feature="${escapeHtml(feat.feature)}" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px 16px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
        <!-- LAYER 1: USER-FRIENDLY EXPLANATION -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="font-size:0.92rem; font-weight:700; color:var(--navy-900);">${escapeHtml(feat.display_name)}</div>
            <div style="font-size:0.8rem; color:var(--ink-500); margin-top:2px;">
              Your value: <strong style="color:var(--navy-800);">${escapeHtml(formattedInput)}</strong>
            </div>
          </div>
          <div style="display:inline-flex; align-items:center; gap:5px; font-size:0.76rem; font-weight:700; color:${badgeColor}; background:${badgeBg}; padding:3px 10px; border-radius:999px;">
            <span>${icon}</span>
            <span>${escapeHtml(humanStrength)}</span>
          </div>
        </div>

        <div style="margin-top:8px; font-size:0.84rem; color:var(--ink-700); line-height:1.45; font-style:italic;">
          "${escapeHtml(plainExp)}"
        </div>

        <!-- LAYER 2: TECHNICAL SHAP DETAILS (COLLAPSIBLE) -->
        <details class="shap-tech-details" style="margin-top:10px; border-top:1px dashed #e2e8f0; padding-top:6px;">
          <summary style="font-size:0.76rem; font-weight:700; color:var(--teal-700); cursor:pointer; user-select:none; padding:2px 0;">
            Technical explanation
          </summary>
          <div style="margin-top:6px; padding:10px 12px; background:#f8fafc; border-radius:6px; font-size:0.77rem; line-height:1.45; color:var(--ink-700);">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
              <div>
                <span style="color:var(--ink-500);">SHAP contribution:</span>
                <strong style="color:${badgeColor}; font-family:monospace; margin-left:4px;">${formattedShap}</strong>
              </div>
              <div>
                <span style="color:var(--ink-500);">Baseline model output:</span>
                <strong style="color:var(--navy-900); font-family:monospace; margin-left:4px;">${baseDisplay}</strong>
              </div>
            </div>
            <div style="margin-bottom:4px;">
              <strong>SHAP contribution</strong> shows how this feature moved the model output relative to the model's baseline for this prediction.
            </div>
            <div>
              <strong>Baseline</strong> represents the model's expected output before considering this applicant's individual feature values.
            </div>
          </div>
        </details>
      </div>
    `;
  };

  const posList = document.getElementById("shap-positive-factors-list");
  if (posList) {
    if (posFeatures.length > 0) {
      posList.innerHTML = posFeatures.map(renderTwoLayerCard).join("");
    } else {
      posList.innerHTML = `<div style="font-size:0.78rem; color:var(--ink-500); padding:4px 0;">No strong positive influences detected for this prediction.</div>`;
    }
  }

  const negList = document.getElementById("shap-negative-factors-list");
  if (negList) {
    const combinedNeg = [...negFeatures, ...neuFeatures];
    if (combinedNeg.length > 0) {
      negList.innerHTML = combinedNeg.map(renderTwoLayerCard).join("");
    } else {
      negList.innerHTML = `<div style="font-size:0.78rem; color:var(--ink-500); padding:4px 0;">No negative influences detected for this prediction.</div>`;
    }
  }

  const inspector = document.getElementById("shap-feature-inspector");
  if (inspector) {
    inspector.style.display = "none";
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
