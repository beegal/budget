function setSaveState(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("save-error", isError);
}

function resetSaveState() {
  setSaveState(document.querySelector("[data-save-state]"), "");
}

async function login(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const response = await fetch("/auth/cookie/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error("Email ou mot de passe invalide");
}

async function register(email, password) {
  const response = await fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Création du compte impossible");
  }
}

async function submitAuthForm(form, mode) {
  const message = form.querySelector("[data-auth-message]");
  const email = form.elements.email.value.trim();
  const password = form.elements.password.value;
  setSaveState(message, "Connexion...", false);
  try {
    if (mode === "register") await register(email, password);
    await login(email, password);
    window.location.href = "/";
  } catch (error) {
    setSaveState(message, error.message || "Erreur de connexion", true);
  }
}

function parseDisplayNumber(value) {
  return Number(String(value || "").replace(/\s/g, "").replace(",", "."));
}

function formatDisplayNumber(value, decimals = 2) {
  const sign = value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toLocaleString("fr-BE", {
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
  const decimals = Number(table.dataset.numberDecimals || 2);
  let runningBalance = balanceDefined ? parseDisplayNumber(openingRaw) : 0;
  let operationsTotal = 0;

  table.querySelectorAll("tbody tr").forEach((row) => {
    const index = row.querySelector(".row-index-value");
    const title = balanceDefined ? `Solde: ${formatDisplayMoney(runningBalance, decimals)}` : "Solde: inconnu";
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
      ? `Solde actuel : ${formatDisplayMoney(runningBalance, decimals)} - Total opérations : ${formatDisplayMoney(operationsTotal, decimals)}`
      : `Solde actuel : inconnu - Total opérations : ${formatDisplayMoney(operationsTotal, decimals)}`;
  }
}


async function saveCell(element) {
  const state = document.querySelector("[data-save-state]");
  const kind = element.dataset.save;
  let payload = { value: element.value ?? element.textContent.trim() };
  let endpoint = `/api/${kind}`;

  if (kind === "transaction") {
    const row = element.closest("[data-transaction-id]");
    payload.id = row.dataset.transactionId;
    payload.field = element.dataset.field;
  } else if (kind === "account-balance") {
    payload.period_id = element.dataset.periodId;
    payload.account_id = element.dataset.accountId;
    payload.field = element.dataset.field;
  } else if (kind === "label") {
    const row = element.closest("[data-label-id]");
    payload.id = row.dataset.labelId;
    payload.field = element.dataset.field;
  } else if (kind === "period-date") {
    payload.id = element.dataset.id;
    payload.field = element.dataset.field;
  } else {
    payload.id = element.dataset.id;
  }

  element.classList.add("saving");
  setSaveState(state, "Enregistrement...");

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  element.classList.remove("saving");

  if (!result.ok) {
    element.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  element.classList.remove("save-error");
  if (kind === "period-date") {
    element.value = result.value || "";
    window.location.reload();
    return;
  }
  if (result.value !== undefined) {
    if (element.matches("input, select, textarea")) element.value = result.value;
    else element.textContent = result.value;
    element.dataset.before = result.value;
    element.dataset.original = result.value;
    if (kind === "transaction" && element.dataset.field === "date") {
      element.closest("[data-transaction-id]").dataset.sortDate = result.date_sort || "";
    }
  }
  element.classList.add("saved");
  setSaveState(state, "Enregistré");
  setTimeout(() => element.classList.remove("saved"), 700);
}

function openAccountBalanceEditor(cell) {
  const display = cell.querySelector("[data-balance-display]");
  const editor = cell.querySelector("[data-balance-edit]");
  const input = cell.querySelector("[data-balance-input]");
  if (!display || !editor || !input) return;
  input.value = cell.dataset.original || "";
  display.hidden = true;
  editor.hidden = false;
  input.focus();
  input.select();
}

function cancelAccountBalanceEditor(cell) {
  const display = cell.querySelector("[data-balance-display]");
  const editor = cell.querySelector("[data-balance-edit]");
  const input = cell.querySelector("[data-balance-input]");
  if (input) input.value = cell.dataset.original || "";
  if (editor) editor.hidden = true;
  if (display) display.hidden = false;
  cell.classList.remove("save-error");
  resetSaveState();
}

function setAccountBalanceTone(cell, value) {
  const amount = parseDisplayNumber(value);
  cell.classList.remove("positive", "negative");
  if (!value) return;
  if (amount > 0) cell.classList.add("positive");
  if (amount < 0) cell.classList.add("negative");
}

async function saveAccountBalanceEditor(cell) {
  const state = document.querySelector("[data-save-state]");
  const input = cell.querySelector("[data-balance-input]");
  const display = cell.querySelector("[data-balance-display]");
  const editor = cell.querySelector("[data-balance-edit]");
  const value = input?.value.trim() || "";
  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/account-balance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      period_id: cell.dataset.periodId,
      account_id: cell.dataset.accountId,
      field: "opening",
      value,
    }),
  });
  const result = await response.json();
  if (!result.ok) {
    cell.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  const savedValue = result.value || "";
  cell.dataset.original = savedValue;
  if (input) input.value = savedValue;
  if (display) {
    display.textContent = result.display || "inconnu";
    display.classList.toggle("balance-undefined", !savedValue);
    display.hidden = false;
  }
  if (editor) editor.hidden = true;
  setAccountBalanceTone(cell, savedValue);
  const currentCell = cell.closest("tr")?.querySelector("[data-account-current-cell]");
  if (currentCell) {
    currentCell.textContent = result.current_display || "inconnu";
    currentCell.classList.toggle("balance-undefined", !result.current);
    setAccountBalanceTone(currentCell, result.current || "");
  }
  cell.classList.remove("save-error");
  setSaveState(state, "Enregistré");
}

async function hideAccountTab(button) {
  if (button.disabled) return;
  const response = await fetch("/api/account-visible-if-empty", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: button.dataset.accountId, value: false }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(document.querySelector("[data-save-state]"), result.error || "Erreur", true);
    return;
  }
  window.location.href = `/period/${button.dataset.periodId}`;
}

async function saveTransactionRow(row) {
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-transaction-table]");
  const payload = {
    id: row.dataset.transactionId || null,
    period_id: table.dataset.periodId,
    account_id: table.dataset.accountId,
    date: getRowField(row, "date"),
    label: getRowField(row, "label"),
    amount: getRowField(row, "amount"),
    comment: getRowField(row, "comment"),
  };

  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/transaction-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }

  row.dataset.transactionId = result.id;
  row.dataset.sortDate = result.date_sort || "";
  setRowField(row, "date", result.date || "");
  setRowField(row, "label", result.label || "");
  setRowField(row, "amount", result.amount || "");
  setRowField(row, "comment", result.comment || "");
  setRowField(row, "sort_index", result.sort_index || "");
  setTransactionRowTone(row);
  delete row.dataset.newRow;
  row.classList.remove("dirty", "save-error");
  snapshotRow(row);
  setRowActions(row, false);
  insertTransactionRowSorted(row);
  applyTransactionIndexes(table, result.rows || []);
  updateTransactionRunningBalances(table);
  flashSavedRow(row);
  setSaveState(state, "Enregistré");
}

async function deleteTransactionRow(row) {
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-transaction-table]");
  if (row.dataset.newRow === "true") {
    row.remove();
    return;
  }
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/transaction-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.transactionId }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  applyTransactionIndexes(table, result.rows || []);
  updateTransactionRunningBalances(table);
  setSaveState(state, "Supprimé");
}

async function clearTransactionTable(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/transaction-clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId, account_id: table.dataset.accountId }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  table.querySelector("tbody").innerHTML = "";
  updateTransactionRunningBalances(table);
  setSaveState(state, "Supprimé");
}

function getRowField(row, field) {
  if (field === "label") return row.querySelector("[data-label-input]")?.value.trim() || "";
  return row.querySelector(`[data-field="${field}"]`)?.textContent.trim() || "";
}

function setRowField(row, field, value) {
  if (field === "label") {
    const input = row.querySelector("[data-label-input]");
    if (input) input.value = value;
    return;
  }
  const cell = row.querySelector(`[data-field="${field}"]`);
  if (cell) cell.textContent = value;
}

