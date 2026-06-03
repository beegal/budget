function setSaveState(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("save-error", isError);
}

function resetSaveState() {
  setSaveState(document.querySelector("[data-save-state]"), "Modifications à valider");
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
    payload.month_id = element.dataset.monthId;
    payload.account_id = element.dataset.accountId;
    payload.field = element.dataset.field;
  } else if (kind === "label") {
    const row = element.closest("[data-label-id]");
    payload.id = row.dataset.labelId;
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
  element.classList.add("saved");
  setSaveState(state, "Enregistré");
  setTimeout(() => element.classList.remove("saved"), 700);
}

async function saveTransactionRow(row) {
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-transaction-table]");
  const payload = {
    id: row.dataset.transactionId || null,
    month_id: table.dataset.monthId,
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
  setRowField(row, "date", result.date || "");
  setRowField(row, "sort_index", result.sort_index || "");
  setTransactionRowTone(row);
  delete row.dataset.newRow;
  row.classList.remove("dirty", "save-error");
  snapshotRow(row);
  setRowActions(row, false);
  insertTransactionRowSorted(row);
  applyTransactionIndexes(table, result.rows || []);
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
  setSaveState(state, "Supprimé");
}

async function clearTransactionTable(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, "Suppression...");
  const response = await fetch("/api/transaction-clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ month_id: table.dataset.monthId, account_id: table.dataset.accountId }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  table.querySelector("tbody").innerHTML = "";
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
  const amount = Number(getRowField(row, "amount").replace(",", "."));
  row.classList.remove("amount-positive", "amount-negative");
  if (amount > 0) row.classList.add("amount-positive");
  if (amount < 0) row.classList.add("amount-negative");
}

function transactionSortKey(row) {
  const date = getRowField(row, "date") || "9999-12-31";
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
    setRowField(row, "sort_index", item.sort_index || "");
    snapshotRow(row);
  }
  for (const item of rows) {
    const row = table.querySelector(`tr[data-transaction-id="${item.id}"]`);
    if (row) tbody.appendChild(row);
  }
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
  setRowField(row, "sort_index", result.sort_index || "");
  applyTransactionIndexes(table, result.rows || []);
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
  row.querySelector('[data-field="date"]').focus();
}

async function saveSettingRow(row) {
  const input = row.querySelector("[data-setting-value]");
  const value = input.value.trim();
  const kind = row.dataset.kind || row.closest("[data-settings-table]")?.dataset.kind;
  const response = await fetch(`/api/${kind}-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id || null, value }),
  });
  const result = await response.json();
  if (!result.ok) {
    input.classList.add("save-error");
    return;
  }
  row.dataset.id = result.id;
  delete row.dataset.newRow;
  input.value = result.value;
  input.dataset.original = result.value;
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
  input.classList.remove("save-error");
  row.classList.remove("dirty");
  setSettingActions(row, false);
  if (kind === "account") applyAccountIndexes(row.closest("[data-settings-table]"), result.rows || []);
  if (kind === "label") addLabelName(result.value);
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
  const input = row.querySelector("[data-setting-value]");
  setSaveState(state, "Suppression...");
  const response = await fetch(`/api/${kind}-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    input.classList.add("save-error");
    setSaveState(state, result.error || "Erreur", true);
    return;
  }
  row.remove();
  setSaveState(state, "Supprimé");
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
  const amount = Number((row.querySelector('[data-budget-field="amount"]')?.value || "").replace(",", "."));
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
  row.querySelector(".icon-status")?.remove();
  const list = row.querySelector("[data-budget-account-list]");
  if (list) list.hidden = true;
  flashSavedRow(row);
}

function toggleBudgetAccountList(row) {
  const list = row.querySelector("[data-budget-account-list]");
  if (!list) return;
  document.querySelectorAll("[data-budget-account-list]").forEach((candidate) => {
    if (candidate !== list) candidate.hidden = true;
  });
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
  row.querySelector("[data-budget-account-list]").hidden = true;
  if (output) {
    output.hidden = false;
    output.innerHTML = `Créé dans <a href="/period/${row.closest("[data-budget-schedule-table]").dataset.monthId}?account=${result.account_id}">${escapeHtml(result.account_name)}</a>, ligne #${escapeHtml(result.sort_index)} (${escapeHtml(result.date)})`;
  }
  flashSavedRow(row);
}

function createSettingRow(table) {
  const kind = table.dataset.kind;
  const placeholder = kind === "account" ? "Nouveau compte" : "Nouvel intitulé";
  const row = document.createElement("tr");
  row.dataset.settingsRow = "";
  row.dataset.kind = kind;
  row.dataset.newRow = "true";
  row.className = "dirty";
  row.innerHTML = `
    ${kind === "account" ? '<td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-account-index></span></td>' : ""}
    <td><input value="" data-setting-value data-original="" autocomplete="off" placeholder="${placeholder}"></td>
    ${kind === "account" ? '<td class="center-cell"><input type="checkbox" data-account-summary checked disabled></td><td class="center-cell"><input type="checkbox" data-account-visible-if-empty checked disabled></td>' : ""}
    <td class="row-actions">
      <button type="button" class="row-confirm" data-confirm-setting>V</button>
      <button type="button" class="row-cancel" data-cancel-setting>X</button>
      <button type="button" class="row-delete" data-delete-setting hidden>-</button>
    </td>`;
  table.querySelector("tbody").appendChild(row);
  row.querySelector("[data-setting-value]").focus();
}

function restoreSettingRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    return;
  }
  const input = row.querySelector("[data-setting-value]");
  input.value = input.dataset.original || "";
  input.classList.remove("save-error");
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
  else if (input.dataset.save) await saveCell(input);
}

document.addEventListener("focusin", (event) => {
  const editable = event.target.closest("[contenteditable][data-save]");
  if (editable) editable.dataset.before = editable.textContent.trim();
  const input = event.target.closest("input[data-save]");
  if (input) input.dataset.before = input.value.trim();
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
    return;
  }
  const transactionCell = event.target.closest('[data-transaction-table] [data-save="transaction"]');
  if (transactionCell) markRowDirty(transactionCell.closest("tr"));
});

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
    return;
  }

  const addButton = event.target.closest("[data-create-label]");
  if (addButton) {
    await createLabelFromPicker(addButton.closest("[data-label-picker]"));
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
});
