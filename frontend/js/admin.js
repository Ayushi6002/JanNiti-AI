/* admin.js
   Jan Niti AI — Evaluator Dashboard Workflow Restructure
   --------------------------------------------------------
   Authoritative Human Decision vs Advisory AI Prediction:
   - AI/ML produces advisory predictions and confidence.
   - AI NEVER makes the final decision.
   - Final decisions are strictly made by Admin/Evaluator.
   - Priority Order for Categorization:
     1. ACTIVE APPEAL -> Appeal Pending
     2. FINAL HUMAN DECISION -> Decision Made by Admin (Approved / Rejected)
     3. PENDING ML CATEGORIZATION -> Pending Decisions (Likely Approved / Likely Rejected / Requires Review)
*/

const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");

const tbody = document.getElementById("applications-tbody");
const topNavContainer = document.getElementById("top-nav-tabs");
const subNavContainer = document.getElementById("sub-nav-tabs");
const nestedSubNavContainer = document.getElementById("nested-sub-tabs");

// Summary counters
const summaryDecidedTotal = document.getElementById("summary-decided-total");
const summaryApprovedCount = document.getElementById("summary-approved-count");
const summaryRejectedCount = document.getElementById("summary-rejected-count");
const summaryPendingTotal = document.getElementById("summary-pending-total");
const summaryLikelyApprovedCount = document.getElementById("summary-likely-approved-count");
const summaryLikelyRejectedCount = document.getElementById("summary-likely-rejected-count");
const summaryRequiresReviewCount = document.getElementById("summary-requires-review-count");
const summaryAppealsTotal = document.getElementById("summary-appeals-total");
const summaryTotal = document.getElementById("summary-total");

const countTopDecided = document.getElementById("count-top-decided");
const countTopPending = document.getElementById("count-top-pending");
const countTopAppeals = document.getElementById("count-top-appeals");

const drawer = document.getElementById("drawer");
const drawerBackdrop = document.getElementById("drawer-backdrop");
const drawerBody = document.getElementById("drawer-body");
const drawerClose = document.getElementById("drawer-close");

// Navigation State
let currentTopTab = "DECISION_MADE";     // "DECISION_MADE" | "PENDING_DECISIONS" | "APPEAL_PENDING"
let currentSubTab = "APPROVED";          // "APPROVED" | "REJECTED" | "LIKELY_APPROVED" | "LIKELY_REJECTED" | "REQUIRES_REVIEW" | "ALL"
let currentReviewFilter = "ALL";         // "ALL" | "MODEL_REVIEW" | "ML_PENDING"
let applicationsCache = [];

// ---- Auth ----
function checkLoginState() {
  const token = sessionStorage.getItem("janniti_auth_token");
  const role = sessionStorage.getItem("janniti_user_role");
  if (token && role === "admin") {
    showDashboard();
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const u = document.getElementById("username").value.trim();
  const p = document.getElementById("password").value;

  try {
    const auth = await supabaseLogin(u, p);

    const { data: profile, error: profileError } = await supabaseClient
      .from("profiles")
      .select("id, full_name, phone, role")
      .eq("id", auth.user.id)
      .single();

    if (profileError || !profile) {
      await supabaseLogout();
      throw new Error("Your Supabase account does not have a profile record.");
    }

    if (profile.role !== "admin") {
      await supabaseLogout();
      throw new Error("This account does not have admin permissions.");
    }

    persistSupabaseAuth(auth.session, auth.user, profile);
    showDashboard();

  } catch (err) {
    loginError.innerHTML = `<div class="notice notice-error">${err.message}</div>`;
  }
});

logoutBtn.addEventListener("click", async () => {
  const token = sessionStorage.getItem("janniti_auth_token");
  try {
    if (token) await apiPost("/auth/logout", {}, false, token);
  } catch (err) {
    console.warn(err.message);
  }
  try {
    if (typeof supabaseLogout === "function") {
      await supabaseLogout();
    }
  } catch (err) {
    console.warn(err.message);
  }
  if (typeof clearSupabaseAuthStorage === "function") {
    clearSupabaseAuthStorage();
  } else {
    sessionStorage.removeItem("janniti_auth_token");
    sessionStorage.removeItem("janniti_user_role");
    sessionStorage.removeItem("janniti_student_email");
  }
  dashboardView.classList.add("hidden");
  loginView.classList.remove("hidden");
});

function showDashboard() {
  loginView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  loadApplications();
}

// ---- Normalization & Classification ----

/**
 * Normalizes confidence score once to a clean integer percentage (0-100).
 * Prevents double multiplication bugs (e.g. 9600%).
 * Returns null if no ML prediction exists (ML Processing Pending).
 */
function getNormalizedConfidence(app) {
  // If no prediction record exists, confidence is not applicable (ML Processing Pending)
  const rawPred = app.model_decision || (app.ai_prediction && app.ai_prediction.prediction) || app.prediction || "";
  const hasPred = !!(app.ai_prediction || (rawPred && rawPred !== "NONE" && rawPred !== ""));
  if (!hasPred) return null;

  let raw = null;
  if (typeof app.confidence === "number") {
    raw = app.confidence;
  } else if (app.ai_prediction && typeof app.ai_prediction.probability === "number") {
    raw = app.ai_prediction.probability;
  }
  if (raw === null || raw === undefined || isNaN(raw)) return null;
  if (raw <= 1.0) {
    return Math.round(raw * 100);
  }
  return Math.round(raw);
}

function formatConfidence(app) {
  const conf = getNormalizedConfidence(app);
  if (conf === null) {
    return "Not Available — ML Processing Pending";
  }
  return `${conf}%`;
}