function setTransactionRowTone(row) {
  const amount = parseDisplayNumber(getRowField(row, "amount"));
  row.classList.remove("amount-positive", "amount-negative");
  if (amount > 0) row.classList.add("amount-positive");
  if (amount < 0) row.classList.add("amount-negative");
}

function transactionSortKey(row) {
  const date = row.dataset.sortDate || getRowField(row, "date") || "9999-12-31";
  const index = Number(getRowField(row, "sort_index") || Number.MAX_SAFE_INTEGER);
  const id = Number(row.dataset.transactionId || Number.MAX_SAFE_INTEGER);
  return { date, index, id };
}

function insertTransactionRowSorted(row) {
  const tbody = row.closest("tbody");
  if (!tbody) return;
  const current = transactionSortKey(row);
  const target = [...tbody.querySelectorAll("tr")]
    .filter((candidate) => candidate !== row)
    .find((candidate) => {
      const candidateKey = transactionSortKey(candidate);
      return (
        candidateKey.date > current.date ||
        (candidateKey.date === current.date && candidateKey.index > current.index) ||
        (candidateKey.date === current.date && candidateKey.index === current.index && candidateKey.id > current.id)
      );
    });
  tbody.insertBefore(row, target || null);
}

function applyTransactionIndexes(table, rows) {
  if (!table || !rows.length) return;
  const tbody = table.querySelector("tbody");
  for (const item of rows) {
    const row = table.querySelector(`tr[data-transaction-id="${item.id}"]`);
    if (!row) continue;
    setRowField(row, "date", item.date || "");
    row.dataset.sortDate = item.date_sort || "";
    setRowField(row, "sort_index", item.sort_index || "");
    snapshotRow(row);
  }
  for (const item of rows) {
    const row = table.querySelector(`tr[data-transaction-id="${item.id}"]`);
    if (row) tbody.appendChild(row);
  }
  updateTransactionRunningBalances(table);
}

function flashSavedRow(row) {
  row.classList.remove("row-saved-flash");
  void row.offsetWidth;
  row.classList.add("row-saved-flash");
  window.setTimeout(() => row.classList.remove("row-saved-flash"), 1400);
}

async function reorderTransactionRow(row, targetRow, position) {
  if (!row || !targetRow || row === targetRow || row.dataset.newRow === "true") return;
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-transaction-table]");
  setSaveState(state, "Réorganisation...");
  const response = await fetch("/api/transaction-reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: row.dataset.transactionId,
      target_id: targetRow.dataset.transactionId,
      position,
    }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  setRowField(row, "date", result.date || "");
  row.dataset.sortDate = result.date_sort || "";
  setRowField(row, "sort_index", result.sort_index || "");
  applyTransactionIndexes(table, result.rows || []);
  updateTransactionRunningBalances(table);
  row.classList.remove("save-error");
  flashSavedRow(row);
  setSaveState(state, "Ordre enregistré");
}

function snapshotRow(row) {
  for (const field of ["date", "amount", "comment"]) {
    const cell = row.querySelector(`[data-field="${field}"]`);
    if (cell) cell.dataset.original = cell.textContent.trim();
  }
  const label = row.querySelector("[data-label-input]");
  if (label) label.dataset.original = label.value.trim();
}

function restoreRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    return;
  }
  for (const field of ["date", "amount", "comment"]) {
    const cell = row.querySelector(`[data-field="${field}"]`);
    if (cell) cell.textContent = cell.dataset.original || "";
  }
  const label = row.querySelector("[data-label-input]");
  if (label) label.value = label.dataset.original || "";
  setTransactionRowTone(row);
  row.classList.remove("dirty", "save-error");
  setRowActions(row, false);
  updateTransactionRunningBalances(row.closest("[data-transaction-table]"));
  resetSaveState();
}

function markRowDirty(row) {
  if (!row || !row.closest("[data-transaction-table]")) return;
  row.classList.add("dirty");
  setRowActions(row, "edit");
}

function setRowActions(row, mode) {
  setActionButtons(row, "row", mode);
}

function focusRowDeleteAction(row) {
  const table = row.closest("[data-transaction-table]");
  table?.querySelectorAll("tbody tr").forEach((candidate) => {
    if (candidate !== row && !candidate.classList.contains("dirty")) setRowActions(candidate, false);
  });
  setRowActions(row, "delete");
}

function createEmptyRow(table) {
  const row = document.createElement("tr");
  row.dataset.newRow = "true";
  row.className = "dirty";
  row.innerHTML = `
    <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-field="sort_index" data-original=""></span></td>
    <td class="editable" contenteditable="true" data-save="transaction" data-field="date" data-original=""></td>
    <td>${labelPickerHtml("", 'data-save="transaction" data-field="label"')}</td>
    <td class="editable num" contenteditable="true" data-save="transaction" data-field="amount" data-original=""></td>
    <td class="editable" contenteditable="true" data-save="transaction" data-field="comment" data-original=""></td>
    <td class="row-actions">
      <button type="button" class="row-confirm" data-confirm-row>V</button>
      <button type="button" class="row-cancel" data-cancel-row>X</button>
      <button type="button" class="row-delete" data-delete-row hidden>-</button>
    </td>`;
  table.querySelector("tbody").appendChild(row);
  updateTransactionRunningBalances(table);
  row.querySelector('[data-field="date"]').focus();
}

async function saveSettingRow(row) {
  const kind = row.dataset.kind || row.closest("[data-settings-table]")?.dataset.kind;
  const wasNewAccount = kind === "account" && row.dataset.newRow === "true";
  const inputs = settingInputs(row);
  const value = settingRowValue(row, kind);
  const response = await fetch(`/api/${kind}-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id || null, value }),
  });
  const result = await response.json();
  if (!result.ok) {
    inputs.forEach((input) => input.classList.add("save-error"));
    return;
  }
  row.dataset.id = result.id;
  delete row.dataset.newRow;
  setSettingRowValue(row, kind, result.value);
  const summaryCheckbox = row.querySelector("[data-account-summary]");
  if (summaryCheckbox) {
    summaryCheckbox.dataset.id = result.id;
    summaryCheckbox.disabled = false;
  }
  const visibleIfEmptyCheckbox = row.querySelector("[data-account-visible-if-empty]");
  if (visibleIfEmptyCheckbox) {
    visibleIfEmptyCheckbox.dataset.id = result.id;
    visibleIfEmptyCheckbox.disabled = false;
  }
  inputs.forEach((input) => input.classList.remove("save-error"));
  row.classList.remove("dirty");
  setSettingActions(row, false);
  if (wasNewAccount) {
    window.location.reload();
    return;
  }
  if (kind === "account") applyAccountIndexes(row.closest("[data-settings-table]"), result.rows || []);
  if (kind === "label") addLabelName(result.value);
}

function settingInputs(row) {
  return [...row.querySelectorAll("[data-setting-value]")];
}

function splitSettingLabel(value) {
  const [group, ...rest] = String(value || "").split(" - ");
  return {
    group: group.trim(),
    subcategory: rest.join(" - ").trim(),
  };
}

function settingRowValue(row, kind) {
  if (kind !== "label") return row.querySelector("[data-setting-value]")?.value.trim() || "";
  const group = row.querySelector('[data-setting-part="group"]')?.value.trim() || "";
  const subcategory = row.querySelector('[data-setting-part="subcategory"]')?.value.trim() || "";
  return subcategory ? `${group} - ${subcategory}` : group;
}

function setSettingRowValue(row, kind, value) {
  if (kind !== "label") {
    const input = row.querySelector("[data-setting-value]");
    if (input) {
      input.value = value;
      input.dataset.original = value;
    }
    return;
  }
  const parts = splitSettingLabel(value);
  const group = row.querySelector('[data-setting-part="group"]');
  const subcategory = row.querySelector('[data-setting-part="subcategory"]');
  if (group) {
    group.value = parts.group;
    group.dataset.original = parts.group;
  }
  if (subcategory) {
    subcategory.value = parts.subcategory;
    subcategory.dataset.original = parts.subcategory;
  }
}

async function saveAccountSummary(input) {
  const response = await fetch("/api/account-summary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: input.dataset.id, value: input.checked }),
  });
  const result = await response.json();
  input.classList.toggle("save-error", !result.ok);
}

async function saveAccountVisibleIfEmpty(input) {
  const response = await fetch("/api/account-visible-if-empty", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: input.dataset.id, value: input.checked }),
  });
  const result = await response.json();
  input.classList.toggle("save-error", !result.ok);
}

async function deleteSettingRow(row) {
  const state = document.querySelector("[data-save-state]");
  const kind = row.dataset.kind || row.closest("[data-settings-table]")?.dataset.kind;
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  const inputs = settingInputs(row);
  setSaveState(state, "Suppression...");
  const response = await fetch(`/api/${kind}-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    inputs.forEach((input) => input.classList.add("save-error"));
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  setSaveState(state, "Supprimé");
}

async function deleteAccountRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/account-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.querySelector("[data-setting-value]")?.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  applyAccountIndexes(document.querySelector('[data-settings-table][data-kind="account"]'), result.rows || []);
  setSaveState(state, "Supprimé");
}

