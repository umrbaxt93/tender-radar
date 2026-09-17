/**
 * Softy Platforma — Main Frontend Application (Section 17)
 * Davlat xaridlari qidiruvi, ko'p o'lchamli filtrlar, korxonalar va shartnomalar,
 * xaridlar xronologiyasi (Timeline), asoslangan tijorat taklifi, Bitrix24 va Admin Paneli.
 */

// ==========================================================================
// Authentication & Global Fetch Interceptor
// ==========================================================================
const AUTH_TOKEN_KEY = "softy_auth_token";
let currentUser = null;

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || sessionStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function setAuthToken(token, remember = true) {
  if (token) {
    if (remember) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
      sessionStorage.removeItem(AUTH_TOKEN_KEY);
    } else {
      sessionStorage.setItem(AUTH_TOKEN_KEY, token);
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

// Global fetch interceptor to attach Bearer token and handle 401 unauthorized
const _nativeFetch = window.fetch;
window.fetch = async function (url, options = {}) {
  const token = getAuthToken();
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  opts.headers = headers;

  const res = await _nativeFetch(url, opts);
  if (res.status === 401 && typeof url === "string" && !url.includes("/api/auth/login")) {
    setAuthToken(null);
    showAuthGate("Sessiyangiz muddati tugagan yoki ruxsat yo'q. Iltimos, qaytadan kiring.");
  }
  return res;
};

function showAuthGate(errorMessage = null) {
  const authGate = document.getElementById("auth-gate");
  const appRoot = document.getElementById("app-root");
  const errorAlert = document.getElementById("auth-error-alert");

  if (authGate) authGate.style.display = "flex";
  if (appRoot) appRoot.style.display = "none";

  if (errorAlert) {
    if (errorMessage) {
      errorAlert.textContent = errorMessage;
      errorAlert.style.display = "block";
    } else {
      errorAlert.style.display = "none";
    }
  }
}

function hideAuthGate() {
  const authGate = document.getElementById("auth-gate");
  const appRoot = document.getElementById("app-root");
  if (authGate) authGate.style.display = "none";
  if (appRoot) appRoot.style.display = "block";
}

function updateUserNavbar() {
  const userBadgeName = document.getElementById("nav-username");
  if (userBadgeName && currentUser) {
    userBadgeName.textContent = currentUser.full_name || currentUser.username;
  }
}

async function checkAuthAndInit() {
  const token = getAuthToken();
  if (!token) {
    showAuthGate();
    return;
  }

  try {
    const res = await fetch("/api/auth/me");
    const data = await res.json();
    if (data && data.authenticated && data.user) {
      currentUser = data.user;
      hideAuthGate();
      updateUserNavbar();
      await initApp();
    } else {
      setAuthToken(null);
      showAuthGate("Sessiyangiz muddati tugagan. Iltimos, qaytadan kiring.");
    }
  } catch (err) {
    console.error("Auth check failed:", err);
    showAuthGate();
  }
}

async function initApp() {
  await loadStaffList();
  readStateFromUrl();
  syncFormToState();
  performSearch();
}

async function handleLogin() {
  const usernameInput = document.getElementById("auth-username");
  const passwordInput = document.getElementById("auth-password");
  const errorAlert = document.getElementById("auth-error-alert");
  const btnSubmit = document.getElementById("btn-auth-submit");
  const btnText = document.getElementById("btn-auth-text");

  const username = usernameInput ? usernameInput.value.trim() : "";
  const password = passwordInput ? passwordInput.value : "";

  if (!username || !password) {
    if (errorAlert) {
      errorAlert.textContent = "Login va maxfiy parolni kiriting.";
      errorAlert.style.display = "block";
    }
    return;
  }

  if (btnSubmit) btnSubmit.disabled = true;
  if (btnText) btnText.textContent = "Tekshirilmoqda...";
  if (errorAlert) errorAlert.style.display = "none";

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      const rememberMe = document.getElementById("auth-remember-me") ? document.getElementById("auth-remember-me").checked : true;
      setAuthToken(data.token, rememberMe);
      currentUser = data.user;
      hideAuthGate();
      updateUserNavbar();
      showToast(`Xush kelibsiz, ${currentUser.full_name || currentUser.username}!`, "success");
      await initApp();
    } else {
      if (errorAlert) {
        errorAlert.textContent = data.error || "Login yoki parol noto'g'ri kiritildi.";
        errorAlert.style.display = "block";
      }
    }
  } catch (err) {
    if (errorAlert) {
      errorAlert.textContent = "Server bilan aloqa o'rnatib bo'lmadi: " + err.message;
      errorAlert.style.display = "block";
    }
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
    if (btnText) btnText.textContent = "Tizimga Kirish ➔";
  }
}

async function handleLogout(callApi = true) {
  const token = getAuthToken();
  setAuthToken(null);
  currentUser = null;
  showAuthGate();
  showToast("Tizimdan muvaffaqiyatli chiqildi", "info");

  if (token && callApi) {
    try {
      await _nativeFetch("/api/auth/logout", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
    } catch (e) {
      // ignore
    }
  }
}

// Application State
const state = {
  query: "",
  view_mode: "lots", // 'lots', 'companies', 'contracts'
  platforms: ["xt_xarid", "uzex", "ebirja", "cooperation"],
  date_field: "announcement_date",
  quick_period: "all",
  date_from: "",
  date_to: "",
  include_missing_dates: false,
  official_status: "",
  has_contract: false,
  expiry_known: false,
  min_price: "",
  max_price: "",
  region: "",
  assigned_staff_id: "",
  crm_status: "",
  limit: 50,
  offset: 0,
  page: 1,
  total_count: 0,
  staffList: [],
  currentCompanyInn: null,
  currentProposalDraft: null
};

// DOM Elements
const searchInput = document.getElementById("global-search-input");
const btnSubmitSearch = document.getElementById("btn-submit-search");
const btnClearSearch = document.getElementById("btn-clear-search");
const filterDateField = document.getElementById("filter-date-field");
const filterDateFrom = document.getElementById("filter-date-from");
const filterDateTo = document.getElementById("filter-date-to");
const filterIncludeMissingDates = document.getElementById("filter-include-missing-dates");
const filterOfficialStatus = document.getElementById("filter-official-status");
const filterHasContract = document.getElementById("filter-has-contract");
const filterExpiryKnown = document.getElementById("filter-expiry-known");
const filterMinPrice = document.getElementById("filter-min-price");
const filterMaxPrice = document.getElementById("filter-max-price");
const filterRegion = document.getElementById("filter-region");
const filterAssignedStaff = document.getElementById("filter-assigned-staff");
const filterCrmStatus = document.getElementById("filter-crm-status");
const btnApplyFilters = document.getElementById("btn-apply-filters");
const btnResetFilters = document.getElementById("btn-reset-filters");
const btnExportExcel = document.getElementById("btn-export-excel");
const btnExportPdf = document.getElementById("btn-export-pdf");

// Modals & Triggers
const modalTimeline = document.getElementById("modal-timeline");
const modalProposal = document.getElementById("modal-proposal");
const modalSources = document.getElementById("modal-sources");
const modalSavedSearches = document.getElementById("modal-saved-searches");
const modalAdmin = document.getElementById("modal-admin");
const btnSourcesModal = document.getElementById("btn-sources-modal");
const btnSavedSearchesModal = document.getElementById("btn-saved-searches-modal");
const btnAdminModal = document.getElementById("btn-admin-modal");
const btnLogout = document.getElementById("btn-logout");
const toastContainer = document.getElementById("toast-container");

// Initialize on page load: check authentication first
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await checkAuthAndInit();
});

