/*
 * Janniti AI - Supabase Authentication Helper
 *
 * IMPORTANT:
 * - The anon/publishable key is safe for browser use.
 * - NEVER put the Supabase service-role/secret key here.
 */

const SUPABASE_URL = "https://ikhxihayzljupugkkznz.supabase.co";

// Put your PUBLIC anon key here.
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlraHhpaGF5emxqdXB1Z2trem56Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTAzNTYwMTIsImV4cCI6MjEwNTkzMjAxMn0.gLZeCGjTxAT9yPVCTPIr542Dp3j7oMEBifdAo8HfaHg";

if (!window.supabase) {
  throw new Error(
    "Supabase JS library is not loaded. Load the Supabase CDN before supabase-auth.js."
  );
}

const supabaseClient = window.supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);


// Sign in an existing user.
async function supabaseLogin(email, password) {
  const { data, error } = await supabaseClient.auth.signInWithPassword({
    email,
    password
  });

  if (error) {
    throw new Error(error.message);
  }

  if (!data.session || !data.session.access_token) {
    throw new Error(
      "Supabase login succeeded but no access token was returned."
    );
  }

  return {
    user: data.user,
    session: data.session,
    access_token: data.session.access_token
  };
}


// Sign up a new user.
async function supabaseSignup(email, password, metadata = {}) {
  const { data, error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: {
      data: metadata
    }
  });

  if (error) {
    throw new Error(error.message);
  }

  return data;
}


// Get the current Supabase session.
async function getSupabaseSession() {
  const { data, error } = await supabaseClient.auth.getSession();

  if (error) {
    throw new Error(error.message);
  }

  return data.session;
}


// Get the current Supabase user.
async function getSupabaseUser() {
  const { data, error } = await supabaseClient.auth.getUser();

  if (error) {
    return null;
  }

  return data.user;
}


// Sign out.
async function supabaseLogout() {
  const { error } = await supabaseClient.auth.signOut();

  if (error) {
    throw new Error(error.message);
  }
}


// Fetch profile from backend with Supabase token
async function fetchCurrentStudentProfile(accessToken) {
  try {
    const token = accessToken || sessionStorage.getItem("janniti_auth_token");
    if (!token) return null;
    const res = await fetch("http://localhost:5000/student/profile", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn("fetchCurrentStudentProfile error:", err);
  }
  return null;
}


// Save authentication information for the existing Janniti frontend.
function persistSupabaseAuth(session, user, profile = {}) {
  sessionStorage.setItem(
    "janniti_auth_token",
    session.access_token
  );

  sessionStorage.setItem(
    "janniti_refresh_token",
    session.refresh_token || ""
  );

  sessionStorage.setItem(
    "janniti_student_logged_in",
    "true"
  );

  sessionStorage.setItem(
    "janniti_student_email",
    user.email || ""
  );

  sessionStorage.setItem(
    "janniti_supabase_user_id",
    user.id || ""
  );

  sessionStorage.setItem(
    "janniti_user_role",
    profile.role || "applicant"
  );

  sessionStorage.setItem(
    "janniti_user_name",
    profile.full_name ||
    user.user_metadata?.full_name ||
    user.email?.split("@")[0] ||
    ""
  );
}


// Clear Janniti authentication storage.
function clearSupabaseAuthStorage() {
  sessionStorage.removeItem("janniti_auth_token");
  sessionStorage.removeItem("janniti_refresh_token");
  sessionStorage.removeItem("janniti_student_logged_in");
  sessionStorage.removeItem("janniti_student_email");
  sessionStorage.removeItem("janniti_supabase_user_id");
  sessionStorage.removeItem("janniti_user_role");
  sessionStorage.removeItem("janniti_user_name");
}