function closeAccountMergeLists(exceptList = null) {
  document.querySelectorAll("[data-account-merge-list]").forEach((candidate) => {
    if (candidate !== exceptList) candidate.hidden = true;
  });
}

function toggleAccountMergeList(row) {
  const list = row.querySelector("[data-account-merge-list]");
  if (!list) return;
  closeAccountMergeLists(list);
  list.hidden = !list.hidden;
}

async function mergeAccountRow(button) {
  const row = button.closest("[data-settings-row]");
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Fusion...");
  const response = await fetch("/api/account-merge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id, target_id: button.dataset.mergeTarget }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.querySelector("[data-setting-value]")?.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  closeAccountMergeLists();
  applyAccountIndexes(document.querySelector('[data-settings-table][data-kind="account"]'), result.rows || []);
  setSaveState(state, "Compte fusionné");
}

async function reorderAccountRow(row, targetRow, position) {
  if (!row || !targetRow || row === targetRow || row.dataset.newRow === "true") return;
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-settings-table]");
  setSaveState(state, "Réorganisation...");
  const response = await fetch("/api/account-reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id, target_id: targetRow.dataset.id, position }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.querySelector("[data-setting-value]")?.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  applyAccountIndexes(table, result.rows || []);
  flashSavedRow(row);
  setSaveState(state, "Ordre enregistré");
}

function applyAccountIndexes(table, rows) {
  if (!table || !rows.length) return;
  const tbody = table.querySelector("tbody");
  for (const item of rows) {
    const row = table.querySelector(`[data-settings-row][data-id="${item.id}"]`);
    if (!row) continue;
    const index = row.querySelector("[data-account-index]");
    if (index) index.textContent = item.sort_index;
  }
  for (const item of rows) {
    const row = table.querySelector(`[data-settings-row][data-id="${item.id}"]`);
    if (row) tbody.appendChild(row);
  }
}

async function saveBudgetRow(row) {
  const state = document.querySelector("[data-save-state]");
  const payload = { id: row.dataset.id || null };
  row.querySelectorAll("[data-budget-field]").forEach((input) => {
    payload[input.dataset.budgetField] = input.value.trim();
  });
  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/monthly-budget-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.dataset.id = result.id;
  delete row.dataset.newRow;
  setBudgetField(row, "day", result.day);
  setBudgetField(row, "label", result.label);
  setBudgetField(row, "amount", result.amount);
  setBudgetRowTone(row);
  snapshotBudgetRow(row);
  row.classList.remove("dirty", "save-error");
  setBudgetActions(row, false);
  setSaveState(state, "Enregistré");
}

async function deleteBudgetRow(row) {
  const state = document.querySelector("[data-save-state]");
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/monthly-budget-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  setSaveState(state, "Supprimé");
}

function createBudgetRow(table) {
  table.querySelector("[data-empty-budget-row]")?.remove();
  const row = document.createElement("tr");
  row.dataset.budgetRow = "";
  row.dataset.newRow = "true";
  row.className = "dirty";
  row.innerHTML = `
    <td><input data-budget-field="day" data-original="" inputmode="numeric"></td>
    <td>${labelPickerHtml("", 'data-budget-field="label"')}</td>
    <td><input data-budget-field="amount" data-original="" inputmode="decimal"></td>
    <td class="row-actions">
      <button type="button" class="row-confirm" data-confirm-budget>V</button>
      <button type="button" class="row-cancel" data-cancel-budget>X</button>
      <button type="button" class="row-delete" data-delete-budget hidden>-</button>
    </td>`;
  table.querySelector("tbody").appendChild(row);
  row.querySelector("[data-budget-field='day']").focus();
}

function restoreBudgetRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  row.querySelectorAll("[data-budget-field]").forEach((input) => {
    input.value = input.dataset.original || "";
  });
  setBudgetRowTone(row);
  row.classList.remove("dirty", "save-error");
  setBudgetActions(row, false);
  resetSaveState();
}

function markBudgetDirty(row) {
  row.classList.add("dirty");
  setBudgetRowTone(row);
  setBudgetActions(row, "edit");
}

function setBudgetRowTone(row) {
  const amount = parseDisplayNumber(row.querySelector('[data-budget-field="amount"]')?.value || "");
  row.classList.remove("amount-positive", "amount-negative");
  if (amount > 0) row.classList.add("amount-positive");
  if (amount < 0) row.classList.add("amount-negative");
}

function setBudgetActions(row, mode) {
  setActionButtons(row, "budget", mode);
}

function setBudgetField(row, field, value) {
  const input = row.querySelector(`[data-budget-field="${field}"]`);
  if (input) input.value = value ?? "";
}

function snapshotBudgetRow(row) {
  row.querySelectorAll("[data-budget-field]").forEach((input) => {
    input.dataset.original = input.value.trim();
  });
}

async function cancelBudgetSchedule(row) {
  const response = await fetch("/api/budget-schedule-cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.budgetScheduleId }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    return;
  }
  row.classList.remove("budget-status-scheduled");
  row.classList.add("budget-status-cancel");
  const status = row.querySelector("[data-budget-status]");
  if (status) status.textContent = result.status_label || "Annulé";
  row.querySelector("[data-budget-schedule-cancel]")?.remove();
  row.querySelector("[data-budget-schedule-confirm]")?.remove();
  const list = row.querySelector("[data-budget-account-list]");
  if (list) list.hidden = true;
  flashSavedRow(row);
}

function closeBudgetAccountLists(exceptList = null) {
  document.querySelectorAll("[data-budget-account-list]").forEach((candidate) => {
    if (candidate !== exceptList) candidate.hidden = true;
  });
}

function toggleBudgetAccountList(row) {
  const list = row.querySelector("[data-budget-account-list]");
  if (!list) return;
  closeBudgetAccountLists(list);
  list.hidden = !list.hidden;
}

async function instantiateBudgetSchedule(button) {
  const row = button.closest("[data-budget-schedule-id]");
  const output = row.querySelector("[data-budget-created]");
  const response = await fetch("/api/budget-schedule-instantiate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.budgetScheduleId, account_id: button.dataset.budgetAccount }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    if (output) {
      output.hidden = false;
      output.textContent = result.error || "Erreur";
    }
    return;
  }
  row.classList.remove("save-error");
  row.classList.remove("budget-status-scheduled", "budget-status-cancel");
  row.classList.add("budget-status-found");
  const status = row.querySelector("[data-budget-status]");
  if (status) status.textContent = result.status_label || "Trouvé";
  row.querySelector("[data-budget-schedule-cancel]")?.remove();
  row.querySelector("[data-budget-schedule-confirm]")?.remove();
  row.querySelector("[data-budget-account-list]").hidden = true;
  if (output) {
    output.hidden = false;
    output.innerHTML = `Créé dans <a href="/period/${row.closest("[data-budget-schedule-table]").dataset.periodId}?account=${result.account_id}">${escapeHtml(result.account_name)}</a>, ligne #${escapeHtml(result.sort_index)} (${escapeHtml(result.date)})`;
  }
  flashSavedRow(row);
}

function openPeriodRangeEditor(range) {
  const display = range.querySelector("[data-period-range-display]");
  const editor = range.querySelector("[data-period-range-edit]");
  if (!display || !editor) return;
  display.hidden = true;
  editor.hidden = false;
  editor.querySelector("[data-period-start]")?.focus();
}

