/* api.js — shared config + fetch helpers used by every page */

const API_BASE = "http://localhost:5000";

function getStoredToken() {
  try {
    return sessionStorage.getItem("janniti_auth_token");
  } catch {
    return null;
  }
}

async function apiPost(path, body, isFormData = false, token = null) {
  const headers = {};
  if (!isFormData) {
    headers["Content-Type"] = "application/json";
  }
  const activeToken = token || getStoredToken();
  if (activeToken) {
    headers["Authorization"] = `Bearer ${activeToken}`;
  }

  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers,
    body: isFormData ? body : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

async function apiPut(path, body, isFormData = false, token = null) {
  const headers = {};
  if (!isFormData) {
    headers["Content-Type"] = "application/json";
  }
  const activeToken = token || getStoredToken();
  if (activeToken) {
    headers["Authorization"] = `Bearer ${activeToken}`;
  }

  const res = await fetch(API_BASE + path, {
    method: "PUT",
    headers,
    body: isFormData ? body : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

async function apiGet(path, token = null) {
  const headers = {};
  const activeToken = token || getStoredToken();
  if (activeToken) {
    headers["Authorization"] = `Bearer ${activeToken}`;
  }

  const res = await fetch(API_BASE + path, { headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function formatDecisionLabel(decision) {
  const map = {
    APPROVE: "Approved",
    REJECT: "Rejected",
    NEEDS_HUMAN_REVIEW: "Needs Human Review",
    ML_PROCESSING_PENDING: "ML Processing Pending",
  };
  return map[decision] || decision;
}

function pillClassFor(decision) {
  if (decision === "APPROVE") return "pill-approve";
  if (decision === "REJECT") return "pill-reject";
  if (decision === "NEEDS_HUMAN_REVIEW") return "pill-review";
  if (decision === "ML_PROCESSING_PENDING") return "pill-ml-pending";
  return "pill-neutral";
}

function formatDateTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// Ensure helpers are globally available in browser window scope
if (typeof window !== "undefined") {
  window.apiGet = apiGet;
  window.apiPost = apiPost;
  window.apiPut = apiPut;
}

