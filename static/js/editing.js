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
    const row = element.closest("[data-label-id], [data-settings-row][data-kind='label']");
    payload.id = labelRowId(row);
    payload.field = element.dataset.field || "name";
  } else if (kind === "period-date") {
    payload.id = element.dataset.id;
    payload.field = element.dataset.field;
  } else {
    payload.id = element.dataset.id;
  }

  element.classList.add("saving");
  setSaveState(state, tr("js.saving"));

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  element.classList.remove("saving");

  if (!result.ok) {
    element.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
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
  setSaveState(state, tr("js.saved"));
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
  setSaveState(state, tr("js.saving"));
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
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  const savedValue = result.value || "";
  cell.dataset.original = savedValue;
  if (input) input.value = savedValue;
  if (display) {
    display.textContent = result.display || tr("period.unknown");
    display.classList.toggle("balance-undefined", !savedValue);
    display.hidden = false;
  }
  if (editor) editor.hidden = true;
  setAccountBalanceTone(cell, savedValue);
  const currentCell = cell.closest("tr")?.querySelector("[data-account-current-cell]");
  if (currentCell) {
    currentCell.textContent = result.current_display || tr("period.unknown");
    currentCell.classList.toggle("balance-undefined", !result.current);
    setAccountBalanceTone(currentCell, result.current || "");
  }
  cell.classList.remove("save-error");
  setSaveState(state, tr("js.saved"));
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
    setSaveState(document.querySelector("[data-save-state]"), result.error || tr("js.save-error"), true);
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

  setSaveState(state, tr("js.saving"));
  const response = await fetch("/api/transaction-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
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
  setSaveState(state, result.budget_message || tr("js.saved"));
}

async function deleteTransactionRow(row) {
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-transaction-table]");
  if (row.dataset.newRow === "true") {
    row.remove();
    return;
  }
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/transaction-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.transactionId }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  row.remove();
  applyTransactionIndexes(table, result.rows || []);
  updateTransactionRunningBalances(table);
  setSaveState(state, tr("js.deleted"));
}

async function clearTransactionTable(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/transaction-clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId, account_id: table.dataset.accountId }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  table.querySelector("tbody").innerHTML = "";
  updateTransactionRunningBalances(table);
  setSaveState(state, tr("js.deleted"));
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
  setSaveState(state, tr("js.reordering"));
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
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  setRowField(row, "date", result.date || "");
  row.dataset.sortDate = result.date_sort || "";
  setRowField(row, "sort_index", result.sort_index || "");
  applyTransactionIndexes(table, result.rows || []);
  updateTransactionRunningBalances(table);
  row.classList.remove("save-error");
  flashSavedRow(row);
  setSaveState(state, tr("js.order-saved"));
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
    <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-drag-handle title="${tr("period.move")}">↕</button><span class="row-index-value" data-field="sort_index" data-original=""></span></td>
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
  const oldValue = settingRowOriginalValue(row, kind);
  const response = await fetch(`/api/${kind}-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: settingRowId(row, kind), value }),
  });
  const result = await response.json();
  if (!result.ok) {
    inputs.forEach((input) => input.classList.add("save-error"));
    return;
  }
  row.dataset.id = result.id;
  if (kind === "label") row.dataset.labelId = result.id;
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
  if (kind === "label") replaceLabelName(oldValue, result.value);
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

function settingRowOriginalValue(row, kind) {
  if (kind !== "label") return row.querySelector("[data-setting-value]")?.dataset.original || "";
  const group = row.querySelector('[data-setting-part="group"]')?.dataset.original || "";
  const subcategory = row.querySelector('[data-setting-part="subcategory"]')?.dataset.original || "";
  return subcategory ? `${group} - ${subcategory}` : group;
}

function labelRowId(row) {
  return row?.dataset.labelId || row?.dataset.id || null;
}

function settingRowId(row, kind) {
  if (row.dataset.newRow === "true") return null;
  return kind === "label" ? labelRowId(row) : row.dataset.id || null;
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
  const oldValue = settingRowOriginalValue(row, kind);
  setSaveState(state, tr("js.deleting"));
  const response = await fetch(`/api/${kind}-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: settingRowId(row, kind) }),
  });
  const result = await response.json();
  if (!result.ok) {
    inputs.forEach((input) => input.classList.add("save-error"));
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  row.remove();
  if (kind === "label") removeLabelName(oldValue);
  setSaveState(state, tr("js.deleted"));
}

