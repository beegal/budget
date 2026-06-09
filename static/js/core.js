function setSaveState(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("save-error", isError);
}

function resetSaveState() {
  setSaveState(document.querySelector("[data-save-state]"), "");
}

function budgetConfig() {
  return window.BUDGET_CONFIG || {};
}

function tr(key, values = {}) {
  let text = (window.BUDGET_I18N || {})[key] || key;
  for (const [name, value] of Object.entries(values)) {
    text = text.split(`{${name}}`).join(String(value));
  }
  return text;
}

function displayLocale() {
  return budgetConfig().locale || navigator.language || "fr-FR";
}

function numberDecimals(defaultValue = 2) {
  const value = Number(budgetConfig().numberDecimals);
  return Number.isFinite(value) ? value : defaultValue;
}

function numberSeparators() {
  const parts = new Intl.NumberFormat(displayLocale()).formatToParts(12345.6);
  return {
    group: parts.find((part) => part.type === "group")?.value || " ",
    decimal: parts.find((part) => part.type === "decimal")?.value || ",",
  };
}

function setLongLivedCookie(name, value) {
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; Max-Age=315360000; Path=/; SameSite=Lax`;
}

function getCookie(name) {
  const encodedName = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(encodedName))
    ?.slice(encodedName.length) || "";
}

function persistInitialLanguage() {
  if (getCookie("budget_language")) return;
  const language = budgetConfig().language;
  if (language) setLongLivedCookie("budget_language", language);
}

function updateLanguageSelector(select) {
  const icon = select.closest(".language-selector")?.querySelector("[data-language-selector-icon]");
  const option = select.selectedOptions[0];
  if (icon && option) icon.textContent = option.dataset.icon || "";
}

persistInitialLanguage();

async function login(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const response = await fetch("/auth/cookie/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error(tr("js.invalid-login"));
}

async function register(email, password) {
  const response = await fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || tr("js.register-error"));
  }
}

async function submitAuthForm(form, mode) {
  const message = form.querySelector("[data-auth-message]");
  const email = form.elements.email.value.trim();
  const password = form.elements.password.value;
  setSaveState(message, tr("js.login-progress"), false);
  try {
    if (mode === "register") await register(email, password);
    await login(email, password);
    window.location.href = "/";
  } catch (error) {
    setSaveState(message, error.message || tr("js.login-error"), true);
  }
}

function parseDisplayNumber(value) {
  let normalized = String(value || "")
    .trim()
    .replace(/\s/g, "")
    .replace(/EUR|eur|euro/gi, "");
  if (!normalized) return 0;
  const lastComma = normalized.lastIndexOf(",");
  const lastDot = normalized.lastIndexOf(".");
  const decimalIndex = Math.max(lastComma, lastDot);
  if (decimalIndex >= 0) {
    const separator = normalized[decimalIndex];
    const fractionLength = normalized.length - decimalIndex - 1;
    const looksLikeDecimal = fractionLength > 0 && fractionLength <= numberDecimals();
    if (looksLikeDecimal) {
      const integerPart = normalized.slice(0, decimalIndex).replace(/[,.]/g, "");
      const fractionPart = normalized.slice(decimalIndex + 1).replace(/[,.]/g, "");
      return Number(`${integerPart}.${fractionPart}`);
    }
    normalized = normalized.split(separator).join("");
  }
  return Number(normalized.replace(/[,.]/g, ""));
}

function formatDisplayNumber(value, decimals = 2) {
  const sign = value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toLocaleString(displayLocale(), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

function formatDisplayMoney(value, decimals = 2) {
  return `${formatDisplayNumber(value, decimals)} EUR`;
}

function updateTransactionRunningBalances(table) {
  if (!table) return;
  const openingRaw = table.dataset.openingBalance || "";
  const balanceDefined = openingRaw.trim() !== "";
  const decimals = Number(table.dataset.numberDecimals || numberDecimals());
  let runningBalance = balanceDefined ? parseDisplayNumber(openingRaw) : 0;
  let operationsTotal = 0;

  table.querySelectorAll("tbody tr").forEach((row) => {
    const index = row.querySelector(".row-index-value");
    const title = balanceDefined
      ? `${tr("js.balance")}: ${formatDisplayMoney(runningBalance, decimals)}`
      : tr("js.unknown-balance");
    if (index) {
      index.title = title;
      index.setAttribute("aria-label", title);
    }
    const amount = parseDisplayNumber(getRowField(row, "amount"));
    if (Number.isFinite(amount)) {
      operationsTotal += amount;
      if (balanceDefined) runningBalance += amount;
    }
  });

  const currentBalance = table.querySelector("[data-current-balance-text]");
  if (currentBalance) {
    currentBalance.textContent = balanceDefined
      ? `${tr("js.current-balance")} : ${formatDisplayMoney(runningBalance, decimals)} - ${tr("js.total-operations")} : ${formatDisplayMoney(operationsTotal, decimals)}`
      : `${tr("js.current-balance")} : ${tr("period.unknown")} - ${tr("js.total-operations")} : ${formatDisplayMoney(operationsTotal, decimals)}`;
  }
}