function cancelPeriodRangeEditor(range) {
  const display = range.querySelector("[data-period-range-display]");
  const editor = range.querySelector("[data-period-range-edit]");
  const start = range.querySelector("[data-period-start]");
  const end = range.querySelector("[data-period-end]");
  if (start) start.value = start.dataset.original || "";
  if (end) end.value = end.dataset.original || "";
  range.classList.remove("save-error");
  if (editor) editor.hidden = true;
  if (display) display.hidden = false;
  resetSaveState();
}

async function savePeriodRange(range) {
  const state = document.querySelector("[data-save-state]");
  const start = range.querySelector("[data-period-start]");
  const end = range.querySelector("[data-period-end]");
  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/period-range", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: range.dataset.id,
      start_date: start?.value.trim() || "",
      end_date: end?.value.trim() || "",
    }),
  });
  const result = await response.json();
  if (!result.ok) {
    range.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  if (start) {
    start.value = result.start_date || "";
    start.dataset.original = start.value;
  }
  if (end) {
    end.value = result.end_date || "";
    end.dataset.original = end.value;
  }
  window.location.reload();
}

function openPeriodNameEditor(wrapper) {
  const display = wrapper.querySelector("[data-period-name-display]");
  const editor = wrapper.querySelector("[data-period-name-edit]");
  if (!display || !editor) return;
  display.hidden = true;
  editor.hidden = false;
  const input = editor.querySelector("[data-period-name-input]");
  input?.focus();
  input?.select();
}

function cancelPeriodNameEditor(wrapper) {
  const display = wrapper.querySelector("[data-period-name-display]");
  const editor = wrapper.querySelector("[data-period-name-edit]");
  const input = wrapper.querySelector("[data-period-name-input]");
  if (input) input.value = input.dataset.original || "";
  wrapper.classList.remove("save-error");
  if (editor) editor.hidden = true;
  if (display) display.hidden = false;
  resetSaveState();
}

async function savePeriodName(wrapper) {
  const state = document.querySelector("[data-save-state]");
  const input = wrapper.querySelector("[data-period-name-input]");
  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/period-name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: wrapper.dataset.id,
      name: input?.value.trim() || "",
    }),
  });
  const result = await response.json();
  if (!result.ok) {
    wrapper.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  if (input) {
    input.value = result.name || "";
    input.dataset.original = input.value;
  }
  window.location.reload();
}

async function deletePeriod(button) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/period-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: button.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  window.location.reload();
}

function createBudgetScheduleRow(table) {
  table.querySelector("tbody tr td[colspan]")?.closest("tr")?.remove();
  const index = table.querySelectorAll("tbody tr").length + 1;
  const row = document.createElement("tr");
  row.className = "budget-schedule-row budget-status-scheduled dirty";
  row.dataset.newRow = "true";
  row.dataset.budgetScheduleNewRow = "true";
  row.innerHTML = `
    <td class="row-index-cell"><span class="row-index-value">${index}</span></td>
    <td>${labelPickerHtml("", 'data-budget-schedule-field="label"')}</td>
    <td><input class="num" data-budget-schedule-field="amount" inputmode="decimal" placeholder="0"></td>
    <td><span class="budget-status-pill">Planifié</span></td>
    <td class="row-actions">
      <button type="button" class="row-confirm" data-confirm-budget-schedule-row>V</button>
      <button type="button" class="row-cancel" data-cancel-budget-schedule-row>X</button>
    </td>`;
  table.querySelector("tbody").appendChild(row);
  row.querySelector("[data-label-input]")?.focus();
}

function cancelBudgetScheduleRow(row) {
  if (row?.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
  }
}

async function saveBudgetScheduleRow(row) {
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-budget-schedule-table]");
  const label = row.querySelector("[data-label-input]")?.value.trim() || "";
  const amount = row.querySelector('[data-budget-schedule-field="amount"]')?.value.trim() || "";
  setSaveState(state, "Enregistrement...");
  const response = await fetch("/api/budget-schedule-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId, label, amount }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  window.location.reload();
}

async function clearBudgetSchedule(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/budget-schedule-clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  window.location.reload();
}

function createSettingRow(table) {
  const kind = table.dataset.kind;
  const valueCells = kind === "label"
    ? `<td><input value="" data-setting-value data-setting-part="group" data-original="" autocomplete="off" placeholder="Nom de groupage"></td>
    <td><input value="" data-setting-value data-setting-part="subcategory" data-original="" autocomplete="off" placeholder="Sous catégorie"></td>`
    : `<td><input value="" data-setting-value data-original="" autocomplete="off" placeholder="Nouveau compte"></td>`;
  const row = document.createElement("tr");
  row.dataset.settingsRow = "";
  row.dataset.kind = kind;
  row.dataset.newRow = "true";
  row.className = "dirty";
  row.innerHTML = `
    ${kind === "account" ? '<td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="Déplacer">↕</button></td>' : ""}
    ${valueCells}
    ${kind === "account" ? '<td class="center-cell"><input type="checkbox" data-account-summary checked disabled></td><td class="center-cell"><input type="checkbox" data-account-visible-if-empty checked disabled></td>' : ""}
    <td class="row-actions">
      <button type="button" class="row-confirm" data-confirm-setting>V</button>
      <button type="button" class="row-cancel" data-cancel-setting>X</button>
      <button type="button" class="row-delete" data-delete-setting hidden>-</button>
    </td>`;
  table.querySelector("tbody").appendChild(row);
  row.querySelector("[data-setting-value]").focus();
}

function openPeriodCreateCard(card) {
  const toggle = card.querySelector("[data-period-create-toggle]");
  const form = card.querySelector("[data-period-create-form]");
  if (!toggle || !form) return;
  toggle.hidden = true;
  form.hidden = false;
  form.querySelector('input[name="name"]')?.focus();
}

function cancelPeriodCreateCard(card) {
  const toggle = card.querySelector("[data-period-create-toggle]");
  const form = card.querySelector("[data-period-create-form]");
  if (!toggle || !form) return;
  form.reset();
  form.hidden = true;
  toggle.hidden = false;
  resetSaveState();
}

function restoreSettingRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    return;
  }
  settingInputs(row).forEach((input) => {
    input.value = input.dataset.original || "";
    input.classList.remove("save-error");
  });
  row.classList.remove("dirty");
  setSettingActions(row, false);
  resetSaveState();
}

function markSettingDirty(row) {
  row.classList.add("dirty");
  setSettingActions(row, "edit");
}

function setSettingActions(row, mode) {
  setActionButtons(row, "setting", mode);
}

function setActionButtons(row, kind, mode) {
  const editing = mode === true || mode === "edit";
  const deleting = mode === "delete";
  row.querySelectorAll(`[data-confirm-${kind}], [data-cancel-${kind}]`).forEach((button) => {
    button.hidden = !editing;
  });
  row.querySelectorAll(`[data-delete-${kind}]`).forEach((button) => {
    button.hidden = !deleting;
  });
}

function focusSettingDeleteAction(row) {
  const table = row.closest("[data-settings-table]");
  table?.querySelectorAll("[data-settings-row]").forEach((candidate) => {
    if (candidate !== row && !candidate.classList.contains("dirty")) setSettingActions(candidate, false);
  });
  setSettingActions(row, "delete");
}

function labelPickerHtml(value, attrs) {
  return `<div class="label-picker" data-label-picker>
    <div class="label-picker-row">
      <input value="${escapeHtml(value)}" data-original="${escapeHtml(value)}" autocomplete="off" placeholder="Intitulé" ${attrs} data-label-input>
      <button class="label-add" type="button" data-create-label hidden>+</button>
    </div>
    <div class="label-suggestions" data-label-suggestions hidden></div>
  </div>`;
}

function labelNames() {
  return window.BUDGET_LABELS || [];
}

function normalized(value) {
  return value.trim().toLocaleLowerCase();
}