async function deleteUnusedLabelRows(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/label-delete-unused", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  const deleted = result.deleted || [];
  for (const label of deleted) {
    table?.querySelector(`[data-settings-row][data-label-id="${label.id}"]`)?.remove();
    removeLabelName(label.name);
  }
  setSaveState(state, `${tr("js.deleted")} (${result.count || 0})`);
}

async function deleteAccountRow(row) {
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/account-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.querySelector("[data-setting-value]")?.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  row.remove();
  applyAccountIndexes(document.querySelector('[data-settings-table][data-kind="account"]'), result.rows || []);
  setSaveState(state, tr("js.deleted"));
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
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  row.remove();
  closeAccountMergeLists();
  applyAccountIndexes(document.querySelector('[data-settings-table][data-kind="account"]'), result.rows || []);
  setSaveState(state, tr("js.account-merged"));
}

async function reorderAccountRow(row, targetRow, position) {
  if (!row || !targetRow || row === targetRow || row.dataset.newRow === "true") return;
  const state = document.querySelector("[data-save-state]");
  const table = row.closest("[data-settings-table]");
  setSaveState(state, tr("js.reordering"));
  const response = await fetch("/api/account-reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id, target_id: targetRow.dataset.id, position }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.querySelector("[data-setting-value]")?.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  applyAccountIndexes(table, result.rows || []);
  flashSavedRow(row);
  setSaveState(state, tr("js.order-saved"));
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
  setSaveState(state, tr("js.saving"));
  const response = await fetch("/api/monthly-budget-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
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
  sortBudgetRows(row.closest("[data-monthly-budget-table]"));
  updateBudgetTotal(row.closest("[data-monthly-budget-table]"));
  setSaveState(state, tr("js.saved"));
}

function sortBudgetRows(table) {
  const tbody = table?.querySelector("tbody");
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll("[data-budget-row]"));
  rows.sort((left, right) => {
    const leftDay = Number(left.querySelector('[data-budget-field="day"]')?.value || 0);
    const rightDay = Number(right.querySelector('[data-budget-field="day"]')?.value || 0);
    if (leftDay !== rightDay) return leftDay - rightDay;
    const leftLabel = left.querySelector('[data-budget-field="label"]')?.value || "";
    const rightLabel = right.querySelector('[data-budget-field="label"]')?.value || "";
    return leftLabel.localeCompare(rightLabel, displayLocale());
  });
  rows.forEach((budgetRow) => tbody.appendChild(budgetRow));
}

async function deleteBudgetRow(row) {
  const state = document.querySelector("[data-save-state]");
  if (row.dataset.newRow === "true") {
    row.remove();
    resetSaveState();
    return;
  }
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/monthly-budget-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: row.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  row.remove();
  updateBudgetTotal(document.querySelector("[data-monthly-budget-table]"));
  setSaveState(state, tr("js.deleted"));
}

function updateBudgetTotal(table) {
  const totalCell = table?.querySelector("[data-monthly-budget-total]");
  if (!totalCell) return;
  const total = Array.from(table.querySelectorAll("[data-budget-row]"))
    .reduce((sum, row) => sum + parseDisplayNumber(row.querySelector('[data-budget-field="amount"]')?.value || ""), 0);
  totalCell.textContent = formatDisplayMoney(total, numberDecimals());
  totalCell.classList.toggle("positive", total > 0);
  totalCell.classList.toggle("negative", total < 0);
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

async function addRecurringBudgetCandidate(button) {
  const table = document.querySelector("[data-monthly-budget-table]");
  if (!table) return;
  createBudgetRow(table);
  const rows = table.querySelectorAll("[data-budget-row]");
  const row = rows[rows.length - 1];
  setBudgetField(row, "day", button.dataset.day || "");
  setBudgetField(row, "label", button.dataset.label || "");
  setBudgetField(row, "amount", button.dataset.amount || "");
  await saveBudgetRow(row);
  if (row.classList.contains("save-error")) return;
  button.closest("tr")?.remove();
  const candidateRows = document.querySelectorAll("[data-recurring-budget-tool] tbody tr");
  if (candidateRows.length === 0) window.location.reload();
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
  if (status) status.textContent = result.status_label || tr("js.canceled");
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
      output.textContent = result.error || tr("js.save-error");
    }
    return;
  }
  row.classList.remove("save-error");
  row.classList.remove("budget-status-scheduled", "budget-status-cancel");
  row.classList.add("budget-status-found");
  const status = row.querySelector("[data-budget-status]");
  if (status) status.textContent = result.status_label || tr("js.found");
  row.querySelector("[data-budget-schedule-cancel]")?.remove();
  row.querySelector("[data-budget-schedule-confirm]")?.remove();
  row.querySelector("[data-budget-account-list]").hidden = true;
  if (output) {
    output.hidden = false;
    output.innerHTML = `${escapeHtml(tr("js.created-in"))} <a href="/period/${row.closest("[data-budget-schedule-table]").dataset.periodId}?account=${result.account_id}">${escapeHtml(result.account_name)}</a>, ligne #${escapeHtml(result.sort_index)} (${escapeHtml(result.date)})`;
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
  setSaveState(state, tr("js.saving"));
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
    setSaveState(state, result.error || tr("js.save-error"), true);
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
  setSaveState(state, tr("js.saving"));
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
    setSaveState(state, result.error || tr("js.save-error"), true);
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
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/period-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: button.dataset.id }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || tr("js.save-error"), true);
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
    <td><span class="budget-status-pill">${tr("period.status-scheduled")}</span></td>
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
  setSaveState(state, tr("js.saving"));
  const response = await fetch("/api/budget-schedule-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId, label, amount }),
  });
  const result = await response.json();
  if (!result.ok) {
    row.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  window.location.reload();
}

