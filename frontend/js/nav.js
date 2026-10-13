/* ==========================================================================
   JanNiti AI — Shared Accessible Responsive Navigation & Auth State
   File: frontend/js/nav.js
   Responsibilities:
   - Manages responsive hamburger menu button with full ARIA accessibility
   - Traps / manages keyboard interaction (Esc to close, outside click)
   - Synchronizes [data-auth-link] dynamically across pages based on session
   ========================================================================== */

(function () {
  "use strict";

  function initNav() {
    const toggleBtn = document.getElementById("nav-toggle-btn") || document.querySelector(".nav-toggle-btn");
    const siteNav = document.getElementById("site-nav") || document.querySelector(".site-nav");

    if (toggleBtn && siteNav) {
      toggleBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        const isOpen = siteNav.classList.toggle("is-open");
        toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
      });

      // Close when clicking any nav link inside mobile drawer
      siteNav.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
          if (siteNav.classList.contains("is-open")) {
            siteNav.classList.remove("is-open");
            toggleBtn.setAttribute("aria-expanded", "false");
          }
        });
      });

      // Close on Escape key press
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && siteNav.classList.contains("is-open")) {
          siteNav.classList.remove("is-open");
          toggleBtn.setAttribute("aria-expanded", "false");
          toggleBtn.focus();
        }
      });

      // Close on click outside
      document.addEventListener("click", function (e) {
        if (siteNav.classList.contains("is-open") && !siteNav.contains(e.target) && !toggleBtn.contains(e.target)) {
          siteNav.classList.remove("is-open");
          toggleBtn.setAttribute("aria-expanded", "false");
        }
      });

      // Reset when window resized to desktop
      window.addEventListener("resize", function () {
        if (window.innerWidth > 900 && siteNav.classList.contains("is-open")) {
          siteNav.classList.remove("is-open");
          toggleBtn.setAttribute("aria-expanded", "false");
        }
      });
    }

    // Synchronize [data-auth-link] across all pages
    syncAuthLinks();
  }

  function syncAuthLinks() {
    try {
      const token = sessionStorage.getItem("janniti_auth_token");
      const isLoggedIn = sessionStorage.getItem("janniti_student_logged_in") === "true" && Boolean(token);
      const studentName = sessionStorage.getItem("janniti_user_name");
      const authLinks = document.querySelectorAll("[data-auth-link]");

      authLinks.forEach(function (link) {
        if (isLoggedIn) {
          link.href = "user-dashboard.html";
          const label = studentName ? `Portal (${studentName.split(" ")[0]})` : "Student Portal";
          link.textContent = label;
          link.title = "Go to your Student Dashboard";
        } else {
          link.href = "user-login.html";
          link.textContent = "Student Login";
          link.title = "Login or register as a student";
        }
      });
    } catch (e) {
      // Storage access protected or disabled
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNav);
  } else {
    initNav();
  }

  // Expose helper globally for auth events
  window.syncJanNitiNavAuth = syncAuthLinks;
})();