function renderLabelSuggestions(picker) {
  const input = picker.querySelector("[data-label-input]");
  const suggestions = picker.querySelector("[data-label-suggestions]");
  const addButton = picker.querySelector("[data-create-label]");
  const value = input.value.trim();
  const needle = normalized(value);
  const labels = labelNames();
  const exact = value && labels.some((label) => normalized(label) === needle);
  const matches = needle
    ? labels.filter((label) => normalized(label).includes(needle)).slice(0, 8)
    : labels.slice(0, 8);

  addButton.hidden = !value || exact;
  suggestions.innerHTML = matches
    .map((label) => `<button type="button" data-label-suggestion="${escapeHtml(label)}">${escapeHtml(label)}</button>`)
    .join("");
  suggestions.hidden = matches.length === 0;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function addLabelName(name) {
  window.BUDGET_LABELS = labelNames();
  if (!window.BUDGET_LABELS.some((label) => normalized(label) === normalized(name))) {
    window.BUDGET_LABELS.push(name);
    window.BUDGET_LABELS.sort((a, b) => a.localeCompare(b));
  }
}

async function createLabelFromPicker(picker) {
  const input = picker.querySelector("[data-label-input]");
  const state = document.querySelector("[data-save-state]");
  const value = input.value.trim();
  if (!value) return;

  setSaveState(state, "Création de l'intitulé...");
  const response = await fetch("/api/label-from-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  const result = await response.json();
  if (!result.ok) {
    input.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }

  addLabelName(result.label.name);
  input.value = result.label.name;
  renderLabelSuggestions(picker);
  const row = picker.closest("tr");
  if (row?.closest("[data-transaction-table]")) markRowDirty(row);
  else if (row?.closest("[data-monthly-budget-table]")) markBudgetDirty(row);
  else if (row?.closest("[data-budget-schedule-table]")) row.classList.add("dirty");
  else if (input.dataset.save) await saveCell(input);
}

function periodFilterCheckboxes(filter) {
  if (!filter) return [];
  return Array.from(filter.querySelectorAll("[data-period-filter-checkbox]"));
}

function periodFilterSelectedIds(filter) {
  return periodFilterCheckboxes(filter)
    .filter((checkbox) => checkbox.checked)
    .map((checkbox) => checkbox.value);
}

function renderPeriodFilterTags(filter) {
  if (!filter) return;
  const tagBox = filter.querySelector("[data-period-tag-box]");
  const input = filter.querySelector("[data-period-tag-input]");
  if (!tagBox || !input) return;
  tagBox.querySelectorAll("[data-period-tag]").forEach((tag) => tag.remove());
  periodFilterCheckboxes(filter)
    .filter((checkbox) => checkbox.checked)
    .forEach((checkbox) => {
      const tag = document.createElement("span");
      tag.className = "period-filter-tag";
      tag.dataset.periodTag = checkbox.value;
      tag.textContent = checkbox.dataset.periodName || checkbox.value;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.dataset.periodTagRemove = "";
      remove.setAttribute("aria-label", `Retirer ${tag.textContent}`);
      remove.textContent = "x";
      tag.appendChild(remove);
      tagBox.insertBefore(tag, input);
    });
}

function syncPeriodFilter(filter, mode = "explicit") {
  if (!filter) return;
  const hidden = filter.querySelector("[data-period-filter-value]");
  const checkboxes = periodFilterCheckboxes(filter);
  const selectedIds = periodFilterSelectedIds(filter);
  if (hidden) {
    if (mode === "all" || (checkboxes.length > 0 && selectedIds.length === checkboxes.length)) hidden.value = "all";
    else if (selectedIds.length === 0) hidden.value = "all";
    else hidden.value = selectedIds.join(",");
  }
  renderPeriodFilterTags(filter);
}

function addPeriodFilterTag(filter, value) {
  if (!filter) return false;
  const needle = normalized(value);
  if (!needle) return false;
  const checkboxes = periodFilterCheckboxes(filter);
  const match = checkboxes.find((checkbox) => normalized(checkbox.dataset.periodName || "") === needle)
    || checkboxes.find((checkbox) => normalized(checkbox.value) === needle)
    || checkboxes.find((checkbox) => normalized(checkbox.dataset.periodName || "").includes(needle));
  if (!match) return false;
  match.checked = true;
  syncPeriodFilter(filter);
  return true;
}

function submitPeriodFilterIfNeeded(filter) {
  const form = filter?.closest("form[data-period-auto-submit]");
  if (!form) return;
  submitFilterForm(form);
}

function submitFilterForm(form) {
  if (typeof form.requestSubmit === "function") form.requestSubmit();
  else form.submit();
}

let filterSubmitTimer = null;

function scheduleFilterSubmit(form) {
  if (!form) return;
  window.clearTimeout(filterSubmitTimer);
  filterSubmitTimer = window.setTimeout(() => submitFilterForm(form), 450);
}

function openAdminUserCreateRow(button) {
  const table = button.closest("table");
  const row = table?.querySelector("[data-admin-user-create-row]");
  const addRow = table?.querySelector("[data-admin-user-add-row]");
  if (!row) return;
  row.hidden = false;
  if (addRow) addRow.hidden = true;
  row.querySelector('input[name="email"]')?.focus();
}

function cancelAdminUserCreateRow(button) {
  const table = button.closest("table");
  const row = table?.querySelector("[data-admin-user-create-row]");
  const addRow = table?.querySelector("[data-admin-user-add-row]");
  const form = table?.querySelector("#admin-create-user-form");
  if (form) form.reset();
  if (row) row.hidden = true;
  if (addRow) addRow.hidden = false;
}

document.addEventListener("focusin", (event) => {
  const editable = event.target.closest("[contenteditable][data-save]");
  if (editable) editable.dataset.before = editable.textContent.trim();
  const input = event.target.closest("input[data-save]");
  if (input) input.dataset.before = input.value.trim();
  const periodTagInput = event.target.closest("[data-period-tag-input]");
  if (periodTagInput) {
    const menu = periodTagInput.closest("[data-period-filter]")?.querySelector("[data-period-filter-menu]");
    if (menu) menu.hidden = false;
  }
  const transactionRow = event.target.closest("[data-transaction-table] tr[data-transaction-id]");
  if (transactionRow && !transactionRow.classList.contains("dirty")) focusRowDeleteAction(transactionRow);
  const settingRow = event.target.closest("[data-settings-row]");
  if (settingRow && !settingRow.classList.contains("dirty")) focusSettingDeleteAction(settingRow);
  const budgetRow = event.target.closest("[data-budget-row]");
  if (budgetRow && !budgetRow.classList.contains("dirty")) setBudgetActions(budgetRow, "delete");
  const picker = event.target.closest("[data-label-picker]");
  if (picker) renderLabelSuggestions(picker);
});

document.addEventListener("focusout", (event) => {
  const editable = event.target.closest("[contenteditable][data-save]");
  if (editable) {
    if (editable.closest("[data-transaction-table]")) {
      return;
    }
    const before = editable.dataset.before ?? "";
    const after = editable.textContent.trim();
    if (before !== after) saveCell(editable);
    return;
  }

  const input = event.target.closest("input[data-save]");
  if (input) {
    if (input.closest("[data-transaction-table]")) {
      window.setTimeout(() => {
        const picker = input.closest("[data-label-picker]");
        const suggestions = picker?.querySelector("[data-label-suggestions]");
        if (suggestions) suggestions.hidden = true;
      }, 120);
      return;
    }
    const before = input.dataset.before ?? "";
    const after = input.value.trim();
    if (before !== after) saveCell(input);
    window.setTimeout(() => {
      const picker = input.closest("[data-label-picker]");
      const suggestions = picker?.querySelector("[data-label-suggestions]");
      if (suggestions) suggestions.hidden = true;
    }, 120);
  }

  const labelInput = event.target.closest("[data-label-input]");
  if (labelInput && !labelInput.dataset.save) {
    window.setTimeout(() => {
      const picker = labelInput.closest("[data-label-picker]");
      const suggestions = picker?.querySelector("[data-label-suggestions]");
      if (suggestions) suggestions.hidden = true;
    }, 120);
  }
});

document.addEventListener("keydown", async (event) => {
  const editable = event.target.closest("[contenteditable][data-save]");
  const input = event.target.closest("input[data-save]");
  const labelInput = event.target.closest("[data-label-input]");
  const transactionRow = event.target.closest("[data-transaction-table] tr");
  const settingInput = event.target.closest("[data-setting-value]");
  const budgetInput = event.target.closest("[data-budget-field]");
  const periodInput = event.target.closest("[data-period-start], [data-period-end]");
  const periodNameInput = event.target.closest("[data-period-name-input]");
  const periodCreateInput = event.target.closest("[data-period-create-form] input");
  const budgetScheduleInput = event.target.closest("[data-budget-schedule-field], [data-budget-schedule-new-row] [data-label-input]");
  const accountBalanceInput = event.target.closest("[data-balance-input]");
  const periodTagInput = event.target.closest("[data-period-tag-input]");

  if ((event.key === "Enter" || event.key === ",") && periodTagInput) {
    event.preventDefault();
    const filter = periodTagInput.closest("[data-period-filter]");
    const added = addPeriodFilterTag(filter, periodTagInput.value);
    if (added) {
      periodTagInput.value = "";
      submitPeriodFilterIfNeeded(filter);
    }
    return;
  }
  if (event.key === "Escape" && document.querySelector("[data-budget-account-list]:not([hidden])")) {
    event.preventDefault();
    closeBudgetAccountLists();
    return;
  }
  if (event.key === "Escape" && document.querySelector("[data-account-merge-list]:not([hidden])")) {
    event.preventDefault();
    closeAccountMergeLists();
    return;
  }
  if (event.key === "Escape" && accountBalanceInput) {
    event.preventDefault();
    cancelAccountBalanceEditor(accountBalanceInput.closest("[data-account-balance-cell]"));
    return;
  }
  if (event.key === "Escape" && budgetScheduleInput) {
    event.preventDefault();
    cancelBudgetScheduleRow(budgetScheduleInput.closest("[data-budget-schedule-new-row]"));
    return;
  }
  if (event.key === "Escape" && periodCreateInput) {
    event.preventDefault();
    cancelPeriodCreateCard(periodCreateInput.closest("[data-period-create-card]"));
    return;
  }
  if (event.key === "Escape" && periodNameInput) {
    event.preventDefault();
    cancelPeriodNameEditor(periodNameInput.closest("[data-period-name]"));
    return;
  }
  if (event.key === "Escape" && periodInput) {
    event.preventDefault();
    cancelPeriodRangeEditor(periodInput.closest("[data-period-range]"));
    return;
  }
  if (event.key === "Escape" && transactionRow) {
    event.preventDefault();
    restoreRow(transactionRow);
    return;
  }
  if (event.key === "Escape" && settingInput) {
    event.preventDefault();
    restoreSettingRow(settingInput.closest("[data-settings-row]"));
    return;
  }
  if (event.key === "Escape" && budgetInput) {
    event.preventDefault();
    restoreBudgetRow(budgetInput.closest("[data-budget-row]"));
    return;
  }
  if (event.key === "Enter" && transactionRow) {
    const picker = labelInput?.closest("[data-label-picker]");
    const addButton = picker?.querySelector("[data-create-label]");
    if (addButton && !addButton.hidden) {
      event.preventDefault();
      await createLabelFromPicker(picker);
      return;
    }
    event.preventDefault();
    await saveTransactionRow(transactionRow);
    return;
  }
  if (event.key === "Enter" && accountBalanceInput) {
    event.preventDefault();
    await saveAccountBalanceEditor(accountBalanceInput.closest("[data-account-balance-cell]"));
    return;
  }
  if (event.key === "Enter" && settingInput) {
    event.preventDefault();
    await saveSettingRow(settingInput.closest("[data-settings-row]"));
    return;
  }
  if (event.key === "Enter" && budgetInput) {
    const picker = labelInput?.closest("[data-label-picker]");
    const addButton = picker?.querySelector("[data-create-label]");
    if (addButton && !addButton.hidden) {
      event.preventDefault();
      await createLabelFromPicker(picker);
      return;
    }
    event.preventDefault();
    await saveBudgetRow(budgetInput.closest("[data-budget-row]"));
    return;
  }
  if (event.key === "Enter" && periodInput) {
    event.preventDefault();
    await savePeriodRange(periodInput.closest("[data-period-range]"));
    return;
  }
  if (event.key === "Enter" && periodNameInput) {
    event.preventDefault();
    await savePeriodName(periodNameInput.closest("[data-period-name]"));
    return;
  }
  if (event.key === "Enter" && budgetScheduleInput) {
    const picker = labelInput?.closest("[data-label-picker]");
    const addButton = picker?.querySelector("[data-create-label]");
    if (addButton && !addButton.hidden) {
      event.preventDefault();
      await createLabelFromPicker(picker);
      return;
    }
    event.preventDefault();
    await saveBudgetScheduleRow(budgetScheduleInput.closest("[data-budget-schedule-new-row]"));
    return;
  }
  if (event.key === "Enter" && labelInput) {
    const picker = labelInput.closest("[data-label-picker]");
    const addButton = picker?.querySelector("[data-create-label]");
    if (addButton && !addButton.hidden) {
      event.preventDefault();
      await createLabelFromPicker(picker);
      return;
    }
  }
  if (event.key === "Enter" && editable) {
    event.preventDefault();
    editable.blur();
  }
  if (event.key === "Enter" && input) {
    event.preventDefault();
    if (input.closest("[data-transaction-table]")) markRowDirty(input.closest("tr"));
    else input.blur();
  }
});

document.addEventListener("change", (event) => {
  const accountSummary = event.target.closest("[data-account-summary]");
  if (accountSummary) {
    saveAccountSummary(accountSummary);
    return;
  }
  const accountVisibleIfEmpty = event.target.closest("[data-account-visible-if-empty]");
  if (accountVisibleIfEmpty) {
    saveAccountVisibleIfEmpty(accountVisibleIfEmpty);
    return;
  }
  const input = event.target.closest("select[data-save]");
  if (input) saveCell(input);

  const importSelect = event.target.closest("[data-import-format], [data-import-date-format]");
  if (importSelect) {
    const textarea = document.querySelector("[data-import-textarea]");
    if (!textarea) return;
    const formatSelect = document.querySelector("[data-import-format]");
    const dateFormatSelect = document.querySelector("[data-import-date-format]");
    const dateExamples = {
      dmy: "26/03/2026",
      mdy: "03/26/2026",
      ymd: "2026-03-26",
    };
    const dateExample = dateExamples[dateFormatSelect?.value] || dateExamples.dmy;
    const placeholders = {
      csv_header: `Date,Intitulé,Montant,commentaire\n${dateExample},Exemple,-12.50,Note`,
      csv_no_header: `${dateExample},Exemple,-12.50,Note`,
      tsv_header: `Date\tIntitulé\tMontant\tcommentaire\n${dateExample}\tExemple\t-12.50\tNote`,
      tsv_no_header: `${dateExample}\tExemple\t-12.50\tNote`,
    };
    textarea.placeholder = placeholders[formatSelect?.value] || "";
  }

  const periodCheckbox = event.target.closest("[data-period-filter-checkbox]");
  if (periodCheckbox) {
    const filter = periodCheckbox.closest("[data-period-filter]");
    syncPeriodFilter(filter);
    submitPeriodFilterIfNeeded(filter);
  }

  const autoSubmitSelect = event.target.closest("form[data-filter-auto-submit] select");
  if (autoSubmitSelect) submitFilterForm(autoSubmitSelect.closest("form"));
});

document.addEventListener("input", (event) => {
  const settingInput = event.target.closest("[data-setting-value]");
  if (settingInput) {
    markSettingDirty(settingInput.closest("[data-settings-row]"));
    return;
  }
  const budgetInput = event.target.closest("[data-budget-field]");
  if (budgetInput) {
    const labelInput = event.target.closest("[data-label-input]");
    if (labelInput) renderLabelSuggestions(labelInput.closest("[data-label-picker]"));
    markBudgetDirty(budgetInput.closest("[data-budget-row]"));
    return;
  }
  const input = event.target.closest("[data-label-input]");
  if (input) {
    renderLabelSuggestions(input.closest("[data-label-picker]"));
    if (input.closest("[data-transaction-table]")) markRowDirty(input.closest("tr"));
    if (input.closest("[data-budget-schedule-new-row]")) input.closest("tr").classList.add("dirty");
    const autoSubmitForm = input.closest("form[data-filter-auto-submit]");
    if (autoSubmitForm) scheduleFilterSubmit(autoSubmitForm);
    return;
  }
  const periodTagInput = event.target.closest("[data-period-tag-input]");
  if (periodTagInput && periodTagInput.value.includes(",")) {
    const parts = periodTagInput.value.split(",");
    periodTagInput.value = parts.pop() || "";
    const filter = periodTagInput.closest("[data-period-filter]");
    const added = parts.map((part) => addPeriodFilterTag(filter, part)).some(Boolean);
    if (added) submitPeriodFilterIfNeeded(filter);
  }
  const budgetScheduleInput = event.target.closest("[data-budget-schedule-field]");
  if (budgetScheduleInput) budgetScheduleInput.closest("tr")?.classList.add("dirty");
  const transactionCell = event.target.closest('[data-transaction-table] [data-save="transaction"]');
  if (transactionCell) {
    markRowDirty(transactionCell.closest("tr"));
    updateTransactionRunningBalances(transactionCell.closest("[data-transaction-table]"));
  }
});

document.querySelectorAll("[data-transaction-table]").forEach(updateTransactionRunningBalances);

document.addEventListener("mousedown", (event) => {
  if (event.target.closest("[data-label-suggestions]") || event.target.closest("[data-create-label]")) {
    event.preventDefault();
  }
});

document.addEventListener("dragstart", (event) => {
  const transactionRow = event.target.closest("[data-transaction-table] tbody tr[data-transaction-id]");
  const accountRow = event.target.closest('[data-settings-table][data-kind="account"] [data-settings-row]');
  if (transactionRow && transactionRow.dataset.newRow !== "true" && event.target.closest("[data-drag-handle]")) {
    transactionRow.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `transaction:${transactionRow.dataset.transactionId}`);
    return;
  }
  if (accountRow && accountRow.dataset.newRow !== "true" && event.target.closest("[data-account-drag-handle]")) {
    accountRow.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `account:${accountRow.dataset.id}`);
    return;
  }
  if (event.target.closest("[data-drag-handle], [data-account-drag-handle]")) {
    event.preventDefault();
  }
});