// ==========================================================================
// Event Listeners
// ==========================================================================
function setupEventListeners() {
  // Search Bar
  btnSubmitSearch.addEventListener("click", () => {
    state.query = searchInput.value.trim();
    state.offset = 0;
    state.page = 1;
    syncStateToUrl();
    performSearch();
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      btnSubmitSearch.click();
    }
  });

  searchInput.addEventListener("input", () => {
    btnClearSearch.style.display = searchInput.value ? "block" : "none";
  });

  btnClearSearch.addEventListener("click", () => {
    searchInput.value = "";
    btnClearSearch.style.display = "none";
    btnSubmitSearch.click();
  });

  // Search Hints Tags
  document.querySelectorAll(".hint-tag").forEach(tag => {
    tag.addEventListener("click", () => {
      searchInput.value = tag.getAttribute("data-query");
      btnClearSearch.style.display = "block";
      btnSubmitSearch.click();
    });
  });

  // Quick Period Pills
  document.querySelectorAll(".pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const period = btn.getAttribute("data-period");
      state.quick_period = period;

      // Reset manual dates when quick period selected
      if (period !== "all") {
        filterDateFrom.value = "";
        filterDateTo.value = "";
        state.date_from = "";
        state.date_to = "";
      }
      state.offset = 0;
      state.page = 1;
      syncStateToUrl();
      performSearch();
    });
  });

  // Apply & Reset Filters
  btnApplyFilters.addEventListener("click", () => {
    readFormIntoState();
    state.offset = 0;
    state.page = 1;
    syncStateToUrl();
    performSearch();
  });

  btnResetFilters.addEventListener("click", () => {
    resetAllFilters();
  });

  document.getElementById("btn-clear-all-tags").addEventListener("click", () => {
    resetAllFilters();
  });

  document.getElementById("btn-empty-reset").addEventListener("click", () => {
    resetAllFilters();
  });

  // Tab Switching
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const targetTab = btn.getAttribute("data-tab");
      state.view_mode = targetTab;
      state.offset = 0;
      state.page = 1;

      document.querySelectorAll(".view-pane").forEach(pane => pane.classList.remove("active"));
      document.getElementById(`pane-${targetTab}`).classList.add("active");

      syncStateToUrl();
      performSearch();
    });
  });

  // Pagination
  document.getElementById("btn-prev-page").addEventListener("click", () => {
    if (state.offset > 0) {
      state.offset = Math.max(0, state.offset - state.limit);
      state.page = Math.floor(state.offset / state.limit) + 1;
      performSearch();
    }
  });

  document.getElementById("btn-next-page").addEventListener("click", () => {
    if (state.offset + state.limit < state.total_count) {
      state.offset += state.limit;
      state.page = Math.floor(state.offset / state.limit) + 1;
      performSearch();
    }
  });

  // Export Excel (.xlsx) & PDF (.pdf)
  if (btnExportExcel) {
    btnExportExcel.addEventListener("click", () => {
      triggerExport("xlsx");
    });
  }
  if (btnExportPdf) {
    btnExportPdf.addEventListener("click", () => {
      triggerExport("pdf");
    });
  }

  // Modals Close handlers
  document.querySelectorAll("[data-close]").forEach(btn => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-close");
      document.getElementById(modalId).style.display = "none";
    });
  });

  window.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-backdrop")) {
      e.target.style.display = "none";
    }
  });

  // Platform sources modal trigger
  btnSourcesModal.addEventListener("click", () => {
    openSourcesModal();
  });

  // Saved searches modal trigger
  btnSavedSearchesModal.addEventListener("click", () => {
    openSavedSearchesModal();
  });

  document.getElementById("btn-save-current-search").addEventListener("click", () => {
    saveCurrentSearch();
  });

  const btnRunFullSync = document.getElementById("btn-run-full-sync");
  if (btnRunFullSync) {
    btnRunFullSync.addEventListener("click", async () => {
      btnRunFullSync.disabled = true;
      btnRunFullSync.textContent = "⏳ Sinxronlanmoqda...";
      showToast("Anti-blocking sinxronizatsiya boshlandi (2024-01-01 dan)...", "info");
      try {
        const res = await fetch("/api/sync/run", { method: "POST" });
        const data = await res.json();
        showToast(`Sinxronizatsiya yakunlandi! Qo'shildi: ${data.total_records_added || 0} ta`, "success");
        openSourcesModal();
        performSearch();
      } catch (err) {
        showToast("Sinxronlashda xatolik: " + err.message, "error");
      } finally {
        btnRunFullSync.disabled = false;
        btnRunFullSync.textContent = "🔄 Hozir sinxronlash";
      }
    });
  }

  // E-IMZO & Sessiya Modali boshqaruvi
  const btnEimzoModal = document.getElementById("btn-eimzo-modal");
  const modalEimzo = document.getElementById("modal-eimzo");
  const btnSaveEimzo = document.getElementById("btn-save-eimzo");
  const btnClearEimzo = document.getElementById("btn-clear-eimzo");
  const eimzoTokenInput = document.getElementById("eimzo-token-input");
  const eimzoTinInput = document.getElementById("eimzo-tin-input");
  const eimzoDaemonStatus = document.getElementById("eimzo-daemon-status");
  const eimzoSessionStatus = document.getElementById("eimzo-session-status");

  if (btnEimzoModal) {
    btnEimzoModal.addEventListener("click", async () => {
      modalEimzo.style.display = "flex";
      try {
        const res = await fetch("/api/eimzo/status");
        const d = await res.json();
        if (d.daemon && d.daemon.running) {
          eimzoDaemonStatus.textContent = "✅ " + d.daemon.message;
          eimzoDaemonStatus.style.color = "#059669";
        } else {
          eimzoDaemonStatus.textContent = "⚠️ " + (d.daemon?.message || "Faol emas");
          eimzoDaemonStatus.style.color = "#d97706";
        }

        if (d.session && d.session.authenticated) {
          eimzoSessionStatus.textContent = `✅ Faol (STIR: ${d.session.tin})`;
          eimzoSessionStatus.style.color = "#059669";
          if (d.session.token) eimzoTokenInput.value = d.session.token;
          if (d.session.tin) eimzoTinInput.value = d.session.tin;
        } else {
          eimzoSessionStatus.textContent = "Faol emas (kalit kiritilmagan)";
          eimzoSessionStatus.style.color = "#64748b";
        }
      } catch (e) {
        console.error(e);
      }
    });
  }

  if (btnSaveEimzo) {
    btnSaveEimzo.addEventListener("click", async () => {
      const token = eimzoTokenInput.value.trim();
      const tin = eimzoTinInput.value.trim() || "308904387";
      try {
        const res = await fetch("/api/eimzo/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, tin })
        });
        const d = await res.json();
        showToast(d.message || "E-IMZO sessiyasi saqlandi", "success");
        modalEimzo.style.display = "none";
      } catch (e) {
        showToast("Xatolik: " + e.message, "error");
      }
    });
  }

  if (btnClearEimzo) {
    btnClearEimzo.addEventListener("click", async () => {
      try {
        await fetch("/api/eimzo/clear", { method: "POST" });
        eimzoTokenInput.value = "";
        eimzoSessionStatus.textContent = "Faol emas";
        showToast("E-IMZO sessiyasi tozalandi", "info");
      } catch (e) {
        showToast("Xatolik: " + e.message, "error");
      }
    });
  }

  // Proposal confirmation checkbox gate
  const checkConfirm = document.getElementById("check-confirm-pricing");
  const btnConfirmProposal = document.getElementById("btn-confirm-proposal");
  checkConfirm.addEventListener("change", () => {
    btnConfirmProposal.disabled = !checkConfirm.checked;
  });

  btnConfirmProposal.addEventListener("click", async () => {
    await confirmAndSaveProposal();
  });

  document.getElementById("btn-copy-proposal").addEventListener("click", () => {
    const text = document.getElementById("proposal-body-text").value;
    navigator.clipboard.writeText(text).then(() => {
      showToast("Taklif matni nusxalandi!", "success");
    });
  });

  // Timeline modal action buttons
  document.getElementById("btn-open-proposal-from-timeline").addEventListener("click", () => {
    if (state.currentCompanyInn) {
      modalTimeline.style.display = "none";
      openProposalModal(state.currentCompanyInn);
    }
  });

  document.getElementById("btn-sync-bitrix-timeline").addEventListener("click", async () => {
    if (state.currentCompanyInn) {
      await syncToBitrix(state.currentCompanyInn);
    }
  });

  document.getElementById("btn-save-new-task").addEventListener("click", async () => {
    const taskInput = document.getElementById("new-task-title");
    const title = taskInput.value.trim();
    if (!title || !state.currentCompanyInn) return;
    
    await saveNewTask(state.currentCompanyInn, title);
    taskInput.value = "";
  });

  document.getElementById("timeline-assign-select").addEventListener("change", async (e) => {
    if (state.currentCompanyInn && e.target.value) {
      await assignStaffMember(state.currentCompanyInn, e.target.value);
    }
  });

  // Auth Form Submit
  const authForm = document.getElementById("auth-login-form");
  if (authForm) {
    authForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handleLogin();
    });
  }

  // Password Visibility Toggle
  const btnTogglePwd = document.getElementById("btn-toggle-pwd");
  const authPasswordInput = document.getElementById("auth-password");
  const eyeIcon = document.getElementById("eye-icon");
  const eyeText = document.getElementById("eye-text");
  if (btnTogglePwd && authPasswordInput) {
    btnTogglePwd.addEventListener("click", () => {
      if (authPasswordInput.type === "password") {
        authPasswordInput.type = "text";
        if (eyeIcon) eyeIcon.textContent = "🙈";
        if (eyeText) eyeText.textContent = "Yashirish";
      } else {
        authPasswordInput.type = "password";
        if (eyeIcon) eyeIcon.textContent = "👁️";
        if (eyeText) eyeText.textContent = "Ko'rsatish";
      }
    });
  }

  // Logout Button
  const btnLogoutEl = document.getElementById("btn-logout");
  if (btnLogoutEl) {
    btnLogoutEl.addEventListener("click", () => {
      handleLogout();
    });
  }

  // Admin Panel Modal Trigger
  const btnAdminModalEl = document.getElementById("btn-admin-modal");
  if (btnAdminModalEl) {
    btnAdminModalEl.addEventListener("click", () => {
      openAdminModal();
    });
  }

  // Admin Panel Tab Switching
  document.querySelectorAll("[data-admin-tab]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-admin-tab]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const targetTab = btn.getAttribute("data-admin-tab");
      document.querySelectorAll(".admin-tab-content").forEach(c => c.style.display = "none");
      const activeContent = document.getElementById(`admin-tab-${targetTab}`);
      if (activeContent) activeContent.style.display = "block";
    });
  });

  // Admin Manual Sync Button
  const btnAdminSyncNow = document.getElementById("btn-admin-sync-now");
  if (btnAdminSyncNow) {
    btnAdminSyncNow.addEventListener("click", async () => {
      const progress = document.getElementById("admin-sync-progress");
      btnAdminSyncNow.disabled = true;
      if (progress) progress.style.display = "block";
      showToast("To'liq sinxronizatsiya ishga tushirildi (2024-01-01 dan)...", "info");
      try {
        const res = await fetch("/api/sync/run", { method: "POST" });
        const data = await res.json();
        showToast(`Sinxronizatsiya muvaffaqiyatli yakunlandi! Qo'shildi: ${data.total_records_added || 0} ta`, "success");
        await loadAdminStats();
        await loadAdminSyncLogs();
        performSearch();
      } catch (err) {
        showToast("Sinxronlashda xatolik: " + err.message, "error");
      } finally {
        btnAdminSyncNow.disabled = false;
        if (progress) progress.style.display = "none";
      }
    });
  }

  // Admin Password Change Form
  const formChangePwd = document.getElementById("form-change-password");
  if (formChangePwd) {
    formChangePwd.addEventListener("submit", (e) => {
      e.preventDefault();
      handlePasswordChange();
    });
  }

  // Copy Gemini Pitch
  const btnCopyPitch = document.getElementById("btn-copy-gemini-pitch");
  if (btnCopyPitch) {
    btnCopyPitch.addEventListener("click", () => {
      const p = document.getElementById("gemini-pitch-text");
      if (p && navigator.clipboard) {
        navigator.clipboard.writeText(p.textContent.replace(/^"|"$/g, ''));
        showToast("Taklif matni nusxalandi!", "info");
      }
    });
  }

  // Send Gemini Lead to Bitrix24
  const btnSendBitrix = document.getElementById("btn-gemini-send-bitrix");
  if (btnSendBitrix) {
    btnSendBitrix.addEventListener("click", async () => {
      if (!currentGeminiAnalysis || !currentGeminiAnalysis.lot) return;
      const lot = currentGeminiAnalysis.lot;
      btnSendBitrix.disabled = true;
      btnSendBitrix.textContent = "⏳ Bitrix24 ga yuborilmoqda...";
      try {
        const res = await fetch("/api/crm/create-task", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            inn: lot.buyer_inn,
            company_name: lot.buyer_name,
            title: `[Gemini AI] ${lot.title} (${currentGeminiAnalysis.verdict || 'Tahlil'})`,
            responsible_id: "umid"
          })
        });
        const d = await res.json();
        showToast("Bitrix24 CRM da yangi savdo vazifasi yaratildi!", "success");
      } catch (err) {
        showToast("Bitrix24 ga yuborishda xatolik: " + err.message, "error");
      } finally {
        btnSendBitrix.disabled = false;
        btnSendBitrix.textContent = "💼 Bitrix24 ga AI Lidi sifatida yuborish";
      }
    });
  }

  // Save Gemini Key Form
  const formGeminiKey = document.getElementById("form-gemini-settings");
  if (formGeminiKey) {
    formGeminiKey.addEventListener("submit", async (e) => {
      e.preventDefault();
      const inp = document.getElementById("input-gemini-key");
      const key = inp ? inp.value.trim() : "";
      if (!key) {
        showToast("Gemini API kalitini kiriting", "warning");
        return;
      }
      try {
        const res = await fetch("/api/gemini/key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: key })
        });
        const d = await res.json();
        showToast(d.message || "Gemini API kaliti saqlandi!", "success");
        await loadGeminiStatus();
      } catch (err) {
        showToast("Saqlashda xatolik: " + err.message, "error");
      }
    });
  }
}

