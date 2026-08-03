document.addEventListener("DOMContentLoaded", () => {
  const formset = document.querySelector("[data-variant-formset]");
  const addButton = document.querySelector("[data-add-variant]");
  const emptyTemplate = document.querySelector("[data-empty-variant-form]");

  if (!formset || !addButton || !emptyTemplate) {
    return;
  }

  const prefix = formset.dataset.prefix;
  const totalFormsInput = document.getElementById(
    `id_${prefix}-TOTAL_FORMS`
  );

  if (!totalFormsInput) {
    return;
  }

  const addVariant = () => {
    const formIndex = Number.parseInt(totalFormsInput.value, 10);

    const newFormHtml = emptyTemplate.innerHTML.replace(
      /__prefix__/g,
      String(formIndex)
    );

    formset.insertAdjacentHTML("beforeend", newFormHtml);
    totalFormsInput.value = String(formIndex + 1);
  };

  const removeVariant = (button) => {
    const variantForm = button.closest("[data-variant-form]");

    if (!variantForm) {
      return;
    }

    const deleteInput = variantForm.querySelector(
      'input[name$="-DELETE"]'
    );

    if (deleteInput) {
      deleteInput.checked = true;
    }

    variantForm.hidden = true;
  };

  addButton.addEventListener("click", addVariant);

  document.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-variant]");

    if (!removeButton) {
      return;
    }

    removeVariant(removeButton);
  });
});