document.addEventListener("dragend", (event) => {
  event.target.closest("tr")?.classList.remove("dragging");
  document.querySelectorAll(".drag-over-before, .drag-over-after").forEach((row) => {
    row.classList.remove("drag-over-before", "drag-over-after");
  });
});

document.addEventListener("dragover", (event) => {
  const targetRow =
    event.target.closest("[data-transaction-table] tbody tr[data-transaction-id]") ||
    event.target.closest('[data-settings-table][data-kind="account"] [data-settings-row]');
  if (!targetRow) return;
  event.preventDefault();
  const rect = targetRow.getBoundingClientRect();
  const position = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  document.querySelectorAll(".drag-over-before, .drag-over-after").forEach((row) => {
    if (row !== targetRow) row.classList.remove("drag-over-before", "drag-over-after");
  });
  targetRow.classList.toggle("drag-over-before", position === "before");
  targetRow.classList.toggle("drag-over-after", position === "after");
});

document.addEventListener("drop", async (event) => {
  const targetRow =
    event.target.closest("[data-transaction-table] tbody tr[data-transaction-id]") ||
    event.target.closest('[data-settings-table][data-kind="account"] [data-settings-row]');
  if (!targetRow) return;
  event.preventDefault();
  const dragged = event.dataTransfer.getData("text/plain");
  const position = targetRow.classList.contains("drag-over-after") ? "after" : "before";
  targetRow.classList.remove("drag-over-before", "drag-over-after");
  if (dragged.startsWith("transaction:")) {
    const table = targetRow.closest("[data-transaction-table]");
    if (!table) return;
    const row = table.querySelector(`tr[data-transaction-id="${dragged.replace("transaction:", "")}"]`);
    await reorderTransactionRow(row, targetRow, position);
  }
  if (dragged.startsWith("account:")) {
    const table = targetRow.closest('[data-settings-table][data-kind="account"]');
    if (!table) return;
    const row = table.querySelector(`[data-settings-row][data-id="${dragged.replace("account:", "")}"]`);
    await reorderAccountRow(row, targetRow, position);
  }
});