/**
 * Strict Order of Priority Categorization:
 * 1. ACTIVE APPEAL -> APPEAL_PENDING
 * 2. FINAL HUMAN DECISION -> DECISION_MADE (APPROVED / REJECTED)
 * 3. PENDING ML CATEGORIZATION -> PENDING_DECISIONS:
 *    - Likely to Get Approved (APPROVE >= 70%)
 *    - Likely to Get Rejected (REJECT >= 70%)
 *    - Requires Human Review:
 *        - Model Review Required (APPROVE/REJECT < 70% or NEEDS_HUMAN_REVIEW)
 *        - ML Processing Pending (No ML prediction exists)
 */
function classifyApplication(app) {
  // 1. ACTIVE APPEAL (Priority 1)
  const statusUpper = (app.status || "").toUpperCase();
  const appealStatusUpper = (app.appeal && app.appeal.status ? app.appeal.status : "").toUpperCase();
  const hasActiveAppeal = statusUpper === "APPEAL_PENDING" || appealStatusUpper === "PENDING";

  if (hasActiveAppeal) {
    const origDec = (app.admin_final_decision || app.final_decision || (app.decision && app.decision.decision) || "REJECTED").toUpperCase();
    return {
      top: "APPEAL_PENDING",
      sub: "APPEAL_PENDING",
      parentSub: "APPEAL_PENDING",
      reviewSub: null,
      label: "Appeal Pending",
      originalDecision: origDec,
      isAppeal: true,
      confidence: getNormalizedConfidence(app),
    };
  }

  // 2. FINAL HUMAN DECISION (Priority 2)
  const humanDec = (app.admin_final_decision || app.final_decision || (app.decision && app.decision.decision) || "").toUpperCase();
  if (humanDec === "APPROVED" || humanDec === "APPROVE") {
    return {
      top: "DECISION_MADE",
      sub: "APPROVED",
      parentSub: "APPROVED",
      reviewSub: null,
      label: "Approved by Admin / Evaluator",
      humanDecision: "APPROVED",
      confidence: getNormalizedConfidence(app),
    };
  }
  if (humanDec === "REJECTED" || humanDec === "REJECT") {
    return {
      top: "DECISION_MADE",
      sub: "REJECTED",
      parentSub: "REJECTED",
      reviewSub: null,
      label: "Rejected by Admin / Evaluator",
      humanDecision: "REJECTED",
      confidence: getNormalizedConfidence(app),
    };
  }

  // 3. PENDING ML CATEGORIZATION (Priority 3) - Advisory ONLY
  const rawPred = app.model_decision || (app.ai_prediction && app.ai_prediction.prediction) || app.prediction || "";
  const pred = rawPred ? rawPred.toUpperCase() : "";
  const hasPredictionRecord = !!(app.ai_prediction || (app.model_decision && app.model_decision !== "NONE" && app.model_decision !== ""));
  const conf = getNormalizedConfidence(app);

  // Business Rules:
  // - No ML prediction exists -> ML PROCESSING PENDING (under Requires Human Review)
  if (!hasPredictionRecord || !pred) {
    return {
      top: "PENDING_DECISIONS",
      sub: "ML_PROCESSING_PENDING",
      parentSub: "REQUIRES_REVIEW",
      reviewSub: "ML_PROCESSING_PENDING",
      label: "ML Processing Pending",
      confidence: null,
      isMLPending: true,
    };
  }

  // - High-confidence threshold is >= 70%
  // - APPROVE and conf >= 70% -> Likely to Get Approved
  if (pred === "APPROVE" && conf !== null && conf >= 70) {
    return {
      top: "PENDING_DECISIONS",
      sub: "LIKELY_APPROVED",
      parentSub: "LIKELY_APPROVED",
      reviewSub: null,
      label: "Likely to Get Approved",
      confidence: conf,
    };
  }

  // - REJECT and conf >= 70% -> Likely to Get Rejected
  if (pred === "REJECT" && conf !== null && conf >= 70) {
    return {
      top: "PENDING_DECISIONS",
      sub: "LIKELY_REJECTED",
      parentSub: "LIKELY_REJECTED",
      reviewSub: null,
      label: "Likely to Get Rejected",
      confidence: conf,
    };
  }

  // - Valid prediction exists with conf < 70% OR pred === NEEDS_HUMAN_REVIEW -> Model Review Required
  return {
    top: "PENDING_DECISIONS",
    sub: "REQUIRES_REVIEW",
    parentSub: "REQUIRES_REVIEW",
    reviewSub: "MODEL_REVIEW_REQUIRED",
    label: "Requires Human Review (Model Review Required)",
    confidence: conf,
    isModelReview: true,
  };
}

function getRiskPillClass(risk) {
  const r = (risk || "LOW").toUpperCase();
  if (r === "HIGH") return "pill-risk-high";
  if (r === "MEDIUM" || r === "MED") return "pill-risk-medium";
  return "pill-risk-low";
}