// ==========================================================================
// Gemini AI Tender Intelligence
// ==========================================================================
let currentGeminiAnalysis = null;

async function openGeminiModal(lotId) {
  const modal = document.getElementById("modal-gemini-ai");
  const loading = document.getElementById("gemini-loading");
  const content = document.getElementById("gemini-content");
  const sub = document.getElementById("gemini-lot-subtitle");

  if (!modal) return;
  modal.style.display = "flex";
  if (loading) loading.style.display = "block";
  if (content) content.style.display = "none";
  if (sub) sub.textContent = `Lot #${lotId} bo'yicha Gemini AI tahlili yuklanmoqda...`;

  try {
    const res = await fetch("/api/gemini/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lot_id: lotId })
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || "Tahlil qilib bo'lmadi", "error");
      modal.style.display = "none";
      return;
    }

    currentGeminiAnalysis = data;
    renderGeminiAnalysis(data);
  } catch (err) {
    showToast("Gemini AI bilan aloqa xatosi: " + err.message, "error");
    modal.style.display = "none";
  }
}

function renderGeminiAnalysis(data) {
  const loading = document.getElementById("gemini-loading");
  const content = document.getElementById("gemini-content");
  const sub = document.getElementById("gemini-lot-subtitle");
  const badge = document.getElementById("gemini-engine-badge");

  if (loading) loading.style.display = "none";
  if (content) content.style.display = "block";

  const lot = data.lot || {};
  if (sub) sub.textContent = `${lot.lot_number ? 'Lot #' + lot.lot_number + ': ' : ''}${lot.title || ''} • ${lot.buyer_name || 'Nomsiz buyurtmachi'}`;
  if (badge) badge.textContent = data.ai_engine || "Google Gemini";

  const scoreEl = document.getElementById("gemini-relevance-score");
  const catEl = document.getElementById("gemini-it-category");
  const verdictEl = document.getElementById("gemini-verdict");
  const winProbEl = document.getElementById("gemini-win-prob");
  const marginEl = document.getElementById("gemini-margin");
  const pricingEl = document.getElementById("gemini-pricing-text");
  const risksList = document.getElementById("gemini-risks-list");
  const tipsList = document.getElementById("gemini-tips-list");
  const pitchEl = document.getElementById("gemini-pitch-text");

  if (scoreEl) scoreEl.textContent = (data.relevance_score || 90) + "%";
  if (catEl) catEl.textContent = data.it_category || "IT Litsenziyalash";
  if (verdictEl) {
    verdictEl.textContent = data.verdict || "QATNASHISH TAVSIYA ETILADI";
    verdictEl.style.color = data.verdict_badge === "danger" ? "#dc2626" : (data.verdict_badge === "warning" ? "#d97706" : "#16a34a");
  }
  if (winProbEl) winProbEl.textContent = `Yutuq ehtimoli: ${data.win_probability || "Yuqori"}`;
  if (marginEl) marginEl.textContent = data.margin_estimate || "14% - 18%";
  if (pricingEl) pricingEl.textContent = data.pricing_strategy || "";

  if (risksList) {
    risksList.innerHTML = (data.hidden_risks || []).map(r => `<li>${escapeHtml(r)}</li>`).join("");
  }
  if (tipsList) {
    tipsList.innerHTML = (data.technical_tips || []).map(t => `<li>${escapeHtml(t)}</li>`).join("");
  }
  if (pitchEl) pitchEl.textContent = `"${data.client_pitch || ''}"`;
}

// ==========================================================================
// Admin Panel Functions
// ==========================================================================
async function openAdminModal() {
  const modalAdminEl = document.getElementById("modal-admin");
  if (modalAdminEl) modalAdminEl.style.display = "flex";
  await loadAdminStats();
  await loadAdminTasks();
  await loadAdminSyncLogs();
  await loadGeminiStatus();
  renderAdminStaff();
}

async function loadGeminiStatus() {
  try {
    const res = await fetch("/api/gemini/status");
    const data = await res.json();
    const stEl = document.getElementById("gemini-status-text");
    if (stEl && data) {
      stEl.textContent = data.mode || (data.has_key ? "Google Gemini 1.5 Flash (Live API)" : "Intelligent Heuristic IT Advisor");
    }
  } catch (e) {
    // ignore
  }
}