document.addEventListener("click", async (event) => {
  if (!event.target.closest("[data-budget-account-list], [data-budget-schedule-confirm]")) {
    closeBudgetAccountLists();
  }
  if (!event.target.closest("[data-account-merge-list], [data-merge-account]")) {
    closeAccountMergeLists();
  }
  if (!event.target.closest("[data-period-filter]")) {
    document.querySelectorAll("[data-period-filter-menu]").forEach((menu) => {
      menu.hidden = true;
    });
  }

  const periodFilterToggle = event.target.closest("[data-period-filter-toggle]");
  if (periodFilterToggle) {
    const menu = periodFilterToggle.closest("[data-period-filter]")?.querySelector("[data-period-filter-menu]");
    if (menu) menu.hidden = !menu.hidden;
    return;
  }

  const periodFilterAll = event.target.closest("[data-period-filter-all]");
  if (periodFilterAll) {
    const filter = periodFilterAll.closest("[data-period-filter]");
    periodFilterCheckboxes(filter).forEach((checkbox) => {
      checkbox.checked = true;
    });
    syncPeriodFilter(filter, "all");
    submitPeriodFilterIfNeeded(filter);
    return;
  }

  const periodFilterNone = event.target.closest("[data-period-filter-none]");
  if (periodFilterNone) {
    const filter = periodFilterNone.closest("[data-period-filter]");
    periodFilterCheckboxes(filter).forEach((checkbox) => {
      checkbox.checked = false;
    });
    syncPeriodFilter(filter);
    submitPeriodFilterIfNeeded(filter);
    return;
  }

  const periodTagRemove = event.target.closest("[data-period-tag-remove]");
  if (periodTagRemove) {
    const filter = periodTagRemove.closest("[data-period-filter]");
    const tag = periodTagRemove.closest("[data-period-tag]");
    const checkbox = filter?.querySelector(`[data-period-filter-checkbox][value="${CSS.escape(tag?.dataset.periodTag || "")}"]`);
    if (checkbox) checkbox.checked = false;
    syncPeriodFilter(filter);
    submitPeriodFilterIfNeeded(filter);
    return;
  }

  const adminCreateToggle = event.target.closest("[data-admin-user-create-toggle]");
  if (adminCreateToggle) {
    openAdminUserCreateRow(adminCreateToggle);
    return;
  }

  const adminCreateCancel = event.target.closest("[data-admin-user-create-cancel]");
  if (adminCreateCancel) {
    cancelAdminUserCreateRow(adminCreateCancel);
    return;
  }

  const hideAccountTabButton = event.target.closest("[data-hide-account-tab]");
  if (hideAccountTabButton) {
    event.preventDefault();
    await hideAccountTab(hideAccountTabButton);
    return;
  }

  const deletePeriodButton = event.target.closest("[data-delete-period]");
  if (deletePeriodButton) {
    await deletePeriod(deletePeriodButton);
    return;
  }

  const periodCreateToggle = event.target.closest("[data-period-create-toggle]");
  if (periodCreateToggle) {
    openPeriodCreateCard(periodCreateToggle.closest("[data-period-create-card]"));
    return;
  }

  const periodCreateCancel = event.target.closest("[data-period-create-cancel]");
  if (periodCreateCancel) {
    cancelPeriodCreateCard(periodCreateCancel.closest("[data-period-create-card]"));
    return;
  }

  const periodNameDisplay = event.target.closest("[data-period-name-display]");
  if (periodNameDisplay) {
    openPeriodNameEditor(periodNameDisplay.closest("[data-period-name]"));
    return;
  }

  const confirmPeriodName = event.target.closest("[data-confirm-period-name]");
  if (confirmPeriodName) {
    await savePeriodName(confirmPeriodName.closest("[data-period-name]"));
    return;
  }

  const cancelPeriodName = event.target.closest("[data-cancel-period-name]");
  if (cancelPeriodName) {
    cancelPeriodNameEditor(cancelPeriodName.closest("[data-period-name]"));
    return;
  }

  const periodRangeDisplay = event.target.closest("[data-period-range-display]");
  if (periodRangeDisplay) {
    openPeriodRangeEditor(periodRangeDisplay.closest("[data-period-range]"));
    return;
  }

  const confirmPeriod = event.target.closest("[data-confirm-period]");
  if (confirmPeriod) {
    await savePeriodRange(confirmPeriod.closest("[data-period-range]"));
    return;
  }

  const cancelPeriod = event.target.closest("[data-cancel-period]");
  if (cancelPeriod) {
    cancelPeriodRangeEditor(cancelPeriod.closest("[data-period-range]"));
    return;
  }

  const balanceDisplay = event.target.closest("[data-balance-display]");
  if (balanceDisplay) {
    openAccountBalanceEditor(balanceDisplay.closest("[data-account-balance-cell]"));
    return;
  }

  const confirmAccountBalance = event.target.closest("[data-confirm-account-balance]");
  if (confirmAccountBalance) {
    await saveAccountBalanceEditor(confirmAccountBalance.closest("[data-account-balance-cell]"));
    return;
  }

  const cancelAccountBalance = event.target.closest("[data-cancel-account-balance]");
  if (cancelAccountBalance) {
    cancelAccountBalanceEditor(cancelAccountBalance.closest("[data-account-balance-cell]"));
    return;
  }

  const tabAddToggle = event.target.closest("[data-tab-add-toggle]");
  if (tabAddToggle) {
    const menu = tabAddToggle.closest(".tab-add-wrapper")?.querySelector("[data-tab-add-menu]");
    if (menu) menu.hidden = !menu.hidden;
    return;
  }
  if (!event.target.closest("[data-tab-add-menu]")) {
    document.querySelectorAll("[data-tab-add-menu]").forEach((menu) => {
      menu.hidden = true;
    });
  }

  const focusedTransactionRow = event.target.closest("[data-transaction-table] tr[data-transaction-id]");
  if (focusedTransactionRow && !focusedTransactionRow.classList.contains("dirty")) {
    focusRowDeleteAction(focusedTransactionRow);
  }
  const focusedSettingRow = event.target.closest("[data-settings-row]");
  if (focusedSettingRow && !focusedSettingRow.classList.contains("dirty")) {
    focusSettingDeleteAction(focusedSettingRow);
  }
  const focusedBudgetRow = event.target.closest("[data-budget-row]");
  if (focusedBudgetRow && !focusedBudgetRow.classList.contains("dirty")) {
    setBudgetActions(focusedBudgetRow, "delete");
  }

  const suggestion = event.target.closest("[data-label-suggestion]");
  if (suggestion) {
    const picker = suggestion.closest("[data-label-picker]");
    const input = picker.querySelector("[data-label-input]");
    input.value = suggestion.dataset.labelSuggestion;
    picker.querySelector("[data-label-suggestions]").hidden = true;
    const row = picker.closest("tr");
    if (row?.closest("[data-transaction-table]")) markRowDirty(row);
    else if (row?.closest("[data-monthly-budget-table]")) markBudgetDirty(row);
    else if (input.dataset.save) await saveCell(input);
    else if (input.closest("form[data-filter-auto-submit]")) submitFilterForm(input.closest("form"));
    return;
  }

  const addButton = event.target.closest("[data-create-label]");
  if (addButton) {
    await createLabelFromPicker(addButton.closest("[data-label-picker]"));
    return;
  }

  const addRow = event.target.closest("[data-add-row]");
  if (addRow) {
    createEmptyRow(addRow.closest("[data-transaction-table]"));
  }

  const removeAll = event.target.closest("[data-remove-all]");
  if (removeAll) {
    await clearTransactionTable(removeAll.closest("[data-transaction-table]"));
  }

  const confirmRow = event.target.closest("[data-confirm-row]");
  if (confirmRow) {
    await saveTransactionRow(confirmRow.closest("tr"));
  }

  const cancelRow = event.target.closest("[data-cancel-row]");
  if (cancelRow) {
    restoreRow(cancelRow.closest("tr"));
  }

  const deleteRow = event.target.closest("[data-delete-row]");
  if (deleteRow) {
    await deleteTransactionRow(deleteRow.closest("tr"));
  }

  const addSettingRow = event.target.closest("[data-add-setting-row]");
  if (addSettingRow) {
    createSettingRow(addSettingRow.closest("[data-settings-table]"));
  }

  const mergeAccount = event.target.closest("[data-merge-account]");
  if (mergeAccount) {
    toggleAccountMergeList(mergeAccount.closest("[data-settings-row]"));
    return;
  }

  const mergeAccountChoice = event.target.closest("[data-merge-target]");
  if (mergeAccountChoice) {
    await mergeAccountRow(mergeAccountChoice);
    return;
  }

  const deleteAccount = event.target.closest("[data-delete-account]");
  if (deleteAccount) {
    await deleteAccountRow(deleteAccount.closest("[data-settings-row]"));
    return;
  }

  const confirmSetting = event.target.closest("[data-confirm-setting]");
  if (confirmSetting) {
    await saveSettingRow(confirmSetting.closest("[data-settings-row]"));
  }

  const cancelSetting = event.target.closest("[data-cancel-setting]");
  if (cancelSetting) {
    restoreSettingRow(cancelSetting.closest("[data-settings-row]"));
  }

  const deleteSetting = event.target.closest("[data-delete-setting]");
  if (deleteSetting) {
    await deleteSettingRow(deleteSetting.closest("[data-settings-row]"));
  }

  const addBudgetRow = event.target.closest("[data-add-budget-row]");
  if (addBudgetRow) {
    createBudgetRow(addBudgetRow.closest("[data-monthly-budget-table]"));
  }

  const confirmBudget = event.target.closest("[data-confirm-budget]");
  if (confirmBudget) {
    await saveBudgetRow(confirmBudget.closest("[data-budget-row]"));
  }

  const cancelBudget = event.target.closest("[data-cancel-budget]");
  if (cancelBudget) {
    restoreBudgetRow(cancelBudget.closest("[data-budget-row]"));
  }

  const deleteBudget = event.target.closest("[data-delete-budget]");
  if (deleteBudget) {
    await deleteBudgetRow(deleteBudget.closest("[data-budget-row]"));
  }

  const budgetCancel = event.target.closest("[data-budget-schedule-cancel]");
  if (budgetCancel) {
    await cancelBudgetSchedule(budgetCancel.closest("[data-budget-schedule-id]"));
  }

  const budgetConfirm = event.target.closest("[data-budget-schedule-confirm]");
  if (budgetConfirm) {
    toggleBudgetAccountList(budgetConfirm.closest("[data-budget-schedule-id]"));
  }

  const budgetAccount = event.target.closest("[data-budget-account]");
  if (budgetAccount) {
    await instantiateBudgetSchedule(budgetAccount);
  }

  const addBudgetSchedule = event.target.closest("[data-add-budget-schedule]");
  if (addBudgetSchedule) {
    createBudgetScheduleRow(addBudgetSchedule.closest("[data-budget-schedule-table]"));
    return;
  }

  const clearBudgetScheduleButton = event.target.closest("[data-budget-schedule-clear]");
  if (clearBudgetScheduleButton) {
    await clearBudgetSchedule(clearBudgetScheduleButton.closest("[data-budget-schedule-table]"));
    return;
  }

  const confirmBudgetScheduleRow = event.target.closest("[data-confirm-budget-schedule-row]");
  if (confirmBudgetScheduleRow) {
    await saveBudgetScheduleRow(confirmBudgetScheduleRow.closest("[data-budget-schedule-new-row]"));
    return;
  }

  const cancelBudgetScheduleRowButton = event.target.closest("[data-cancel-budget-schedule-row]");
  if (cancelBudgetScheduleRowButton) {
    cancelBudgetScheduleRow(cancelBudgetScheduleRowButton.closest("[data-budget-schedule-new-row]"));
    return;
  }
});

document.addEventListener("submit", async (event) => {
  const loginForm = event.target.closest("[data-auth-login]");
  if (loginForm) {
    event.preventDefault();
    await submitAuthForm(loginForm, "login");
    return;
  }
  const registerForm = event.target.closest("[data-auth-register]");
  if (registerForm) {
    event.preventDefault();
    await submitAuthForm(registerForm, "register");
  }
});