// ---- Applications Loader ----
async function loadApplications() {
  tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--ink-500);">Loading applications…</td></tr>`;
  try {
    const token = sessionStorage.getItem("janniti_auth_token");
    const data = await apiGet(`/admin/applications`, token);
    applicationsCache = data.applications || [];
    updateDashboardCountsAndNavigation();
    renderFilteredTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="notice notice-error">Could not load applications: ${err.message}. Make sure the backend server is running at ${API_BASE}.</div></td></tr>`;
  }
}

// ---- Dynamic Counting & Sub-Nav Rendering ----
function updateDashboardCountsAndNavigation() {
  let approvedCount = 0;
  let rejectedCount = 0;
  let likelyApprovedCount = 0;
  let likelyRejectedCount = 0;
  let modelReviewCount = 0;
  let mlPendingCount = 0;
  let appealsCount = 0;

  applicationsCache.forEach(app => {
    const c = classifyApplication(app);
    if (c.top === "DECISION_MADE") {
      if (c.sub === "APPROVED") approvedCount++;
      if (c.sub === "REJECTED") rejectedCount++;
    } else if (c.top === "PENDING_DECISIONS") {
      if (c.sub === "LIKELY_APPROVED") likelyApprovedCount++;
      else if (c.sub === "LIKELY_REJECTED") likelyRejectedCount++;
      else if (c.sub === "ML_PROCESSING_PENDING") mlPendingCount++;
      else modelReviewCount++;
    } else if (c.top === "APPEAL_PENDING") {
      appealsCount++;
    }
  });

  const requiresReviewCount = modelReviewCount + mlPendingCount;
  const decidedTotal = approvedCount + rejectedCount;
  const pendingTotal = likelyApprovedCount + likelyRejectedCount + requiresReviewCount;
  const totalApps = applicationsCache.length;

  // Update Summary Strip
  if (summaryDecidedTotal) summaryDecidedTotal.textContent = decidedTotal;
  if (summaryApprovedCount) summaryApprovedCount.textContent = approvedCount;
  if (summaryRejectedCount) summaryRejectedCount.textContent = rejectedCount;

  if (summaryPendingTotal) summaryPendingTotal.textContent = pendingTotal;
  if (summaryLikelyApprovedCount) summaryLikelyApprovedCount.textContent = likelyApprovedCount;
  if (summaryLikelyRejectedCount) summaryLikelyRejectedCount.textContent = likelyRejectedCount;
  if (summaryRequiresReviewCount) summaryRequiresReviewCount.textContent = requiresReviewCount;

  if (summaryAppealsTotal) summaryAppealsTotal.textContent = appealsCount;
  if (summaryTotal) summaryTotal.textContent = totalApps;

  // Update Top Nav Tab Badges
  if (countTopDecided) countTopDecided.textContent = decidedTotal;
  if (countTopPending) countTopPending.textContent = pendingTotal;
  if (countTopAppeals) countTopAppeals.textContent = appealsCount;

  renderSubNavTabs({
    decidedTotal, approvedCount, rejectedCount,
    pendingTotal, likelyApprovedCount, likelyRejectedCount,
    requiresReviewCount, modelReviewCount, mlPendingCount,
    appealsCount
  });
}

function renderSubNavTabs(counts) {
  if (!subNavContainer) return;

  if (currentTopTab === "DECISION_MADE") {
    if (nestedSubNavContainer) nestedSubNavContainer.classList.add("hidden");
    if (currentSubTab !== "APPROVED" && currentSubTab !== "REJECTED") {
      currentSubTab = "APPROVED";
    }
    subNavContainer.innerHTML = `
      <button class="sub-nav-btn ${currentSubTab === 'APPROVED' ? 'active' : ''}" data-sub="APPROVED">
        Approved by Admin / Evaluator <span class="sub-count">${counts.approvedCount}</span>
      </button>
      <button class="sub-nav-btn ${currentSubTab === 'REJECTED' ? 'active' : ''}" data-sub="REJECTED">
        Rejected by Admin / Evaluator <span class="sub-count">${counts.rejectedCount}</span>
      </button>
    `;
  } else if (currentTopTab === "PENDING_DECISIONS") {
    if (!["LIKELY_APPROVED", "LIKELY_REJECTED", "REQUIRES_REVIEW"].includes(currentSubTab)) {
      currentSubTab = "LIKELY_APPROVED";
    }
    subNavContainer.innerHTML = `
      <button class="sub-nav-btn ${currentSubTab === 'LIKELY_APPROVED' ? 'active' : ''}" data-sub="LIKELY_APPROVED">
        Likely to Get Approved <span class="sub-count">${counts.likelyApprovedCount}</span>
      </button>
      <button class="sub-nav-btn ${currentSubTab === 'LIKELY_REJECTED' ? 'active' : ''}" data-sub="LIKELY_REJECTED">
        Likely to Get Rejected <span class="sub-count">${counts.likelyRejectedCount}</span>
      </button>
      <button class="sub-nav-btn ${currentSubTab === 'REQUIRES_REVIEW' ? 'active' : ''}" data-sub="REQUIRES_REVIEW">
        Requires Human Review <span class="sub-count">${counts.requiresReviewCount}</span>
      </button>
    `;

    // Render nested sub-tabs when on Requires Human Review
    if (nestedSubNavContainer) {
      if (currentSubTab === "REQUIRES_REVIEW") {
        nestedSubNavContainer.classList.remove("hidden");
        nestedSubNavContainer.innerHTML = `
          <span style="font-size:0.76rem; font-weight:700; color:var(--ink-500); text-transform:uppercase; letter-spacing:0.04em; margin-right:4px;">Review Category:</span>
          <button class="nested-pill-btn ${currentReviewFilter === 'ALL' ? 'active' : ''}" data-filter="ALL">
            All Human Review <span class="sub-count">${counts.requiresReviewCount}</span>
          </button>
          <button class="nested-pill-btn ${currentReviewFilter === 'MODEL_REVIEW' ? 'active' : ''}" data-filter="MODEL_REVIEW">
            Model Review Required <span class="sub-count">${counts.modelReviewCount}</span>
          </button>
          <button class="nested-pill-btn ${currentReviewFilter === 'ML_PENDING' ? 'active' : ''}" data-filter="ML_PENDING">
            ML Processing Pending <span class="sub-count">${counts.mlPendingCount}</span>
          </button>
        `;

        nestedSubNavContainer.querySelectorAll(".nested-pill-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            currentReviewFilter = btn.dataset.filter;
            nestedSubNavContainer.querySelectorAll(".nested-pill-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            renderFilteredTable();
          });
        });
      } else {
        nestedSubNavContainer.classList.add("hidden");
      }
    }
  } else if (currentTopTab === "APPEAL_PENDING") {
    if (nestedSubNavContainer) nestedSubNavContainer.classList.add("hidden");
    currentSubTab = "ALL";
    subNavContainer.innerHTML = `
      <button class="sub-nav-btn active" data-sub="ALL">
        All Active Appeals <span class="sub-count">${counts.appealsCount}</span>
      </button>
      <span style="font-size:0.8rem; color:var(--ink-500); margin-left:auto;">
        Original human decisions preserved. Evaluator re-evaluation required.
      </span>
    `;
  }

  // Attach click listeners to sub-nav buttons
  subNavContainer.querySelectorAll(".sub-nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentSubTab = btn.dataset.sub;
      subNavContainer.querySelectorAll(".sub-nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      updateDashboardCountsAndNavigation();
      renderFilteredTable();
    });
  });
}

// Wire up Top-Nav tab switches
if (topNavContainer) {
  topNavContainer.querySelectorAll(".top-nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      topNavContainer.querySelectorAll(".top-nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTopTab = btn.dataset.top;
      if (currentTopTab === "DECISION_MADE") {
        currentSubTab = "APPROVED";
      } else if (currentTopTab === "PENDING_DECISIONS") {
        currentSubTab = "LIKELY_APPROVED";
      } else {
        currentSubTab = "ALL";
      }
      updateDashboardCountsAndNavigation();
      renderFilteredTable();
    });
  });
}

// ---- Table Rendering ----
function renderFilteredTable() {
  const filtered = applicationsCache.filter(app => {
    const c = classifyApplication(app);
    if (c.top !== currentTopTab) return false;

    if (currentTopTab === "PENDING_DECISIONS") {
      if (currentSubTab === "LIKELY_APPROVED") {
        return c.sub === "LIKELY_APPROVED";
      }
      if (currentSubTab === "LIKELY_REJECTED") {
        return c.sub === "LIKELY_REJECTED";
      }
      if (currentSubTab === "REQUIRES_REVIEW") {
        if (currentReviewFilter === "MODEL_REVIEW") {
          return c.reviewSub === "MODEL_REVIEW_REQUIRED";
        }
        if (currentReviewFilter === "ML_PENDING") {
          return c.reviewSub === "ML_PROCESSING_PENDING";
        }
        return c.parentSub === "REQUIRES_REVIEW"; // ALL
      }
    }

    if (currentSubTab === "ALL") return true;
    return c.sub === currentSubTab;
  });

  renderTable(filtered);
}

function renderTable(apps) {
  if (apps.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:36px; color:var(--ink-500);">No applications found in this section.</td></tr>`;
    return;
  }

  tbody.innerHTML = apps.map((app) => {
    const c = classifyApplication(app);
    const applicantData = app.applicant_data || {
      scholarship_scheme: (app.scholarship_schemes && app.scholarship_schemes.scheme_name) || "General Scholarship",
    };
    const risk = app.risk_level || (app.anomaly_assessment && app.anomaly_assessment.risk_level) || "LOW";
    const pred = (app.model_decision || (app.ai_prediction && app.ai_prediction.prediction) || app.prediction || "NEEDS_HUMAN_REVIEW").toUpperCase();
    
    // AI Prediction badge (Advisory Only)
    let aiPredBadge = "";
    if (c.isMLPending) {
      aiPredBadge = `<span class="pill pill-ml-pending">ML PROCESSING PENDING</span>`;
    } else if (pred === "APPROVE") {
      aiPredBadge = `<span class="pill pill-approve">AI: APPROVE</span>`;
    } else if (pred === "REJECT") {
      aiPredBadge = `<span class="pill pill-reject">AI: REJECT</span>`;
    } else {
      aiPredBadge = `<span class="pill pill-review">AI: NEEDS REVIEW</span>`;
    }

    // Confidence display
    let confDisplay = "";
    if (c.isMLPending) {
      confDisplay = `<span style="font-size:0.78rem; color:var(--ink-500); font-weight:600;">Not Available — ML Pending</span>`;
    } else {
      confDisplay = `<strong style="color:var(--navy-900);">${formatConfidence(app)}</strong>`;
    }

    // Authoritative Final Status badge
    let statusBadge = "";
    if (c.top === "DECISION_MADE") {
      if (c.sub === "APPROVED") {
        statusBadge = `<span class="pill pill-approve">APPROVED</span>`;
      } else {
        statusBadge = `<span class="pill pill-reject">REJECTED</span>`;
      }
    } else if (c.top === "PENDING_DECISIONS") {
      statusBadge = `<span class="pill pill-review">PENDING HUMAN DECISION</span>`;
    } else if (c.top === "APPEAL_PENDING") {
      statusBadge = `
        <div>
          <span class="pill pill-review">APPEAL PENDING</span>
          <div style="font-size:0.72rem; color:var(--ink-500); margin-top:2px;">Orig: <strong>${c.originalDecision || "REJECTED"}</strong></div>
        </div>
      `;
    }

    return `
    <tr data-id="${app.id}">
      <td><span class="app-id-box" style="margin:0;">${app.id.slice(0, 8)}…</span></td>
      <td><strong>${applicantData.scholarship_scheme}</strong></td>
      <td>${aiPredBadge}</td>
      <td><span class="pill ${getRiskPillClass(risk)}">${risk}</span></td>
      <td>${confDisplay}</td>
      <td>${statusBadge}</td>
      <td>${formatDateTime(app.created_at)}</td>
    </tr>`;
  }).join("");

  document.querySelectorAll("#applications-tbody tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => openDrawer(row.dataset.id));
  });
}