async function clearBudgetSchedule(table) {
  const state = document.querySelector("[data-save-state]");
  setSaveState(state, tr("js.deleting"));
  const response = await fetch("/api/budget-schedule-clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period_id: table.dataset.periodId }),
  });
  const result = await response.json();
  if (!result.ok) {
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }
  window.location.reload();
}

function createSettingRow(table) {
  const kind = table.dataset.kind;
  const valueCells = kind === "label"
    ? `<td><input value="" data-setting-value data-setting-part="group" data-original="" autocomplete="off" placeholder="${tr("parameters.group-name")}"></td>
    <td><input value="" data-setting-value data-setting-part="subcategory" data-original="" autocomplete="off" placeholder="${tr("parameters.subcategory")}"></td>`
    : `<td><input value="" data-setting-value data-original="" autocomplete="off" placeholder="${tr("parameters.new-account")}"></td>`;
  const row = document.createElement("tr");
  row.dataset.settingsRow = "";
  row.dataset.kind = kind;
  row.dataset.newRow = "true";
  row.className = "dirty";
  row.innerHTML = `
    ${kind === "account" ? `<td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="${tr("period.move")}">↕</button></td>` : ""}
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
      <input value="${escapeHtml(value)}" data-original="${escapeHtml(value)}" autocomplete="off" placeholder="${escapeHtml(tr("filters.label-placeholder"))}" ${attrs} data-label-input>
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
    window.BUDGET_LABELS.sort((a, b) => a.localeCompare(b, displayLocale()));
  }
}

function removeLabelName(name) {
  const oldNeedle = normalized(name);
  window.BUDGET_LABELS = labelNames().filter((label) => normalized(label) !== oldNeedle);
}

function replaceLabelName(oldName, newName) {
  if (oldName) removeLabelName(oldName);
  addLabelName(newName);
}

async function createLabelFromPicker(picker) {
  const input = picker.querySelector("[data-label-input]");
  const state = document.querySelector("[data-save-state]");
  const value = input.value.trim();
  if (!value) return;

  setSaveState(state, tr("js.label-creating"));
  const response = await fetch("/api/label-from-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  const result = await response.json();
  if (!result.ok) {
    input.classList.add("save-error");
    setSaveState(state, result.error || tr("js.save-error"), true);
    return;
  }

  if (!result.hidden) addLabelName(result.label.name);
  input.value = result.label.name;
  renderLabelSuggestions(picker);
  const row = picker.closest("tr");
  if (row?.closest("[data-transaction-table]")) markRowDirty(row);
  else if (row?.closest("[data-monthly-budget-table]")) markBudgetDirty(row);
  else if (row?.closest("[data-budget-schedule-table]")) row.classList.add("dirty");
  else if (input.dataset.save) await saveCell(input);
}