async function loadAdminStats() {
  try {
    const res = await fetch("/api/admin/stats");
    const data = await res.json();
    if (!data || !data.stats) return;

    const s = data.stats;
    const statLots = document.getElementById("admin-stat-lots");
    const statCompanies = document.getElementById("admin-stat-companies");
    const statContractSum = document.getElementById("admin-stat-contract-sum");
    const statContracts = document.getElementById("admin-stat-contracts");

    if (statLots) statLots.textContent = new Intl.NumberFormat("uz-UZ").format(s.total_lots);
    if (statCompanies) statCompanies.textContent = new Intl.NumberFormat("uz-UZ").format(s.total_companies);
    if (statContractSum) statContractSum.textContent = (s.total_contract_sum / 1e9).toFixed(1) + " mlrd";
    if (statContracts) statContracts.textContent = new Intl.NumberFormat("uz-UZ").format(s.total_contracts);

    // Platform distribution
    const pContainer = document.getElementById("admin-platform-stats");
    if (pContainer && s.platform_counts) {
      const platformNames = {
        "xt_xarid": "xt-xarid.uz",
        "uzex": "xarid.uzex.uz",
        "ebirja": "xarid.ebirja.uz",
        "cooperation": "new.cooperation.uz"
      };
      pContainer.innerHTML = Object.entries(s.platform_counts).map(([pid, cnt]) => `
        <div class="platform-stat-row">
          <span><strong>${platformNames[pid] || pid}</strong></span>
          <span class="badge ${cnt > 0 ? 'badge-success' : 'badge-warning'}">${new Intl.NumberFormat("uz-UZ").format(cnt)} ta lot</span>
        </div>
      `).join("");
    }
  } catch (err) {
    console.error("Failed to load admin stats:", err);
  }
}

async function loadAdminTasks() {
  try {
    const res = await fetch("/api/admin/tasks");
    const data = await res.json();
    const tasks = data.tasks || [];

    const tasksCount = document.getElementById("admin-tasks-count");
    if (tasksCount) tasksCount.textContent = `Jami: ${tasks.length} ta`;

    const tbody = document.getElementById("admin-tasks-body");
    if (!tbody) return;

    if (tasks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: #64748b; padding: 1.5rem;">Hozircha sotuv vazifalari mavjud emas. Lotlar yoki korxonalar oynasidan "Tijorat taklifi tayyorlash" orqali vazifa yarating.</td></tr>`;
      return;
    }

    tbody.innerHTML = tasks.map(t => {
      const staffMember = state.staffList.find(s => s.id === t.assigned_staff_id);
      const staffName = staffMember ? staffMember.name : (t.assigned_staff_id || "Biriktirilmagan");
      const statusClass = (t.status || "YANGI").toLowerCase();
      return `
        <tr>
          <td><strong>#${t.id}</strong></td>
          <td>
            <div style="font-weight: 600;">${escapeHtml(t.company_name || 'Korxona')}</div>
            <div style="font-size: 0.72rem; color: #64748b;">STIR: ${t.company_inn}</div>
          </td>
          <td>${escapeHtml(t.task_title || t.title || 'Mijoz bilan aloqa')}</td>
          <td><span class="badge badge-info">${escapeHtml(t.task_type || 'TAKTAK')}</span></td>
          <td>${escapeHtml(staffName)}</td>
          <td>
            <span class="status-badge-inline ${statusClass}">${escapeHtml(t.status || 'YANGI')}</span>
          </td>
          <td>${formatDate(t.created_at)}</td>
          <td>
            <select class="form-select" style="font-size: 0.78rem; padding: 0.2rem 0.5rem; width: auto;" onchange="window.handleTaskStatusChange(${t.id}, this.value)">
              <option value="YANGI" ${t.status === 'YANGI' ? 'selected' : ''}>YANGI</option>
              <option value="JARAYONDA" ${t.status === 'JARAYONDA' ? 'selected' : ''}>JARAYONDA</option>
              <option value="BAJARILDI" ${t.status === 'BAJARILDI' ? 'selected' : ''}>BAJARILDI</option>
            </select>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Failed to load admin tasks:", err);
  }
}

async function handleTaskStatusChange(taskId, newStatus) {
  try {
    const res = await fetch("/api/admin/tasks/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, status: newStatus })
    });
    const data = await res.json();
    if (data && data.success) {
      showToast(`Vazifa #${taskId} holati "${newStatus}" ga o'zgartirildi`, "success");
      await loadAdminTasks();
    } else {
      showToast("Vazifa holatini o'zgartirib bo'lmadi", "error");
    }
  } catch (err) {
    showToast("Xatolik yuz berdi: " + err.message, "error");
  }
}
window.handleTaskStatusChange = handleTaskStatusChange;

async function loadAdminSyncLogs() {
  try {
    const res = await fetch("/api/sync/logs");
    const data = await res.json();
    const logs = data.sync_logs || [];

    const tbody = document.getElementById("admin-sync-logs-body");
    if (!tbody) return;

    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:1.5rem;">Sinxronizatsiya loglari topilmadi</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td>#${l.id}</td>
        <td><strong>${escapeHtml(l.platform_id)}</strong></td>
        <td>${l.sync_start ? l.sync_start.substring(0, 19) : '—'}</td>
        <td>${l.sync_end ? l.sync_end.substring(0, 19) : '—'}</td>
        <td><span style="color: #059669; font-weight: 600;">+${l.records_added || 0}</span></td>
        <td>${l.records_updated || 0}</td>
        <td><span class="badge ${l.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${l.status}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load sync logs:", err);
  }
}

function renderAdminStaff() {
  const container = document.getElementById("admin-staff-cards");
  if (!container) return;

  const staff = state.staffList || [];
  if (staff.length === 0) {
    container.innerHTML = `<p class="text-muted">Xodimlar ro'yxati yuklanmoqda...</p>`;
    return;
  }

  container.innerHTML = staff.map(s => `
    <div class="admin-staff-card">
      <div class="staff-avatar">${s.name.charAt(0)}</div>
      <div class="staff-info">
        <h5>${escapeHtml(s.name)}</h5>
        <p><strong>Lavozim:</strong> ${escapeHtml(s.role)}</p>
        <p><strong>Email:</strong> ${escapeHtml(s.email || '—')}</p>
        <p><strong>Telefon:</strong> ${escapeHtml(s.phone || '+998 71 200-00-00')}</p>
      </div>
    </div>
  `).join("");
}

async function handlePasswordChange() {
  const oldPass = document.getElementById("input-old-password").value;
  const newPass = document.getElementById("input-new-password").value;
  const confirmPass = document.getElementById("input-confirm-password").value;
  const alertBox = document.getElementById("admin-pwd-alert");
  const btnSave = document.getElementById("btn-save-new-password");

  if (!oldPass || !newPass) {
    alertBox.style.display = "block";
    alertBox.style.background = "#fef2f2";
    alertBox.style.color = "#b91c1c";
    alertBox.textContent = "Barcha maydonlarni to'ldiring";
    return;
  }

  if (newPass !== confirmPass) {
    alertBox.style.display = "block";
    alertBox.style.background = "#fef2f2";
    alertBox.style.color = "#b91c1c";
    alertBox.textContent = "Yangi parol tasdig'i bilan mos kelmadi!";
    return;
  }

  if (newPass.length < 6) {
    alertBox.style.display = "block";
    alertBox.style.background = "#fef2f2";
    alertBox.style.color = "#b91c1c";
    alertBox.textContent = "Parol kamida 6 ta belgidan iborat bo'lishi kerak";
    return;
  }

  btnSave.disabled = true;
  btnSave.textContent = "Saqlanmoqda...";

  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: oldPass, new_password: newPass })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      alertBox.style.display = "block";
      alertBox.style.background = "#ecfdf5";
      alertBox.style.color = "#065f46";
      alertBox.textContent = "✅ " + (data.message || "Parol muvaffaqiyatli o'zgartirildi!");
      document.getElementById("form-change-password").reset();
      showToast("Administrator paroli muvaffaqiyatli yangilandi!", "success");
    } else {
      alertBox.style.display = "block";
      alertBox.style.background = "#fef2f2";
      alertBox.style.color = "#b91c1c";
      alertBox.textContent = data.error || data.message || "Parolni o'zgartirishda xatolik";
    }
  } catch (err) {
    alertBox.style.display = "block";
    alertBox.style.background = "#fef2f2";
    alertBox.style.color = "#b91c1c";
    alertBox.textContent = "Xatolik: " + err.message;
  } finally {
    btnSave.disabled = false;
    btnSave.textContent = "💾 Parolni Saqlash va Yangilash";
  }
}

