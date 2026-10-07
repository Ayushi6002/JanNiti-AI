/* track.js */

const trackForm = document.getElementById("track-form");
const appIdInput = document.getElementById("app-id-input");
const statusResult = document.getElementById("status-result");
const trackBtn = document.getElementById("track-btn");

function getRiskPillClass(risk) {
  const r = (risk || "LOW").toUpperCase();
  if (r === "HIGH") return "pill-risk-high";
  if (r === "MEDIUM" || r === "MED") return "pill-risk-medium";
  return "pill-risk-low";
}

function renderStatus(data, anomalyData) {
  const hasPred = !!(data.ai_prediction || (data.decision && data.decision !== "NONE" && data.decision !== "PENDING") || (data.prediction && data.prediction !== "PENDING"));
  const decisionValue = (!hasPred) ? "ML_PROCESSING_PENDING" : ((data.decision && typeof data.decision === "object")
    ? (data.decision.decision || data.status)
    : (data.decision || data.status));
  const pillClass = pillClassFor(decisionValue);
  const decisionLabel = formatDecisionLabel(decisionValue);
  const rawConf = (typeof data.confidence === "number" && data.confidence > 0) ? data.confidence : ((data.ai_prediction && typeof data.ai_prediction.probability === "number") ? data.ai_prediction.probability : null);
  const confidenceDisplay = (hasPred && rawConf !== null) ? `${Math.round(rawConf <= 1.0 ? rawConf * 100 : rawConf)}%` : "Not Available — ML Processing Pending";
  const explanation = data.explanation || (data.ai_prediction && data.ai_prediction.explanation) || {};
  const explanationText = explanation.simple_explanation || "This recommendation was generated using the current scholarship rule set and model output.";
  const positiveReasons = explanation.why_approved || [];
  const negativeReasons = explanation.why_rejected || [];

  let reasonsHtml = "";
  if (data.top_reasons || (data.ai_prediction && data.ai_prediction.top_reasons)) {
    const reasons = data.top_reasons || data.ai_prediction.top_reasons || [];
    reasonsHtml = `
      <h3>Reasons</h3>
      <ul class="reasons-list">
        ${reasons.map(r => `
          <li>
            <span class="reason-arrow ${r.direction === "increased" ? "up" : "down"}">${r.direction === "increased" ? "▲" : "▼"}</span>
            <span><strong>${(r.feature || "").replace(/_/g, " ")}</strong> ${r.direction || "affected"} the likelihood of this outcome.</span>
          </li>`).join("")}
      </ul>`;
  } else if (data.message) {
    reasonsHtml = `<div class="notice notice-info">${data.message}</div>`;
  }

  // Feature 3: Anomaly & Document Risk Data
  const anomaly = anomalyData || data.anomaly_assessment || null;
  let anomalyHtml = "";

  if (anomaly) {
    const risk = (anomaly.risk_level || "LOW").toUpperCase();
    const score = Math.round(Number(anomaly.anomaly_score) || 0);
    const status = anomaly.status || "CLEAN";
    const isClean = status === "CLEAN";
    const riskPill = getRiskPillClass(risk);
    const reasons = anomaly.reasons || [];

    const studentReasonsHtml = reasons.length ? reasons.map(r => `
      <div class="anomaly-card-item sev-${(r.severity || "medium").toLowerCase()}">
        <div class="anomaly-item-header">
          <span class="anomaly-type-title">${(r.type || "Document Inconsistency").replace(/_/g, " ")}</span>
          <span class="pill ${getRiskPillClass(r.severity || "MEDIUM")}">${r.severity || "MEDIUM"}</span>
        </div>
        ${r.document_type ? `<div class="anomaly-item-doc">Document: ${r.document_type.replace(/_/g, " ")}</div>` : ""}
        <p class="anomaly-item-msg">${r.message || "Potential discrepancy detected in document verification."}</p>
      </div>
    `).join("") : `<div class="notice notice-info">All submitted documents are consistent and complete.</div>`;

    anomalyHtml = `
      <div class="anomaly-panel" style="margin-top:24px; text-align:left;">
        <div class="anomaly-panel-header">
          <h3 class="anomaly-panel-title">🛡️ Document Verification & Anomaly Risk</h3>
          <span class="pill ${riskPill}">${risk} RISK (${score}/100)</span>
        </div>
        <div class="anomaly-panel-body">
          <div class="risk-meter">
            <div class="risk-meter-label">
              <span>Document Anomaly Score</span>
              <span>${score} / 100 (${risk} Risk)</span>
            </div>
            <div class="risk-meter-track">
              <div class="risk-meter-fill ${risk.toLowerCase()}" style="width:${Math.max(5, Math.min(100, score))}%;"></div>
            </div>
          </div>

          <div class="detail-row"><span class="k">Anomaly Status</span><span class="v">${status.replace(/_/g, " ")}</span></div>
          <div class="detail-row"><span class="k">Human Review</span><span class="v">${anomaly.human_review_required ? "Required (Discrepancy Routed for Review)" : "Not Required (Clean)"}</span></div>
          <div class="detail-row"><span class="k">Summary</span><span class="v">${anomaly.summary || "Document check completed."}</span></div>

          ${isClean ? `
            <div class="notice notice-info" style="margin-top:14px;">
              ✅ <strong>No Document Anomalies Detected:</strong> All declared fields match the verified documents and no integrity issues were flagged.
            </div>
          ` : `
            <div class="notice notice-warn" style="margin-top:14px;">
              ⚠️ <strong>Action Required / Evaluator Review:</strong> One or more document discrepancies were detected. These are flagged for an evaluator to verify manually. AI never automatically rejects applications based on anomaly scores.
            </div>
            <h4 style="margin:16px 0 8px;">Document Issues to Resolve</h4>
            <div class="anomaly-cards-grid">
              ${studentReasonsHtml}
            </div>
          `}

          <div style="margin-top:14px; font-size:0.8rem; color:var(--ink-500); line-height:1.4;">
            ℹ️ <strong>Transparency Note:</strong> Document anomaly detection is strictly advisory. Suspicious items route safely to human evaluation.
          </div>
        </div>
      </div>
    `;
  }

  statusResult.innerHTML = `
    <div class="card" style="padding:24px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div>
          <div style="font-size:0.8rem; color:var(--ink-500);">Application ID</div>
          <div class="app-id-box" style="margin-top:4px;">${data.application_id}</div>
        </div>
        <span class="pill ${pillClass}">${decisionLabel}</span>
      </div>

      <div class="detail-row"><span class="k">Processing Status</span><span class="v">${(data.status || "UNKNOWN").replace(/_/g, " ")}</span></div>
      <div class="detail-row"><span class="k">Model Confidence</span><span class="v">${confidenceDisplay}</span></div>

      <div class="notice notice-info" style="margin-top:16px; text-align:left;">${explanationText}</div>

      <div style="margin-top:18px;">${reasonsHtml}</div>

      <!-- Feature 3: Document Fraud & Anomaly Risk Section -->
      ${anomalyHtml}

      <div class="section-panel" style="margin-top:20px; margin-bottom:0; text-align:left;">
        <div class="section-panel-header"><h3 style="margin:0;">Why this decision was made</h3></div>
        <div class="section-panel-body">
          <div style="display:grid; gap:12px;">
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
    </div>
  `;
}