// ---- Application Detail Drawer ----
async function openDrawer(appId) {
  const app = applicationsCache.find((a) => a.id === appId) || { id: appId };
  const token = sessionStorage.getItem("janniti_auth_token");

  drawer.classList.add("open");
  drawerBackdrop.classList.add("open");
  drawerBody.innerHTML = `
    <div style="text-align:center; padding:48px;">
      <span class="spinner"></span>
      <p style="margin-top:14px; color:var(--ink-500); font-size:0.95rem;">Loading application, documents & anomaly assessment…</p>
    </div>
  `;

  let fullDetails = null;
  let anomaly = null;

  try {
    const [detailsRes, anomalyRes] = await Promise.allSettled([
      apiGet(`/admin/applications/${appId}`, token),
      apiGet(`/admin/applications/${appId}/anomalies`, token),
    ]);

    if (detailsRes.status === "fulfilled") {
      fullDetails = detailsRes.value;
    }
    if (anomalyRes.status === "fulfilled") {
      anomaly = anomalyRes.value;
    }
  } catch (err) {
    console.warn("Error fetching application drawer data:", err);
  }

  const appData = (fullDetails && fullDetails.application) || app;
  const c = classifyApplication(appData);

  const d = app.applicant_data || {
    scholarship_scheme: (appData.scholarship_schemes && appData.scholarship_schemes.scheme_name) || "—",
    application_category: appData.application_category || "—",
    academic_score: appData.academic_score || "—",
    previous_score: appData.previous_score || "—",
    attendance: appData.attendance || "—",
    annual_income: appData.annual_income || 0,
    documents_verified: (fullDetails && fullDetails.verification_summary && fullDetails.verification_summary.overall_status) || "—",
  };

  const explanation = app.explanation || (fullDetails && fullDetails.ai_prediction && fullDetails.ai_prediction.explanation) || {
    simple_explanation: "The system evaluated document verification rules and scholarship criteria to generate this advisory assessment.",
    why_approved: [],
    why_rejected: [],
    readable_reasons: [],
  };

  const topReasons = app.top_reasons || (fullDetails && fullDetails.ai_prediction && fullDetails.ai_prediction.top_reasons) || [];
  const reasonsHtml = topReasons.length ? topReasons.map(r => `
    <li>
      <span class="reason-arrow ${r.direction === "increased" ? "up" : "down"}">${r.direction === "increased" ? "▲" : "▼"}</span>
      <span><strong>${(r.feature || "").replace(/_/g, " ")}</strong> ${r.direction || "affected"} the likelihood (impact ${r.impact > 0 ? "+" : ""}${r.impact || "0"})</span>
    </li>`).join("") : `<li><span>No specific SHAP factors calculated.</span></li>`;

  const positiveHtml = (explanation.why_approved || []).length
    ? (explanation.why_approved || []).map(item => `<li><span class="reason-arrow up">▲</span><span>${item}</span></li>`).join("")
    : `<li><span class="reason-arrow up">▲</span><span>No strong positive factors detected.</span></li>`;

  const negativeHtml = (explanation.why_rejected || []).length
    ? (explanation.why_rejected || []).map(item => `<li><span class="reason-arrow down">▼</span><span>${item}</span></li>`).join("")
    : `<li><span class="reason-arrow down">▼</span><span>No strong negative factors detected.</span></li>`;

  // Final human decision determination
  const humanDecision = (appData.admin_final_decision || appData.final_decision || (appData.decision && appData.decision.decision) || "").toUpperCase();
  const alreadyDecided = humanDecision === "APPROVED" || humanDecision === "REJECTED";
  const recordedReason = appData.admin_comment || appData.decision_reason || (appData.decision && (appData.decision.reason || appData.decision.admin_comment)) || "";

  // Appeal details
  const appealObj = appData.appeal || (fullDetails && fullDetails.appeals && fullDetails.appeals[0]) || null;
  const isAppealPending = (appData.status || "").toUpperCase() === "APPEAL_PENDING" || (appealObj && (appealObj.status || "").toUpperCase() === "PENDING");

  // Feature 3: Construct Anomaly section
  let anomalySectionHtml = "";
  if (anomaly) {
    const risk = (anomaly.risk_level || "LOW").toUpperCase();
    const score = Math.round(Number(anomaly.anomaly_score) || 0);
    const status = anomaly.status || "CLEAN";
    const action = anomaly.recommended_action || (status === "ANOMALY_DETECTED" ? "NEEDS_HUMAN_REVIEW" : "PROCEED");
    const humanReviewRequired = anomaly.human_review_required !== false && status === "ANOMALY_DETECTED";
    const reasons = anomaly.reasons || [];
    const persistedCount = anomaly.persisted_records_count || (anomaly.persisted_records && anomaly.persisted_records.length) || reasons.length;

    const fieldInconsistencies = reasons.filter(r => r.category === "FIELD_INCONSISTENCY" || (r.type && r.type.includes("MISMATCH")));
    const crossDocInconsistencies = reasons.filter(r => r.category === "CROSS_DOCUMENT_INCONSISTENCY");
    const duplicates = reasons.filter(r => r.category === "DUPLICATE_DOCUMENT" || (r.type && r.type.includes("DUPLICATE")));
    const temporal = reasons.filter(r => r.category === "TEMPORAL_ANOMALY" || (r.type && (r.type.includes("EXPIRED") || r.type.includes("FUTURE"))));
    const completeness = reasons.filter(r => r.category === "DOCUMENT_COMPLETENESS" || (r.type && r.type.includes("MISSING")));

    const anomalyCardsHtml = reasons.length ? reasons.map((r) => {
      const sev = (r.severity || "MEDIUM").toUpperCase();
      const sevClass = sev === "HIGH" ? "sev-high" : sev === "LOW" ? "sev-low" : "sev-medium";
      const detailsJson = r.details ? (typeof r.details === "object" ? JSON.stringify(r.details, null, 2) : String(r.details)) : null;

      return `
        <div class="anomaly-card-item ${sevClass}">
          <div class="anomaly-item-header">
            <span class="anomaly-type-title">${(r.type || "ANOMALY_DETECTED").replace(/_/g, " ")}</span>
            <span class="pill ${getRiskPillClass(sev)}">${sev}</span>
          </div>
          ${r.document_type ? `<div class="anomaly-item-doc">Document: <strong>${r.document_type}</strong> ${r.file_name ? `(${r.file_name})` : ""}</div>` : ""}
          <p class="anomaly-item-msg">${r.message || "Potential discrepancy detected."}</p>
          ${detailsJson ? `<pre class="anomaly-item-details">${detailsJson}</pre>` : ""}
        </div>
      `;
    }).join("") : `<div class="notice notice-info">✅ All documents are fully consistent and verified. No anomaly issues detected.</div>`;

    anomalySectionHtml = `
      <div class="anomaly-panel" style="margin-top:20px; text-align:left;">
        <div class="anomaly-panel-header">
          <h3 class="anomaly-panel-title">🛡️ Document Fraud & Anomaly Detection</h3>
          <span class="pill ${getRiskPillClass(risk)}">${risk} RISK (${score}/100)</span>
        </div>
        <div class="anomaly-panel-body">
          <div class="risk-meter">
            <div class="risk-meter-label">
              <span>Overall Anomaly Risk Score</span>
              <span>${score} / 100 (${risk})</span>
            </div>
            <div class="risk-meter-track">
              <div class="risk-meter-fill ${risk.toLowerCase()}" style="width:${Math.max(5, Math.min(100, score))}%;"></div>
            </div>
          </div>

          <div class="detail-row"><span class="k">Anomaly Status</span><span class="v"><span class="pill ${status === "CLEAN" ? "pill-approve" : "pill-reject"}">${status.replace(/_/g, " ")}</span></span></div>
          <div class="detail-row"><span class="k">Recommended Action</span><span class="v"><strong>${action.replace(/_/g, " ")}</strong></span></div>
          <div class="detail-row"><span class="k">Evaluator Review</span><span class="v">${humanReviewRequired ? "🚨 Required (Discrepancy Routed for Review)" : "Optional / Automatic Check Clear"}</span></div>
          <div class="detail-row"><span class="k">Persistence Layer</span><span class="v">Production Supabase & Audit Logs (${persistedCount} records)</span></div>

          ${humanReviewRequired ? `
            <div class="notice notice-warn" style="margin-top:12px;">
              🚨 <strong>HUMAN REVIEW REQUIREMENT:</strong> The system detected document discrepancies. Final decision authority rests solely with the human evaluator. AI never automatically rejects an applicant.
            </div>
          ` : `
            <div class="notice notice-info" style="margin-top:12px;">
              ✅ <strong>Automated Verification Passed:</strong> Document contents match application fields.
            </div>
          `}

          <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;">
            <span class="user-pill" style="font-size:0.75rem;">Field Mismatches: ${fieldInconsistencies.length}</span>
            <span class="user-pill" style="font-size:0.75rem;">Cross-Doc Inconsistencies: ${crossDocInconsistencies.length}</span>
            <span class="user-pill" style="font-size:0.75rem;">Duplicates / Reused: ${duplicates.length}</span>
            <span class="user-pill" style="font-size:0.75rem;">Temporal / Date Issues: ${temporal.length}</span>
            <span class="user-pill" style="font-size:0.75rem;">Missing / Incomplete: ${completeness.length}</span>
          </div>

          <h4 style="margin:16px 0 8px;">Detected Document Anomalies (${reasons.length})</h4>
          <div class="anomaly-cards-grid">
            ${anomalyCardsHtml}
          </div>
        </div>
      </div>
    `;
  }

  // Appeal details section
  let appealSectionHtml = "";
  if (appealObj) {
    const appealStatus = (appealObj.status || "PENDING").toUpperCase();
    appealSectionHtml = `
      <div class="notice notice-warn" style="margin-top:20px; border-left: 4px solid var(--amber-600);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h4 style="margin:0; color:var(--amber-800);">🔄 Student Appeal Information</h4>
          <span class="pill pill-review">${appealStatus}</span>
        </div>
        <div style="margin-top:10px;">
          <div class="detail-row"><span class="k">Original Decision</span><span class="v"><strong>${c.originalDecision || humanDecision || "REJECTED"}</strong></span></div>
          <div class="detail-row"><span class="k">Appeal Reason</span><span class="v">${appealObj.reason || "—"}</span></div>
          <div class="detail-row"><span class="k">Appeal Submitted</span><span class="v">${formatDateTime(appealObj.created_at)}</span></div>
          ${appealObj.review_comment ? `<div class="detail-row"><span class="k">Review Comment</span><span class="v">${appealObj.review_comment}</span></div>` : ""}
        </div>
      </div>
    `;
  }

  // Documents Section with View / Download and Download All
  const docsList = (fullDetails && fullDetails.documents) || [];
  let documentsSectionHtml = "";
  if (docsList.length > 0) {
    documentsSectionHtml = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:24px; margin-bottom:10px;">
        <h4 style="margin:0;">Submitted Documents & Verification (${docsList.length})</h4>
        ${docsList.length > 1 ? `
          <button class="btn btn-secondary" id="download-all-docs-btn" style="padding:4px 10px; font-size:0.75rem;">
            ⬇️ Download All Documents
          </button>
        ` : ""}
      </div>
      <div style="display:grid; gap:10px;">
        ${docsList.map(doc => {
          const typeLabel = (doc.document_type || "DOCUMENT").replace(/_/g, " ").toUpperCase();
          const docStatus = doc.verification_status || "PENDING";
          const pillClass = docStatus === "VERIFIED" ? "pill-approve" : (docStatus === "MISMATCH" ? "pill-reject" : "pill-review");
          const viewUrl = `${API_BASE}/admin/applications/${app.id}/documents/${doc.id}/view?token=${encodeURIComponent(token)}`;
          const downloadUrl = `${API_BASE}/admin/applications/${app.id}/documents/${doc.id}/download?token=${encodeURIComponent(token)}`;

          let extractedHtml = "";
          if (doc.extracted_data && typeof doc.extracted_data === "object" && Object.keys(doc.extracted_data).length > 0) {
            extractedHtml = `<div style="margin-top:6px; font-size:0.78rem; color:var(--ink-500); background:rgba(0,0,0,0.02); padding:6px 8px; border-radius:4px;"><strong>Extracted:</strong> ${Object.entries(doc.extracted_data).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ")}</div>`;
          }
          let mismatchHtml = "";
          if (doc.mismatch_details && typeof doc.mismatch_details === "object" && Object.keys(doc.mismatch_details).length > 0) {
            mismatchHtml = `<div style="margin-top:4px; font-size:0.78rem; color:var(--red-700);">⚠️ <strong>Mismatch:</strong> ${Object.entries(doc.mismatch_details).map(([k, v]) => `${k}: ${v}`).join(", ")}</div>`;
          }

          return `
            <div style="padding:12px; background:rgba(255,255,255,0.9); border:1px solid var(--hairline); border-radius:8px; font-size:0.85rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                  <strong>${typeLabel}</strong>: <span style="color:var(--ink-700);">${doc.file_name || "Uploaded Document"}</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="pill ${pillClass}">${docStatus}</span>
                  ${doc.verification_score !== null && doc.verification_score !== undefined ? `<span style="font-weight:700; color:var(--navy-900); font-size:0.8rem;">${Math.round(doc.verification_score)}%</span>` : ""}
                  <a href="${viewUrl}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="padding:4px 8px; font-size:0.75rem; text-decoration:none;">👁️ View / Open</a>
                  <a href="${downloadUrl}" class="btn btn-secondary" style="padding:4px 8px; font-size:0.75rem; text-decoration:none;">⬇️ Download</a>
                </div>
              </div>
              ${extractedHtml}
              ${mismatchHtml}
            </div>
          `;
        }).join("")}
      </div>
    `;
  } else {
    documentsSectionHtml = `<div class="notice notice-info" style="margin-top:14px;">No documents attached to this application.</div>`;
  }

  // Header status label
  let headerStatusHtml = "";
  if (c.top === "DECISION_MADE") {
    headerStatusHtml = `<span class="pill ${c.sub === 'APPROVED' ? 'pill-approve' : 'pill-reject'}">${c.sub} BY EVALUATOR</span>`;
  } else if (c.top === "APPEAL_PENDING") {
    headerStatusHtml = `<span class="pill pill-review">APPEAL PENDING (ORIG: ${c.originalDecision || "REJECTED"})</span>`;
  } else {
    headerStatusHtml = `<span class="pill pill-review">PENDING HUMAN DECISION</span>`;
  }

  drawerBody.innerHTML = `
    <div style="margin-bottom:18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
      <div>
        ${headerStatusHtml}
        <span class="app-id-box" style="margin-left:8px;">${app.id}</span>
      </div>
      <div>
        <a href="${API_BASE}/admin/applications/${app.id}/decision-passport?token=${encodeURIComponent(token)}" target="_blank" class="btn btn-secondary" style="padding:4px 10px; font-size:0.75rem; text-decoration:none;">
          🛂 Decision Passport
        </a>
      </div>
    </div>

    ${appealSectionHtml}

    <!-- Feature 3: Document Fraud / Anomaly Section -->
    ${anomalySectionHtml}

    <h3 style="margin-top:24px;">Applicant Data</h3>
    <div class="detail-row"><span class="k">Scholarship Scheme</span><span class="v"><strong>${d.scholarship_scheme}</strong></span></div>
    <div class="detail-row"><span class="k">Application Category</span><span class="v">${d.application_category}</span></div>
    <div class="detail-row"><span class="k">Academic Score</span><span class="v">${d.academic_score}%</span></div>
    <div class="detail-row"><span class="k">Previous Score</span><span class="v">${d.previous_score}%</span></div>
    <div class="detail-row"><span class="k">Attendance</span><span class="v">${d.attendance}%</span></div>
    <div class="detail-row"><span class="k">Annual Income</span><span class="v">₹${Number(d.annual_income || 0).toLocaleString("en-IN")}</span></div>
    <div class="detail-row"><span class="k">Verification Summary</span><span class="v">${d.documents_verified}</span></div>

    ${documentsSectionHtml}

    <h3 style="margin-top:24px;">AI Advisory Recommendation</h3>
    <div class="detail-row"><span class="k">Model Advisory Prediction</span><span class="v"><span class="pill ${c.isMLPending ? 'pill-ml-pending' : pillClassFor(app.model_decision || (fullDetails && fullDetails.ai_prediction && fullDetails.ai_prediction.prediction) || "NEEDS_HUMAN_REVIEW")}">${c.isMLPending ? 'ML Processing Pending' : formatDecisionLabel(app.model_decision || (fullDetails && fullDetails.ai_prediction && fullDetails.ai_prediction.prediction) || "NEEDS_HUMAN_REVIEW")}</span></span></div>
    <div class="detail-row"><span class="k">Model Confidence</span><span class="v"><strong style="color:var(--navy-900);">${formatConfidence(appData)}</strong></span></div>
    <div class="detail-row"><span class="k">Advisory Category</span><span class="v">${c.label}</span></div>
    ${app.override_applied ? `<div class="notice notice-warn" style="margin-top:10px;">${app.override_applied}</div>` : ""}
    <div class="notice ${c.isMLPending ? 'notice-warn' : 'notice-info'}" style="margin-top:14px; text-align:left;">${c.isMLPending ? 'No ML prediction has been generated for this application yet. This application is awaiting automated model evaluation or human evaluator review.' : (explanation.simple_explanation || "AI explanation summary unavailable.")}</div>

    <h4 style="margin-top:16px;">Top Reasons (SHAP)</h4>
    <ul class="reasons-list" style="max-width:none;">${c.isMLPending ? '<li><span style="color:var(--ink-500);">No SHAP factors calculated — ML processing pending.</span></li>' : reasonsHtml}</ul>

    <h4 style="margin-top:16px;">Why this was approved</h4>
    <ul class="reasons-list" style="max-width:none;">${c.isMLPending ? '<li><span style="color:var(--ink-500);">Not applicable — ML processing pending.</span></li>' : positiveHtml}</ul>

    <h4 style="margin-top:16px;">Why this was rejected or weakened</h4>
    <ul class="reasons-list" style="max-width:none;">${c.isMLPending ? '<li><span style="color:var(--ink-500);">Not applicable — ML processing pending.</span></li>' : negativeHtml}</ul>

    <h3 style="margin-top:24px;">Evaluator Decision</h3>
    ${alreadyDecided && !isAppealPending ? `
      <div class="notice notice-info">
        <strong>Final Decision Recorded:</strong> <span class="pill ${humanDecision === 'APPROVED' ? 'pill-approve' : 'pill-reject'}">${humanDecision}</span><br/>
        <div style="margin-top:8px;"><strong>Reason / Evaluator Comment:</strong> ${recordedReason || "—"}</div>
      </div>
    ` : `
      ${isAppealPending ? `
        <div class="notice notice-warn" style="margin-bottom:14px;">
          An active student appeal is pending. Recording an evaluator decision here will resolve the appeal and update the final authoritative decision.
        </div>
      ` : ""}
      <div class="form-field" style="margin-bottom:10px;">
        <label for="admin-decision-select">Final Evaluator Decision</label>
        <select id="admin-decision-select">
          <option value="" disabled selected>-- Select Evaluator Decision --</option>
          <option value="APPROVE">Approve</option>
          <option value="REJECT">Reject</option>
          <option value="NEEDS_HUMAN_REVIEW">Keep as Needs Review</option>
        </select>
      </div>
      <div class="form-field">
        <label for="admin-comment-input">Comment (mandatory explanation for this decision)</label>
        <textarea class="admin-comment" id="admin-comment-input" placeholder="e.g. Verified original marksheets and income certificate, applicant meets all eligibility norms."></textarea>
      </div>
      <div id="override-notice"></div>
      <div class="override-actions" style="margin-top:12px;">
        <button class="btn btn-primary" id="submit-override-btn">Record Final Decision</button>
      </div>
    `}
  `;

  // Attach Download All Documents Handler
  const downloadAllBtn = document.getElementById("download-all-docs-btn");
  if (downloadAllBtn && docsList.length > 0) {
    downloadAllBtn.addEventListener("click", async () => {
      downloadAllBtn.disabled = true;
      const originalBtnText = downloadAllBtn.innerHTML;
      downloadAllBtn.innerHTML = `<span class="spinner"></span> Downloading...`;
      const failedDocs = [];
      let successCount = 0;

      for (const doc of docsList) {
        try {
          const downloadUrl = `${API_BASE}/admin/applications/${app.id}/documents/${doc.id}/download?token=${encodeURIComponent(token)}`;
          const res = await fetch(downloadUrl);
          if (!res.ok) {
            throw new Error(`Server returned HTTP ${res.status}`);
          }
          const blob = await res.blob();
          const blobUrl = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = doc.file_name || `${doc.document_type || "document"}.pdf`;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(blobUrl);
          document.body.removeChild(a);
          successCount++;
          await new Promise(r => setTimeout(r, 350));
        } catch (err) {
          console.error("Document download failed:", doc, err);
          failedDocs.push(`${doc.document_type || "Document"}: ${doc.file_name || doc.id} (${err.message})`);
        }
      }

      downloadAllBtn.disabled = false;
      downloadAllBtn.innerHTML = originalBtnText;

      if (failedDocs.length > 0) {
        alert(`Downloaded ${successCount} of ${docsList.length} documents.\n\nThe following document(s) failed to download:\n• ` + failedDocs.join("\n• "));
      }
    });
  }

  // Attach Final Evaluator Decision Form Handler
  if (!alreadyDecided || isAppealPending) {
    const overrideBtn = document.getElementById("submit-override-btn");
    if (overrideBtn) {
      overrideBtn.addEventListener("click", async () => {
        const decisionSelect = document.getElementById("admin-decision-select");
        const commentInput = document.getElementById("admin-comment-input");
        const notice = document.getElementById("override-notice");

        const decision = decisionSelect ? decisionSelect.value : "";
        const comment = commentInput ? commentInput.value.trim() : "";

        if (!decision) {
          notice.innerHTML = `<div class="notice notice-error">Please select an evaluator decision before recording the final decision.</div>`;
          return;
        }

        if (!comment) {
          notice.innerHTML = `<div class="notice notice-error">Please provide a comment explaining the reason for this decision.</div>`;
          return;
        }

        overrideBtn.disabled = true;
        overrideBtn.innerHTML = `<span class="spinner"></span> Saving...`;

        try {
          // If appeal was pending, also resolve/review the appeal
          if (isAppealPending && appealObj && appealObj.id) {
            try {
              const appealReviewStatus = decision === "APPROVE" ? "RESOLVED" : "REJECTED";
              await apiPost(`/admin/appeals/${appealObj.id}/review`, {
                status: appealReviewStatus,
                review_comment: comment,
              }, false, token);
            } catch (appealErr) {
              console.warn("Appeal review sync warning:", appealErr);
            }
          }

          // Record authoritative human evaluator decision
          await apiPost("/admin/override", {
            application_id: app.id,
            admin_decision: decision,
            admin_comment: comment,
          }, false, token);

          notice.innerHTML = `<div class="notice notice-info">Final decision recorded successfully.</div>`;
          await loadApplications();
          closeDrawer();
        } catch (err) {
          notice.innerHTML = `<div class="notice notice-error">${err.message}</div>`;
          overrideBtn.disabled = false;
          overrideBtn.textContent = "Record Final Decision";
        }
      });
    }
  }
}

function closeDrawer() {
  drawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
}

drawerClose.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);

// Run initial login check
checkLoginState();