// ==========================================================================
// Search & Filter Execution
// ==========================================================================
async function performSearch() {
  setLoading(true);

  const payload = {
    query: state.query,
    view_mode: state.view_mode,
    platforms: state.platforms,
    date_field: state.date_field,
    quick_period: state.quick_period !== "all" ? state.quick_period : null,
    date_from: state.date_from || null,
    date_to: state.date_to || null,
    include_missing_dates: state.include_missing_dates,
    official_status: state.official_status || null,
    has_contract: state.has_contract ? true : null,
    expiry_known: state.expiry_known ? true : null,
    min_price: state.min_price ? parseFloat(state.min_price) : null,
    max_price: state.max_price ? parseFloat(state.max_price) : null,
    region: state.region || null,
    assigned_staff_id: state.assigned_staff_id || null,
    crm_status: state.crm_status || null,
    limit: state.limit,
    offset: state.offset
  };

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    setLoading(false);

    if (data.error) {
      showEmptyState("Xatolik yuz berdi", data.message || "Qidiruvni amalga oshirib bo'lmadi");
      return;
    }

    state.total_count = data.total_count || 0;
    updateKpisAndCounters(data.stats, data.total_count);
    renderActiveFilterTags();

    if (state.total_count === 0) {
      handleEmptyStateScenario();
      return;
    }

    hideEmptyState();

    if (state.view_mode === "lots") {
      renderLotsTable(data.items);
    } else if (state.view_mode === "companies") {
      renderCompaniesTable(data.items);
    } else {
      renderContractsTable(data.items);
    }

    updatePaginationInfo();

  } catch (err) {
    setLoading(false);
    showEmptyState("Aloqa xatosi", "Server bilan ulanishda muammo bo'ldi: " + err.message);
  }
}

function handleEmptyStateScenario() {
  hideAllTables();
  if (state.date_from && state.date_from < "2024-09-01") {
    // Empty state scenario 2: Out of loaded range
    showEmptyState(
      "Bu davr hali yuklanmagan", 
      "Siz tanlagan sana oralig'i (2024-yil 1-sentabrgacha) manbalar arxiviga kirmaydi. Tizim bazasi 2024-09-01 dan boshlab shakllantirilgan."
    );
  } else {
    // Empty state scenario 1: Normal no match
    showEmptyState(
      "Mos yozuv topilmadi", 
      "Kiritilgan kalit so‘z yoki tanlangan filtrlar bo‘yicha natija chiqmadi. Qidiruv so‘zini o‘zgartiring yoki filtrlarni kengaytiring."
    );
  }
}

