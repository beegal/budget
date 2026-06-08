function multiFilterCheckboxes(filter) {
  if (!filter) return [];
  return Array.from(filter.querySelectorAll("[data-multi-filter-checkbox]"));
}

function multiFilterSelectedIds(filter) {
  return multiFilterCheckboxes(filter)
    .filter((checkbox) => checkbox.checked)
    .map((checkbox) => checkbox.value);
}

function renderMultiFilterTags(filter) {
  if (!filter) return;
  const tagBox = filter.querySelector("[data-multi-tag-box]");
  const input = filter.querySelector("[data-multi-tag-input]");
  if (!tagBox || !input) return;
  tagBox.querySelectorAll("[data-multi-tag]").forEach((tag) => tag.remove());
  multiFilterCheckboxes(filter)
    .filter((checkbox) => checkbox.checked)
    .forEach((checkbox) => {
      const tag = document.createElement("span");
      tag.className = "multi-filter-tag";
      tag.dataset.multiTag = checkbox.value;
      tag.textContent = checkbox.dataset.multiName || checkbox.value;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.dataset.multiTagRemove = "";
      remove.setAttribute("aria-label", `Retirer ${tag.textContent}`);
      remove.textContent = "x";
      tag.appendChild(remove);
      tagBox.insertBefore(tag, input);
    });
}

function syncMultiFilter(filter, mode = "explicit") {
  if (!filter) return;
  const hidden = filter.querySelector("[data-multi-filter-value]");
  const checkboxes = multiFilterCheckboxes(filter);
  const selectedIds = multiFilterSelectedIds(filter);
  if (hidden) {
    if (mode === "all" || (checkboxes.length > 0 && selectedIds.length === checkboxes.length)) hidden.value = "all";
    else if (selectedIds.length === 0) hidden.value = "all";
    else hidden.value = selectedIds.join(",");
  }
  renderMultiFilterTags(filter);
}

function addMultiFilterTag(filter, value) {
  if (!filter) return false;
  const needle = normalized(value);
  if (!needle) return false;
  const checkboxes = multiFilterCheckboxes(filter);
  const match = checkboxes.find((checkbox) => normalized(checkbox.dataset.multiName || "") === needle)
    || checkboxes.find((checkbox) => normalized(checkbox.value) === needle)
    || checkboxes.find((checkbox) => normalized(checkbox.dataset.multiName || "").includes(needle));
  if (!match) return false;
  match.checked = true;
  syncMultiFilter(filter);
  return true;
}

function markMultiFilterDirty(filter) {
  if (!filter?.closest("form[data-multi-auto-submit]")) return;
  filter.dataset.multiFilterDirty = "true";
}

function submitMultiFilterIfDirty(filter) {
  const form = filter?.closest("form[data-multi-auto-submit]");
  if (!form || filter.dataset.multiFilterDirty !== "true") return;
  delete filter.dataset.multiFilterDirty;
  submitFilterForm(form);
}

function closeMultiFilter(filter) {
  const menu = filter?.querySelector("[data-multi-filter-menu]");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  submitMultiFilterIfDirty(filter);
}

function closeOpenMultiFilters(exceptFilter = null) {
  document.querySelectorAll("[data-multi-filter]").forEach((filter) => {
    if (filter !== exceptFilter) closeMultiFilter(filter);
  });
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

