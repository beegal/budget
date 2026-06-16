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

function showChartTooltip(point) {
  const chart = point?.closest(".summary-chart");
  const tooltip = chart?.querySelector("[data-chart-tooltip]");
  if (!chart || !tooltip) return;
  tooltip.textContent = point.dataset.tooltip || "";
  tooltip.hidden = false;
  positionChartTooltip(point, tooltip, chart);
}

function positionChartTooltip(point, tooltip, chart) {
  const pointRect = point.getBoundingClientRect();
  const chartRect = chart.getBoundingClientRect();
  const left = pointRect.left - chartRect.left + pointRect.width / 2;
  const top = pointRect.top - chartRect.top;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideChartTooltip(point) {
  const tooltip = point?.closest(".summary-chart")?.querySelector("[data-chart-tooltip]");
  if (tooltip) tooltip.hidden = true;
}

document.addEventListener("focusin", (event) => {
  const chartPoint = event.target.closest("[data-chart-point]");
  if (chartPoint) showChartTooltip(chartPoint);
  const editable = event.target.closest("[contenteditable][data-save]");
  if (editable) editable.dataset.before = editable.textContent.trim();
  const input = event.target.closest("input[data-save]");
  if (input) input.dataset.before = input.value.trim();
  const multiTagInput = event.target.closest("[data-multi-tag-input]");
  if (multiTagInput) {
    const filter = multiTagInput.closest("[data-multi-filter]");
    closeOpenMultiFilters(filter);
    const menu = filter?.querySelector("[data-multi-filter-menu]");
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
  const chartPoint = event.target.closest("[data-chart-point]");
  if (chartPoint) hideChartTooltip(chartPoint);
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
  const multiTagInput = event.target.closest("[data-multi-tag-input]");
  const multiFilterSearch = event.target.closest("[data-multi-filter-search]");

  if (event.key === "Enter" && multiFilterSearch) {
    event.preventDefault();
    return;
  }
  if ((event.key === "Enter" || event.key === ",") && multiTagInput) {
    event.preventDefault();
    const filter = multiTagInput.closest("[data-multi-filter]");
    const added = addMultiFilterTag(filter, multiTagInput.value);
    if (added) {
      multiTagInput.value = "";
      markMultiFilterDirty(filter);
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
  const languageSelect = event.target.closest("[data-language-selector]");
  if (languageSelect) {
    updateLanguageSelector(languageSelect);
    setLongLivedCookie("budget_language", languageSelect.value);
    window.location.reload();
    return;
  }

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
      csv_header: `${tr("common.date")},${tr("common.label")},${tr("common.amount")},${tr("common.comment")}\n${dateExample},Exemple,-12.50,Note`,
      csv_no_header: `${dateExample},Exemple,-12.50,Note`,
      tsv_header: `${tr("common.date")}\t${tr("common.label")}\t${tr("common.amount")}\t${tr("common.comment")}\n${dateExample}\tExemple\t-12.50\tNote`,
      tsv_no_header: `${dateExample}\tExemple\t-12.50\tNote`,
    };
    textarea.placeholder = placeholders[formatSelect?.value] || "";
  }

  const multiCheckbox = event.target.closest("[data-multi-filter-checkbox]");
  if (multiCheckbox) {
    const filter = multiCheckbox.closest("[data-multi-filter]");
    syncMultiFilter(filter);
    markMultiFilterDirty(filter);
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
  const multiTagInput = event.target.closest("[data-multi-tag-input]");
  if (multiTagInput && multiTagInput.value.includes(",")) {
    const parts = multiTagInput.value.split(",");
    multiTagInput.value = parts.pop() || "";
    const filter = multiTagInput.closest("[data-multi-filter]");
    const added = parts.map((part) => addMultiFilterTag(filter, part)).some(Boolean);
    if (added) markMultiFilterDirty(filter);
  }
  const multiFilterSearch = event.target.closest("[data-multi-filter-search]");
  if (multiFilterSearch) {
    filterMultiFilterOptions(multiFilterSearch.closest("[data-multi-filter]"));
    return;
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

document.addEventListener("pointerover", (event) => {
  const chartPoint = event.target.closest("[data-chart-point]");
  if (chartPoint) showChartTooltip(chartPoint);
});

document.addEventListener("pointerout", (event) => {
  const chartPoint = event.target.closest("[data-chart-point]");
  if (chartPoint) hideChartTooltip(chartPoint);
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
  const multiFilterToggle = event.target.closest("[data-multi-filter-toggle]");
  if (multiFilterToggle) {
    const filter = multiFilterToggle.closest("[data-multi-filter]");
    const menu = filter?.querySelector("[data-multi-filter-menu]");
    if (menu && !menu.hidden) closeMultiFilter(filter);
    else {
      closeOpenMultiFilters(filter);
      if (menu) {
        menu.hidden = false;
        const search = filter.querySelector("[data-multi-filter-search]");
        if (search) search.focus();
      }
    }
    return;
  }

  if (!event.target.closest("[data-multi-filter]")) {
    closeOpenMultiFilters();
  }

  const multiFilterAll = event.target.closest("[data-multi-filter-all]");
  if (multiFilterAll) {
    const filter = multiFilterAll.closest("[data-multi-filter]");
    multiFilterCheckboxes(filter).forEach((checkbox) => {
      checkbox.checked = true;
    });
    syncMultiFilter(filter, "all");
    markMultiFilterDirty(filter);
    return;
  }

  const multiFilterNone = event.target.closest("[data-multi-filter-none]");
  if (multiFilterNone) {
    const filter = multiFilterNone.closest("[data-multi-filter]");
    multiFilterCheckboxes(filter).forEach((checkbox) => {
      checkbox.checked = false;
    });
    syncMultiFilter(filter, "none");
    markMultiFilterDirty(filter);
    return;
  }

  const multiTagRemove = event.target.closest("[data-multi-tag-remove]");
  if (multiTagRemove) {
    const filter = multiTagRemove.closest("[data-multi-filter]");
    const tag = multiTagRemove.closest("[data-multi-tag]");
    const checkbox = filter?.querySelector(`[data-multi-filter-checkbox][value="${CSS.escape(tag?.dataset.multiTag || "")}"]`);
    if (checkbox) checkbox.checked = false;
    syncMultiFilter(filter);
    markMultiFilterDirty(filter);
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
    renderLabelSuggestions(picker);
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

  const addRecurringBudget = event.target.closest("[data-add-recurring-budget]");
  if (addRecurringBudget) {
    await addRecurringBudgetCandidate(addRecurringBudget);
    return;
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
