document.addEventListener("DOMContentLoaded", () => {

  function updateFullAlbumOption(variantForm) {
    const fulfilmentSelect = variantForm.querySelector(
        'select[name$="-fulfilment_type"]'
    );

    const fullAlbumOption = variantForm.querySelector(
        "[data-full-album-option]"
    );

    const fullAlbumCheckbox = variantForm.querySelector(
        'input[name$="-is_full_album_download"]'
    );

    if (!fulfilmentSelect || !fullAlbumOption) {
        return;
    }

    const isDigital = fulfilmentSelect.value === "digital";

    fullAlbumOption.hidden = !isDigital;

    if (!isDigital && fullAlbumCheckbox) {
        fullAlbumCheckbox.checked = false;
    }
}


document
    .querySelectorAll("[data-variant-form]")
    .forEach((variantForm) => {
        updateFullAlbumOption(variantForm);
    });


document.addEventListener("change", (event) => {
    if (
        !event.target.matches(
            'select[name$="-fulfilment_type"]'
        )
    ) {
        return;
    }

    const variantForm = event.target.closest(
        "[data-variant-form]"
    );

    if (variantForm) {
        updateFullAlbumOption(variantForm);
    }
});
  /*
   * =========================================================
   * VARIANTY PRODUKTU
   * =========================================================
   */

  const formset = document.querySelector("[data-variant-formset]");
  const addButton = document.querySelector("[data-add-variant]");
  const emptyTemplate = document.querySelector(
    "[data-empty-variant-form]"
  );

  if (formset && addButton && emptyTemplate) {
    const prefix = formset.dataset.prefix;

    const totalFormsInput = document.getElementById(
      `id_${prefix}-TOTAL_FORMS`
    );

    if (totalFormsInput) {
      const addVariant = () => {
        const formIndex = Number.parseInt(
          totalFormsInput.value,
          10
        );

        const newFormHtml = emptyTemplate.innerHTML.replace(
          /__prefix__/g,
          String(formIndex)
        );

        formset.insertAdjacentHTML(
          "beforeend",
          newFormHtml
        );

        totalFormsInput.value = String(formIndex + 1);

        const newVariantForm = formset.lastElementChild;

        if (
          newVariantForm &&
          newVariantForm.matches("[data-variant-form]")
        ) {
          updateFullAlbumOption(newVariantForm);
        }
      };

      addButton.addEventListener("click", addVariant);
    }
  }







  /*
   * =========================================================
   * OBRÁZKY VARIANT
   * =========================================================
   */

  document.addEventListener("click", (event) => {
    const addImageButton = event.target.closest(
      "[data-add-variant-image]"
    );

    if (!addImageButton) {
      return;
    }

    const imageFormset = addImageButton.closest(
      "[data-variant-image-formset]"
    );

    if (!imageFormset) {
      return;
    }

    const prefix = imageFormset.dataset.prefix;

    const imageList = imageFormset.querySelector(
      "[data-variant-image-list]"
    );

    const imageTemplate = imageFormset.querySelector(
      "[data-empty-variant-image-form]"
    );

    const totalFormsInput = document.getElementById(
      `id_${prefix}-TOTAL_FORMS`
    );

    if (
      !imageList ||
      !imageTemplate ||
      !totalFormsInput
    ) {
      return;
    }

    const formIndex = Number.parseInt(
      totalFormsInput.value,
      10
    );

    const newFormHtml = imageTemplate.innerHTML.replace(
      /__prefix__/g,
      String(formIndex)
    );

    imageList.insertAdjacentHTML(
      "beforeend",
      newFormHtml
    );

    totalFormsInput.value = String(formIndex + 1);
  });




  /*
  * =========================================================
  * NÁHLED VYBRANÉHO OBRÁZKU VARIANTY
  * =========================================================
  */

  document.addEventListener("change", (event) => {
    const select = event.target.closest(
      "[data-variant-image-select]"
    );

    if (!select) {
      return;
    }

    const imageForm = select.closest(
      "[data-variant-image-form]"
    );

    if (!imageForm) {
      return;
    }

    const preview = imageForm.querySelector(
      "[data-variant-image-preview]"
    );

    if (!preview) {
      return;
    }

    const previewImage = preview.querySelector(
      "[data-variant-image-preview-img]"
    );

    const emptyState = preview.querySelector(
      "[data-variant-image-preview-empty]"
    );

    const selectedOption = select.selectedOptions[0];

    const previewUrl = selectedOption
      ? selectedOption.dataset.previewUrl
      : "";

    if (previewUrl) {
      previewImage.src = previewUrl;
      previewImage.hidden = false;
      emptyState.hidden = true;
    } else {
      previewImage.src = "";
      previewImage.hidden = true;
      emptyState.hidden = false;
    }
  });





  /*
   * =========================================================
   * ODEBRÁNÍ VARIANTY / OBRÁZKU
   * =========================================================
   */

  document.addEventListener("click", (event) => {
    const removeVariantButton = event.target.closest(
      "[data-remove-variant]"
    );

    if (removeVariantButton) {
      const variantForm = removeVariantButton.closest(
        "[data-variant-form]"
      );

      if (variantForm) {
        const deleteInput = variantForm.querySelector(
          'input[name$="-DELETE"]'
        );

        if (deleteInput) {
          deleteInput.checked = true;
        }

        variantForm.hidden = true;
      }

      return;
    }

    const removeImageButton = event.target.closest(
      "[data-remove-variant-image]"
    );

    if (!removeImageButton) {
      return;
    }

    const imageForm = removeImageButton.closest(
      "[data-variant-image-form]"
    );

    if (!imageForm) {
      return;
    }

    const deleteInput = imageForm.querySelector(
      'input[name$="-DELETE"]'
    );

    if (deleteInput) {
      deleteInput.checked = true;
    }

    imageForm.hidden = true;
  });
});