// ==========================================================================
// Rendering Views (Lots, Companies, Contracts)
// ==========================================================================
function renderLotsTable(items) {
  const tbody = document.getElementById("table-lots-body");
  tbody.innerHTML = "";

  items.forEach(lot => {
    const tr = document.createElement("tr");

    // Match badges
    let matchBadgesHtml = "";
    if (lot.match_tags && lot.match_tags.length > 0) {
      lot.match_tags.forEach(tag => {
        const badgeClass = tag.type === "PRODUCT_MATCH" ? "badge-product-match" : "badge-text-match";
        matchBadgesHtml += `<div class="badge-match ${badgeClass}">🎯 ${escapeHtml(tag.label)}</div>`;
      });
    }

    const platformBadge = `<span class="pill-btn">${escapeHtml(lot.platform_name || lot.platform_id)}</span>`;
    const formattedPrice = formatCurrency(lot.final_price || lot.start_price, lot.currency);
    const dateStr = formatDate(lot.announcement_date || lot.contract_date);
    const buyerName = lot.buyer_name ? escapeHtml(lot.buyer_name) : "Buyurtmachi ko'rsatilmagan";
    const buyerInn = lot.buyer_inn ? `<span class="text-sm font-medium" style="color: var(--primary);">STIR: ${lot.buyer_inn}</span>` : "";

    tr.innerHTML = `
      <td>
        <div class="font-medium">${escapeHtml(lot.lot_number || "—")}</div>
        ${lot.source_url ? `<a href="${escapeHtml(lot.source_url)}" target="_blank" class="text-sm btn-link">Platformada ochish ↗</a>` : ""}
      </td>
      <td>
        <div class="font-medium" style="font-size: 0.9rem;">${lot.highlighted_title || escapeHtml(lot.title || "—")}</div>
        ${matchBadgesHtml}
        ${lot.highlighted_description ? `<div class="text-sm text-muted mt-1">${lot.highlighted_description}</div>` : ""}
      </td>
      <td>${platformBadge}</td>
      <td>
        <div>${buyerName}</div>
        <div>${buyerInn}</div>
      </td>
      <td>
        <div class="text-sm">${dateStr}</div>
        ${lot.license_end_date ? `<div class="text-sm" style="color: #ea580c;">Tugash: ${formatDate(lot.license_end_date)}</div>` : ""}
      </td>
      <td style="text-align: right;">
        <div class="font-medium" style="color: #065f46;">${formattedPrice}</div>
      </td>
      <td>
        <span class="proof-badge ${lot.has_contract ? 'proof-verified' : 'proof-announced'}">
          ${lot.has_contract ? 'Shartnomali' : escapeHtml(lot.official_status || 'Yangi')}
        </span>
      </td>
      <td>
        <div style="display: flex; flex-direction: column; gap: 0.3rem;">
          <button class="btn btn-sm btn-gemini-ai" style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color: white; border: none; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 4px; box-shadow: 0 2px 6px rgba(124, 58, 237, 0.3);" onclick="openGeminiModal('${lot.id || lot.lot_number}')">
            ✨ Gemini AI
          </button>
          ${lot.buyer_inn ? `<button class="btn btn-outline btn-sm" onclick="openTimelineModal('${lot.buyer_inn}')">Xarid tarixi</button>` : ""}
          ${lot.contract_url ? `<a href="${escapeHtml(lot.contract_url)}" target="_blank" class="btn btn-secondary btn-sm">Shartnoma ↗</a>` : ""}
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCompaniesTable(items) {
  const tbody = document.getElementById("table-companies-body");
  tbody.innerHTML = "";

  items.forEach(comp => {
    const tr = document.createElement("tr");

    const isVerified = comp.proof_status === "VERIFIED_BUYER" || comp.verified_contracts_count > 0;
    const proofBadge = isVerified 
      ? `<span class="proof-badge proof-verified">Tasdiqlangan Xaridor</span>`
      : `<span class="proof-badge proof-announced">Xarid e'lon qilgan</span>`;

    const nearestExpiry = comp.nearest_license_expiry 
      ? `<span style="color: #ea580c; font-weight: 600;">${formatDate(comp.nearest_license_expiry)}</span>` 
      : `<span class="text-muted">Noma'lum</span>`;

    tr.innerHTML = `
      <td><span class="font-medium" style="color: var(--primary);">${escapeHtml(comp.inn)}</span></td>
      <td>
        <div class="font-medium">${escapeHtml(comp.name || "Nomsiz korxona")}</div>
        <div class="text-sm text-muted">${escapeHtml(comp.phone || comp.email || "")}</div>
        <div class="mt-1">${proofBadge}</div>
      </td>
      <td>${escapeHtml(comp.region || "—")}</td>
      <td style="text-align: center;"><span class="font-medium">${comp.distinct_lots_count || 1}</span></td>
      <td style="text-align: center;">
        <span class="font-medium" style="color: #065f46;">${comp.verified_contracts_count || 0}</span>
      </td>
      <td>${formatDate(comp.latest_purchase_date)}</td>
      <td>${nearestExpiry}</td>
      <td>
        <div class="font-medium text-sm">${escapeHtml(comp.assigned_staff_name || "Biriktirilmagan")}</div>
        <div class="text-sm text-muted">${escapeHtml(comp.crm_status || "Yangi")}</div>
      </td>
      <td>
        <div style="display: flex; flex-direction: column; gap: 0.3rem;">
          <button class="btn btn-outline btn-sm" onclick="openTimelineModal('${comp.inn}')">Tarixni ko'rish</button>
          <button class="btn btn-primary btn-sm" onclick="openProposalModal('${comp.inn}')">Taklif tuzish</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderContractsTable(items) {
  const tbody = document.getElementById("table-contracts-body");
  tbody.innerHTML = "";

  items.forEach(c => {
    const tr = document.createElement("tr");

    const formattedUnit = formatCurrency(c.unit_price, c.currency);
    const formattedTotal = formatCurrency(c.total_price || c.contract_amount, c.currency);

    tr.innerHTML = `
      <td>
        <div class="font-medium">${escapeHtml(c.contract_number || c.lot_number || "—")}</div>
        <div class="text-sm text-muted">${escapeHtml(c.platform_name || c.platform_id || "")}</div>
      </td>
      <td>
        <div class="font-medium">${escapeHtml(c.product_name || "—")}</div>
        ${c.is_purchased_product ? `<span class="badge-match badge-product-match">Xarid qilingan litsenziya</span>` : ""}
      </td>
      <td>${escapeHtml(c.brand || c.product_family || "—")}</td>
      <td style="text-align: center;">${c.quantity || 1} ${escapeHtml(c.unit || "dona")}</td>
      <td style="text-align: right;">${formattedUnit}</td>
      <td style="text-align: right;"><span class="font-medium" style="color: #065f46;">${formattedTotal}</span></td>
      <td>
        <div>${escapeHtml(c.buyer_name || "—")}</div>
        <div class="text-sm text-muted">STIR: ${escapeHtml(c.buyer_inn || "—")}</div>
      </td>
      <td>${formatDate(c.contract_date)}</td>
      <td>
        ${c.contract_url ? `<a href="${escapeHtml(c.contract_url)}" target="_blank" class="btn btn-outline btn-sm">Ochish ↗</a>` : "—"}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ==========================================================================
// MODAL 1: Company Timeline Modal (17.F)
// ==========================================================================
async function openTimelineModal(inn) {
  state.currentCompanyInn = inn;
  modalTimeline.style.display = "flex";

  const listContainer = document.getElementById("timeline-events-list");
  const tasksContainer = document.getElementById("timeline-tasks-list");
  listContainer.innerHTML = `<div class="spinner"></div>`;
  tasksContainer.innerHTML = "";

  try {
    const res = await fetch(`/api/companies/${inn}`);
    const data = await res.json();

    if (!data.found) {
      showToast("Korxona topilmadi", "error");
      modalTimeline.style.display = "none";
      return;
    }

    const comp = data.company;
    document.getElementById("timeline-company-name").textContent = comp.name || "Nomsiz korxona";
    document.getElementById("timeline-company-inn").textContent = `STIR: ${comp.inn}`;
    document.getElementById("timeline-company-region").textContent = `Hudud: ${comp.region || "Ko'rsatilmagan"}`;
    document.getElementById("timeline-phone").textContent = comp.phone || "Mavjud emas";
    document.getElementById("timeline-email").textContent = comp.email || "Mavjud emas";
    document.getElementById("timeline-address").textContent = comp.legal_address || "Mavjud emas";

    // Proof Badge
    const proofBadge = document.getElementById("timeline-proof-badge");
    if (comp.calculated_proof_status === "VERIFIED_BUYER") {
      proofBadge.textContent = "Tasdiqlangan Xaridor (Shartnoma mavjud)";
      proofBadge.className = "proof-badge proof-verified";
    } else {
      proofBadge.textContent = "Xarid e’lon qilgan (Shartnoma dalilisiz)";
      proofBadge.className = "proof-badge proof-announced";
    }

    // Assign staff select
    const assignSelect = document.getElementById("timeline-assign-select");
    assignSelect.value = comp.assigned_staff_id || "";

    // Render Timeline Events
    listContainer.innerHTML = "";
    if (!data.timeline || data.timeline.length === 0) {
      listContainer.innerHTML = `<div class="text-muted p-3">Ushbu korxona bo'yicha xaridlar topilmadi.</div>`;
    } else {
      data.timeline.forEach(event => {
        const evDiv = document.createElement("div");
        evDiv.className = `timeline-event ${event.is_verified_contract ? 'contracted' : ''}`;

        let itemsHtml = "";
        if (event.items && event.items.length > 0) {
          itemsHtml = `
            <div class="mt-2 text-sm">
              <strong>Mahsulotlar:</strong>
              <ul style="margin-left: 1.2rem; margin-top: 0.2rem;">
                ${event.items.map(it => `<li>${escapeHtml(it.product_name || "")} (${it.quantity || 1} ${escapeHtml(it.unit || "dona")}) — ${formatCurrency(it.total_price || it.unit_price, event.currency)}</li>`).join("")}
              </ul>
            </div>
          `;
        }

        evDiv.innerHTML = `
          <div class="timeline-dot"></div>
          <div class="timeline-card">
            <div class="timeline-header">
              <span class="timeline-date">📅 ${formatDate(event.contract_date || event.announcement_date)}</span>
              <span class="proof-badge ${event.is_verified_contract ? 'proof-verified' : 'proof-announced'}">
                ${escapeHtml(event.proof_status)}
              </span>
            </div>
            <div class="timeline-title">${escapeHtml(event.title || "Xarid loti")}</div>
            <div class="timeline-meta">
              <span><strong>Platforma:</strong> ${escapeHtml(event.platform_name || "Davlat portali")}</span>
              <span><strong>Summa:</strong> ${formatCurrency(event.final_price, event.currency)}</span>
              <span><strong>Yetkazib beruvchi:</strong> ${escapeHtml(event.supplier_name)}</span>
              ${event.license_end_date ? `<span style="color: #ea580c;"><strong>Litsenziya muddati:</strong> ${formatDate(event.license_end_date)}</span>` : ""}
            </div>
            ${itemsHtml}
            <div class="mt-2" style="display: flex; gap: 0.5rem;">
              ${event.source_url ? `<a href="${escapeHtml(event.source_url)}" target="_blank" class="btn btn-outline btn-sm">Lot havolasi ↗</a>` : ""}
              ${event.contract_url ? `<a href="${escapeHtml(event.contract_url)}" target="_blank" class="btn btn-secondary btn-sm">Shartnoma havolasi ↗</a>` : ""}
            </div>
          </div>
        `;
        listContainer.appendChild(evDiv);
      });
    }

    // Render Tasks
    renderTasksList(data.tasks);

  } catch (err) {
    showToast("Ma'lumotlarni yuklashda xatolik", "error");
  }
}

function renderTasksList(tasks) {
  const container = document.getElementById("timeline-tasks-list");
  container.innerHTML = "";
  if (!tasks || tasks.length === 0) {
    container.innerHTML = `<div class="text-muted text-sm">Hozircha biriktirilgan vazifalar yo'q.</div>`;
    return;
  }

  tasks.forEach(t => {
    const item = document.createElement("div");
    item.className = "task-item";
    item.innerHTML = `
      <div>
        <div class="font-medium">${escapeHtml(t.task_title)}</div>
        <div class="text-sm text-muted">Mas'ul: ${escapeHtml(t.assigned_staff_name || "—")} • ${formatDate(t.created_at)}</div>
      </div>
      <div>
        <span class="proof-badge proof-verified">${escapeHtml(t.status || "Yangi")}</span>
      </div>
    `;
    container.appendChild(item);
  });
}

// ==========================================================================
// MODAL 2: Grounded Proposal Modal (17.G)
// ==========================================================================
async function openProposalModal(inn) {
  state.currentCompanyInn = inn;
  modalProposal.style.display = "flex";

  const productsBox = document.getElementById("proposal-observed-products");
  const subjectInput = document.getElementById("proposal-subject-input");
  const bodyText = document.getElementById("proposal-body-text");
  const checkConfirm = document.getElementById("check-confirm-pricing");
  const btnConfirm = document.getElementById("btn-confirm-proposal");

  checkConfirm.checked = false;
  btnConfirm.disabled = true;
  productsBox.innerHTML = `<div class="spinner"></div>`;

  try {
    const res = await fetch(`/api/companies/${inn}/proposal`);
    const draft = await res.json();
    state.currentProposalDraft = draft;

    document.getElementById("proposal-company-header").textContent = `${draft.company_name} (STIR: ${draft.inn})`;
    subjectInput.value = draft.proposal_subject || "";

    // Render observed products
    productsBox.innerHTML = "";
    if (!draft.observed_products || draft.observed_products.length === 0) {
      productsBox.innerHTML = `<div class="text-sm text-muted">Ushbu korxonada aniqlangan xarid faktlari mavjud emas.</div>`;
    } else {
      draft.observed_products.forEach(p => {
        const pItem = document.createElement("div");
        pItem.className = "observed-prod-item";
        pItem.innerHTML = `
          <span><strong>${escapeHtml(p.product)}</strong> (${escapeHtml(p.brand || "IT")})</span>
          <span class="text-muted">Oxirgi xarid: ${formatDate(p.last_purchase_date)} • Tugash: ${formatDate(p.license_end_date)}</span>
        `;
        productsBox.appendChild(pItem);
      });
    }

    // Grounded letter body
    const prodsListText = (draft.observed_products || []).map(p => `• ${p.product} (Oxirgi xarid sanasi: ${p.last_purchase_date})`).join("\n");
    
    bodyText.value = 
`Hurmatli ${draft.company_name} rahbariyati va IT mutaxassislari!

Bizning tahliliy tizimimiz ma'lumotlariga ko'ra, korxonangiz davlat xaridlari platformasi orqali quyidagi dasturiy ta'minot litsenziyalarini xarid qilgan:
${prodsListText}

Litsenziya muddatining tugashi munosabati bilan, dasturiy ta'minotning uzluksiz ishlashi va xavfsizlik yangilanishlarini ta'minlash maqsadida SOFTY jamoasi rasmiy yangilash hamda texnik qo'llab-quvvatlash bo'yicha maxsus shartlarni taklif etadi.

Amaldagi rasmiy litsenziya narxlari distribyutorning joriy kursiga asosan hisoblab taqdim etiladi.

Hurmat bilan,
SOFTY Platforma savdo bo'limi`;

  } catch (err) {
    showToast("Taklifni generatsiya qilishda xatolik", "error");
  }
}

async function confirmAndSaveProposal() {
  if (!state.currentCompanyInn) return;

  const subject = document.getElementById("proposal-subject-input").value;
  const text = document.getElementById("proposal-body-text").value;

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyInn}/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_title: `Tijorat taklifi: ${subject}`,
        task_type: "TIJORAT_TAKTAK",
        assigned_staff_id: state.assigned_staff_id || "usmon",
        proposal_summary: text
      })
    });

    const data = await res.json();
    if (data.success) {
      showToast("Tijorat taklifi tasdiqlandi va vazifa yaratildi!", "success");
      modalProposal.style.display = "none";
      performSearch();
    }
  } catch (err) {
    showToast("Vazifani saqlashda xatolik", "error");
  }
}

