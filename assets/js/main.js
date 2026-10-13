/*
 * Walkie-Talkie — main.js
 * Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0
 */

(function () {
  'use strict';

  /* Theme Management: Auto-detect OS + manual toggle + persist in localStorage */
  function initTheme() {
    var storedTheme = localStorage.getItem('wt-theme');
    var systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)');

    function applyTheme(theme) {
      if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
      updateToggleButtons(theme);
    }

    function updateToggleButtons(theme) {
      var buttons = document.querySelectorAll('.theme-toggle');
      buttons.forEach(function (btn) {
        btn.textContent = (theme === 'dark') ? 'Light Mode' : 'Dark Mode';
      });
    }

    var initialTheme = storedTheme || (systemPrefersDark.matches ? 'dark' : 'light');
    applyTheme(initialTheme);

    // Listen to OS theme changes if user has no manual override saved
    systemPrefersDark.addEventListener('change', function (e) {
      if (!localStorage.getItem('wt-theme')) {
        applyTheme(e.matches ? 'dark' : 'light');
      }
    });

    // Handle toggle click
    document.addEventListener('click', function (e) {
      if (e.target && e.target.classList.contains('theme-toggle')) {
        var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        var next = (current === 'dark') ? 'light' : 'dark';
        localStorage.setItem('wt-theme', next);
        applyTheme(next);
      }
    });
  }

  /* Cookie Notice */
  function initCookieNotice() {
    var notice = document.getElementById('cookie-notice');
    if (!notice) return;
    if (localStorage.getItem('wt-notice-ok') === '1') {
      notice.classList.add('hidden');
      return;
    }
    var btn = document.getElementById('cookie-dismiss');
    if (!btn) return;
    btn.addEventListener('click', function () {
      localStorage.setItem('wt-notice-ok', '1');
      notice.classList.add('hidden');
    });
  }

  /* T&C Download Modal */
  function initDownloadModal() {
    var modal = document.getElementById('tnc-modal');
    if (!modal) return;
    var triggers = document.querySelectorAll('[data-download-url]');
    var acceptBtn = document.getElementById('modal-accept');
    var cancelBtn = document.getElementById('modal-cancel');
    var pendingUrl = null;

    triggers.forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        pendingUrl = el.getAttribute('data-download-url') || 'https://github.com/Shadow-457/walkie-talkie/releases';
        modal.showModal();
      });
    });

    if (acceptBtn) {
      acceptBtn.addEventListener('click', function () {
        modal.close();
        if (pendingUrl && pendingUrl !== '#') {
          window.location.href = pendingUrl;
        } else {
          window.location.href = 'https://github.com/Shadow-457/walkie-talkie/releases';
        }
        pendingUrl = null;
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        modal.close();
        pendingUrl = null;
      });
    }

    modal.addEventListener('click', function (e) {
      var r = modal.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) {
        modal.close();
        pendingUrl = null;
      }
    });
  }

  /* Platform Tabs */
  function initPlatformTabs() {
    var tabs = document.querySelectorAll('.platform-tab');
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var platform = tab.getAttribute('data-platform');
        document.querySelectorAll('.platform-tab').forEach(function (t) { t.classList.remove('active'); });
        tab.classList.add('active');
        document.querySelectorAll('.platform-content').forEach(function (c) { c.classList.remove('active'); });
        var panel = document.getElementById('platform-' + platform);
        if (panel) panel.classList.add('active');
      });
    });
  }

  /* Copy-to-clipboard buttons (landing page mockup, docs snippets) */
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }

  function initCopyButtons() {
    var buttons = document.querySelectorAll('[data-copy]');
    if (!buttons.length) return;
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var text = btn.getAttribute('data-copy') || '';
        var original = btn.textContent;
        function done() {
          btn.textContent = 'Copied';
          setTimeout(function () { btn.textContent = original; }, 1500);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {
            fallbackCopy(text);
            done();
          });
        } else {
          fallbackCopy(text);
          done();
        }
      });
    });
  }

  /* Docs Sidebar Active Link */
  function initDocsNav() {
    var links = document.querySelectorAll('.docs-sidebar a');
    if (!links.length) return;
    var page = window.location.pathname.split('/').pop() || 'index.html';
    links.forEach(function (link) {
      var href = (link.getAttribute('href') || '').split('/').pop();
      if (href === page) link.classList.add('active');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initCookieNotice();
    initDownloadModal();
    initPlatformTabs();
    initCopyButtons();
    initDocsNav();
  });
})();