async function performTrack(id) {
  trackBtn.disabled = true;
  trackBtn.innerHTML = `<span class="spinner"></span>`;
  statusResult.innerHTML = "";

  const token = sessionStorage.getItem("janniti_auth_token");

  try {
    const data = await apiGet(`/status/${encodeURIComponent(id)}`, token);
    
    // Explicitly call the dedicated Feature 3 Student Anomaly API:
    // GET /student/applications/<app_id>/anomalies
    let anomalyData = null;
    try {
      anomalyData = await apiGet(`/student/applications/${encodeURIComponent(id)}/anomalies`, token);
    } catch (anomalyErr) {
      console.warn("Could not fetch dedicated student anomalies endpoint:", anomalyErr.message);
      // Fallback to anomaly_assessment from status payload if available
      anomalyData = data.anomaly_assessment || null;
    }

    renderStatus(data, anomalyData);
  } catch (err) {
    statusResult.innerHTML = `<div class="notice notice-error">${err.message}. Double-check the Application ID and ensure you are logged in.</div>`;
  } finally {
    trackBtn.disabled = false;
    trackBtn.textContent = "Check Status";
  }
}

trackForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = appIdInput.value.trim();
  if (!id) return;
  await performTrack(id);
});

// Auto-fill from URL parameter ?id=... if present
const urlParams = new URLSearchParams(window.location.search);
const prefilledId = urlParams.get("id");
if (prefilledId) {
  appIdInput.value = prefilledId;
  performTrack(prefilledId);
}