// ==========================================================================
// MODAL 3: Sources & Platform Health (17.A, 17.H)
// ==========================================================================
async function openSourcesModal() {
  modalSources.style.display = "flex";
  const container = document.getElementById("sources-cards-container");
  container.innerHTML = `<div class="spinner"></div>`;

  try {
    const res = await fetch("/api/sources");
    const data = await res.json();

    container.innerHTML = "";
    data.sources.forEach(src => {
      const card = document.createElement("div");
      card.className = "source-card";

      const isFallback = src.is_fallback || src.adapter_status === "UNIMPLEMENTED";
      const statusBadge = isFallback
        ? `<span class="proof-badge proof-announced">Adapter ishlab chiqilishi kerak</span>`
        : `<span class="proof-badge proof-verified">Faol / Ulangan</span>`;

      card.innerHTML = `
        <div class="source-card-header">
          <span class="source-title">${escapeHtml(src.name)}</span>
          ${statusBadge}
        </div>
        <div>
          <a href="${escapeHtml(src.base_url)}" target="_blank" class="source-domain">${escapeHtml(src.base_url)} ↗</a>
        </div>
        <div class="source-operator"><strong>Operator:</strong> ${escapeHtml(src.operator || "—")}</div>
        <div class="source-stats">
          <span><strong>Yuklangan davr:</strong> ${escapeHtml(src.loaded_range_start || "—")} dan ${escapeHtml(src.loaded_range_end || "hozirgacha")}</span>
          <span><strong>Bazadagi lotlar:</strong> ${src.lot_count || 0} ta</span>
        </div>
        <div class="mt-2" style="display: flex; justify-content: space-between; align-items: center;">
          <span class="text-sm text-muted">${escapeHtml(src.adapter_description || "")}</span>
          <button class="btn btn-outline btn-sm" onclick="syncSource('${src.id}')">Sinxronlash</button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    showToast("Manbalar holatini yuklashda xatolik", "error");
  }
}

async function syncSource(sourceId) {
  showToast(`Platforma ${sourceId} sinxronlanmoqda...`, "info");
  try {
    const res = await fetch(`/api/sources/${sourceId}/sync`, { method: "POST" });
    const data = await res.json();
    if (data.status === "UNIMPLEMENTED") {
      showToast(data.message, "warning");
    } else {
      showToast(data.message || "Sinxronlash muvaffaqiyatli yakunlandi", "success");
    }
  } catch (err) {
    showToast("Sinxronlashda xatolik", "error");
  }
}

// ==========================================================================
// MODAL 4: Saved Searches (17.E)
// ==========================================================================
async function openSavedSearchesModal() {
  modalSavedSearches.style.display = "flex";
  loadSavedSearchesList();
}

async function loadSavedSearchesList() {
  const container = document.getElementById("saved-searches-list");
  container.innerHTML = `<div class="spinner"></div>`;

  try {
    const res = await fetch("/api/saved-searches");
    const data = await res.json();

    container.innerHTML = "";
    if (!data.saved_searches || data.saved_searches.length === 0) {
      container.innerHTML = `<div class="text-sm text-muted p-2">Saqlangan qidiruvlar mavjud emas.</div>`;
      return;
    }

    data.saved_searches.forEach(item => {
      const div = document.createElement("div");
      div.className = "task-item";
      div.innerHTML = `
        <div>
          <div class="font-medium">${escapeHtml(item.title)}</div>
          <div class="text-sm text-muted">Kalit so'z: "${escapeHtml(item.query_text || "Bo'sh")}" • ${formatDate(item.created_at)}</div>
        </div>
        <button class="btn btn-outline btn-sm" onclick='applySavedSearch(${JSON.stringify(item)})'>Yuklash</button>
      `;
      container.appendChild(div);
    });
  } catch (err) {
    showToast("Saqlangan qidiruvlarni yuklashda xatolik", "error");
  }
}

async function saveCurrentSearch() {
  const titleInput = document.getElementById("saved-search-title-input");
  const title = titleInput.value.trim() || `Qidiruv (${state.query || "Barcha"})`;

  try {
    const res = await fetch("/api/saved-searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        query_text: state.query,
        filter_params: {
          platforms: state.platforms,
          date_field: state.date_field,
          quick_period: state.quick_period,
          date_from: state.date_from,
          date_to: state.date_to,
          region: state.region,
          official_status: state.official_status
        }
      })
    });

    const data = await res.json();
    if (data.success) {
      showToast("Qidiruv saqlandi!", "success");
      titleInput.value = "";
      loadSavedSearchesList();
    }
  } catch (err) {
    showToast("Saqlashda xatolik", "error");
  }
}

function applySavedSearch(item) {
  modalSavedSearches.style.display = "none";
  state.query = item.query_text || "";
  searchInput.value = state.query;
  btnClearSearch.style.display = state.query ? "block" : "none";

  if (item.filter_params) {
    const fp = item.filter_params;
    if (fp.platforms) state.platforms = fp.platforms;
    if (fp.date_field) state.date_field = fp.date_field;
    if (fp.quick_period) state.quick_period = fp.quick_period;
    if (fp.date_from) state.date_from = fp.date_from;
    if (fp.date_to) state.date_to = fp.date_to;
    if (fp.region) state.region = fp.region;
    if (fp.official_status) state.official_status = fp.official_status;
  }

  syncFormToState();
  syncStateToUrl();
  performSearch();
  showToast(`"${item.title}" qidiruvi yuklandi`, "info");
}

// ==========================================================================
// CRM Actions: Staff Assignment & Bitrix24
// ==========================================================================
async function assignStaffMember(inn, staffId) {
  try {
    const res = await fetch(`/api/companies/${inn}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ staff_id: staffId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      performSearch();
    }
  } catch (err) {
    showToast("Xodim biriktirishda xatolik", "error");
  }
}

async function saveNewTask(inn, title) {
  try {
    const res = await fetch(`/api/companies/${inn}/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_title: title,
        task_type: "TAKTAK_TAYYORLASH",
        assigned_staff_id: state.assigned_staff_id || "usmon"
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Vazifa muvaffaqiyatli saqlandi!", "success");
      openTimelineModal(inn);
      performSearch();
    }
  } catch (err) {
    showToast("Vazifani saqlashda xatolik", "error");
  }
}

async function syncToBitrix(inn) {
  showToast("Bitrix24 ga yuborilmoqda...", "info");
  try {
    const res = await fetch(`/api/companies/${inn}/bitrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "Davlat xaridlari tahlili asosida litsenziya uzaytirish bitimi",
        amount: 0.0
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      openTimelineModal(inn);
      performSearch();
    }
  } catch (err) {
    showToast("Bitrix24 ga yuborishda xatolik", "error");
  }
}

// ==========================================================================
// Export Excel (.xlsx) & PDF (.pdf)
// ==========================================================================
function triggerExport(format = "xlsx") {
  const params = new URLSearchParams();
  params.set("format", format);
  params.set("view_mode", state.view_mode);
  if (state.query) params.set("query", state.query);
  if (state.platforms && state.platforms.length > 0) params.set("platforms", state.platforms.join(","));
  params.set("date_field", state.date_field);
  if (state.quick_period && state.quick_period !== "all") params.set("quick_period", state.quick_period);
  if (state.date_from) params.set("date_from", state.date_from);
  if (state.date_to) params.set("date_to", state.date_to);
  if (state.include_missing_dates) params.set("include_missing_dates", "true");
  if (state.official_status) params.set("official_status", state.official_status);
  if (state.has_contract) params.set("has_contract", "true");
  if (state.expiry_known) params.set("expiry_known", "true");
  if (state.min_price) params.set("min_price", state.min_price);
  if (state.max_price) params.set("max_price", state.max_price);
  if (state.region) params.set("region", state.region);
  if (state.assigned_staff_id) params.set("assigned_staff_id", state.assigned_staff_id);
  if (state.crm_status) params.set("crm_status", state.crm_status);

  showToast(format === "pdf" ? "PDF hisobot tayyorlanmoqda va yuklanmoqda..." : "Excel (.xlsx) jadval yuklanmoqda...", "info");
  window.location.href = `/api/export?${params.toString()}`;
}

// ==========================================================================
// Helpers: State, Form & URL Synchronization
// ==========================================================================
function readFormIntoState() {
  state.platforms = Array.from(document.querySelectorAll('input[name="platform"]:checked')).map(cb => cb.value);
  state.date_field = filterDateField.value;
  state.date_from = filterDateFrom.value;
  state.date_to = filterDateTo.value;
  state.include_missing_dates = filterIncludeMissingDates.checked;
  state.official_status = filterOfficialStatus.value;
  state.has_contract = filterHasContract.checked;
  state.expiry_known = filterExpiryKnown.checked;
  state.min_price = filterMinPrice.value;
  state.max_price = filterMaxPrice.value;
  state.region = filterRegion.value;
  state.assigned_staff_id = filterAssignedStaff.value;
  state.crm_status = filterCrmStatus.value;
}

function syncFormToState() {
  searchInput.value = state.query;
  btnClearSearch.style.display = state.query ? "block" : "none";

  document.querySelectorAll('input[name="platform"]').forEach(cb => {
    cb.checked = state.platforms.includes(cb.value);
  });

  filterDateField.value = state.date_field;
  filterDateFrom.value = state.date_from;
  filterDateTo.value = state.date_to;
  filterIncludeMissingDates.checked = state.include_missing_dates;
  filterOfficialStatus.value = state.official_status;
  filterHasContract.checked = state.has_contract;
  filterExpiryKnown.checked = state.expiry_known;
  filterMinPrice.value = state.min_price;
  filterMaxPrice.value = state.max_price;
  filterRegion.value = state.region;
  filterAssignedStaff.value = state.assigned_staff_id;
  filterCrmStatus.value = state.crm_status;

  // Active pill for quick period
  document.querySelectorAll(".pill-btn").forEach(btn => {
    if (btn.getAttribute("data-period") === state.quick_period) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Active tab
  document.querySelectorAll(".tab-btn").forEach(btn => {
    if (btn.getAttribute("data-tab") === state.view_mode) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  document.querySelectorAll(".view-pane").forEach(pane => pane.classList.remove("active"));
  const activePane = document.getElementById(`pane-${state.view_mode}`);
  if (activePane) activePane.classList.add("active");
}

function readStateFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("q")) state.query = urlParams.get("q");
  if (urlParams.has("tab")) state.view_mode = urlParams.get("tab");
  if (urlParams.has("platforms")) state.platforms = urlParams.get("platforms").split(",");
  if (urlParams.has("df")) state.date_field = urlParams.get("df");
  if (urlParams.has("period")) state.quick_period = urlParams.get("period");
  if (urlParams.has("from")) state.date_from = urlParams.get("from");
  if (urlParams.has("to")) state.date_to = urlParams.get("to");
  if (urlParams.has("status")) state.official_status = urlParams.get("status");
  if (urlParams.has("contract")) state.has_contract = urlParams.get("contract") === "1";
  if (urlParams.has("region")) state.region = urlParams.get("region");
  if (urlParams.has("staff")) state.assigned_staff_id = urlParams.get("staff");
  if (urlParams.has("crm")) state.crm_status = urlParams.get("crm");
}

function syncStateToUrl() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.view_mode !== "lots") params.set("tab", state.view_mode);
  if (state.platforms.length < 4) params.set("platforms", state.platforms.join(","));
  if (state.date_field !== "announcement_date") params.set("df", state.date_field);
  if (state.quick_period !== "all") params.set("period", state.quick_period);
  if (state.date_from) params.set("from", state.date_from);
  if (state.date_to) params.set("to", state.date_to);
  if (state.official_status) params.set("status", state.official_status);
  if (state.has_contract) params.set("contract", "1");
  if (state.region) params.set("region", state.region);
  if (state.assigned_staff_id) params.set("staff", state.assigned_staff_id);
  if (state.crm_status) params.set("crm", state.crm_status);

  const newUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.pushState({}, "", newUrl);
}

function resetAllFilters() {
  state.query = "";
  state.platforms = ["xt_xarid", "uzex", "ebirja", "cooperation"];
  state.date_field = "announcement_date";
  state.quick_period = "all";
  state.date_from = "";
  state.date_to = "";
  state.include_missing_dates = false;
  state.official_status = "";
  state.has_contract = false;
  state.expiry_known = false;
  state.min_price = "";
  state.max_price = "";
  state.region = "";
  state.assigned_staff_id = "";
  state.crm_status = "";
  state.offset = 0;
  state.page = 1;

  syncFormToState();
  syncStateToUrl();
  performSearch();
}

function renderActiveFilterTags() {
  const container = document.getElementById("active-filter-tags");
  const bar = document.getElementById("active-filters-bar");
  container.innerHTML = "";

  const tags = [];
  if (state.query) tags.push({ label: `Kalit: "${state.query}"`, reset: () => { state.query = ""; } });
  if (state.platforms.length < 4) tags.push({ label: `Platformalar: ${state.platforms.length} ta`, reset: () => { state.platforms = ["xt_xarid", "uzex", "ebirja", "cooperation"]; } });
  if (state.quick_period !== "all") tags.push({ label: `Davr: ${state.quick_period}`, reset: () => { state.quick_period = "all"; } });
  if (state.date_from || state.date_to) tags.push({ label: `Sana: ${state.date_from || "..."} — ${state.date_to || "..."}`, reset: () => { state.date_from = ""; state.date_to = ""; } });
  if (state.official_status) tags.push({ label: `Holat: ${state.official_status}`, reset: () => { state.official_status = ""; } });
  if (state.has_contract) tags.push({ label: `Faqat shartnomalar`, reset: () => { state.has_contract = false; } });
  if (state.region) tags.push({ label: `Hudud: ${state.region}`, reset: () => { state.region = ""; } });
  if (state.assigned_staff_id) tags.push({ label: `Xodim: ${state.assigned_staff_id}`, reset: () => { state.assigned_staff_id = ""; } });

  if (tags.length === 0) {
    bar.style.display = "none";
    return;
  }

  bar.style.display = "flex";
  tags.forEach(t => {
    const tagEl = document.createElement("span");
    tagEl.className = "active-tag";
    tagEl.innerHTML = `${escapeHtml(t.label)} <span class="active-tag-remove">✕</span>`;
    tagEl.querySelector(".active-tag-remove").addEventListener("click", () => {
      t.reset();
      syncFormToState();
      syncStateToUrl();
      performSearch();
    });
    container.appendChild(tagEl);
  });
}

function updateKpisAndCounters(stats, total) {
  document.getElementById("kpi-total-records").textContent = total.toLocaleString();
  document.getElementById("kpi-total-amount").textContent = stats ? formatCurrency(stats.total_amount, "UZS") : "0 so'm";
  document.getElementById("kpi-unique-buyers").textContent = stats ? stats.unique_buyers_count.toLocaleString() : "0";
  document.getElementById("kpi-verified-contracts").textContent = stats ? stats.contracts_count.toLocaleString() : "0";

  // Tab counter badges
  if (state.view_mode === "lots") {
    document.getElementById("tab-count-lots").textContent = total;
  } else if (state.view_mode === "companies") {
    document.getElementById("tab-count-companies").textContent = total;
  } else {
    document.getElementById("tab-count-contracts").textContent = total;
  }
}

function updatePaginationInfo() {
  const fromNum = state.total_count === 0 ? 0 : state.offset + 1;
  const toNum = Math.min(state.offset + state.limit, state.total_count);
  document.getElementById("pagination-info").textContent = `Ko'rsatilmoqda: ${fromNum} dan ${toNum} gacha (Jami: ${state.total_count})`;
  document.getElementById("current-page-num").textContent = state.page;

  document.getElementById("btn-prev-page").disabled = state.offset === 0;
  document.getElementById("btn-next-page").disabled = toNum >= state.total_count;
}

function setLoading(isLoading) {
  document.getElementById("loading-spinner").style.display = isLoading ? "block" : "none";
}

function showEmptyState(title, desc) {
  hideAllTables();
  const card = document.getElementById("empty-state-container");
  card.style.display = "block";
  document.getElementById("empty-state-title").textContent = title;
  document.getElementById("empty-state-desc").textContent = desc;
}

function hideEmptyState() {
  document.getElementById("empty-state-container").style.display = "none";
}

function hideAllTables() {
  document.getElementById("table-lots-body").innerHTML = "";
  document.getElementById("table-companies-body").innerHTML = "";
  document.getElementById("table-contracts-body").innerHTML = "";
}

async function loadStaffList() {
  try {
    const res = await fetch("/api/staff");
    const data = await res.json();
    state.staffList = data.staff || [];

    const assignSelect = document.getElementById("timeline-assign-select");
    assignSelect.innerHTML = `<option value="">Biriktirilmagan</option>`;
    state.staffList.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = `${s.name} (${s.role})`;
      assignSelect.appendChild(opt);
    });
  } catch (e) {
    console.error("Staff list could not be loaded", e);
  }
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

function formatCurrency(amount, currency = "UZS") {
  if (amount === null || amount === undefined || isNaN(amount)) return "0 so'm";
  return new Intl.NumberFormat("uz-UZ").format(Math.round(amount)) + " so'm";
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  return dateStr.substring(0, 10);
}

function escapeHtml(text) {
  if (!text) return "";
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.toString().replace(/[&<>"']/g, m => map[m]);
}
