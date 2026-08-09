document.addEventListener("DOMContentLoaded", () => {
  const mainMedia = document.querySelector(
    "[data-product-main-media]"
  );

  if (!mainMedia) {
    return;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(
      "[data-product-image-button]"
    );

    if (!button) {
      return;
    }

    const imageUrl = button.dataset.imageUrl;
    const imageAlt = button.dataset.imageAlt || "";

    if (!imageUrl) {
      return;
    }

    const image = document.createElement("img");

    image.className = "shop-product-detail__image";
    image.src = imageUrl;
    image.alt = imageAlt;

    mainMedia.replaceChildren(image);

    document
      .querySelectorAll("[data-product-image-button]")
      .forEach((item) => {
        item.classList.remove("is-active");
      });

    button.classList.add("is-active");
  });
});