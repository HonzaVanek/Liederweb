document.addEventListener("DOMContentLoaded", function () {
  /*
   * Jednoduché formátování textového bloku
   */
  const toolbarButtons = document.querySelectorAll("[data-richtext-action]");

  function replaceSelection(textarea, replacement, selectionStart, selectionEnd) {
    const value = textarea.value;
    textarea.value =
      value.slice(0, selectionStart) +
      replacement +
      value.slice(selectionEnd);

    textarea.focus();
    textarea.selectionStart = selectionStart;
    textarea.selectionEnd = selectionStart + replacement.length;
  }

  function wrapSelection(textarea, before, after, placeholder) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.slice(start, end);
    const textToWrap = selectedText || placeholder;
    const replacement = before + textToWrap + after;

    replaceSelection(textarea, replacement, start, end);

    if (!selectedText) {
      textarea.selectionStart = start + before.length;
      textarea.selectionEnd = start + before.length + placeholder.length;
    }
  }

  function bulletSelection(textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.slice(start, end);

    if (!selectedText) {
      replaceSelection(textarea, "- ", start, end);
      textarea.selectionStart = start + 2;
      textarea.selectionEnd = start + 2;
      return;
    }

    const lines = selectedText.split(/\r?\n/);
    const replacement = lines
      .map(function (line) {
        if (!line.trim()) {
          return line;
        }

        if (/^\s*[-*]\s+/.test(line)) {
          return line;
        }

        return "- " + line;
      })
      .join("\n");

    replaceSelection(textarea, replacement, start, end);
  }

  function insertAtCursor(textarea, insertedText) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;

    replaceSelection(textarea, insertedText, start, end);

    textarea.selectionStart = start + insertedText.length;
    textarea.selectionEnd = start + insertedText.length;
  }

  toolbarButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const row = button.closest(".content-form-row");
      if (!row) {
        return;
      }

      const textarea = row.querySelector("textarea[data-content-richtext='1']");
      if (!textarea) {
        return;
      }

      const action = button.dataset.richtextAction;

      if (action === "bold") {
        wrapSelection(textarea, "**", "**", "tučný text");
      }

      if (action === "italic") {
        wrapSelection(textarea, "*", "*", "kurzíva");
      }

      if (action === "bullet") {
        bulletSelection(textarea);
      }

      if (action === "nbsp") {
        insertAtCursor(textarea, "&nbsp;");
      }
    });
  });

  /*
   * Přesun bloků bez reloadu stránky
   */
  const moveForms = document.querySelectorAll("[data-block-move-form]");

  function getCsrfToken(form) {
    const input = form.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  function renumberBlocks() {
    const cards = document.querySelectorAll("[data-content-block-card]");

    cards.forEach(function (card, index) {
      const number = card.querySelector(".content-block-number");
      if (number) {
        number.textContent = "#" + String(index + 1);
      }
    });
  }

  function updateMoveButtons() {
    const cards = Array.from(document.querySelectorAll("[data-content-block-card]"));

    cards.forEach(function (card, index) {
      const upButton = card.querySelector("[data-direction='up'] button");
      const downButton = card.querySelector("[data-direction='down'] button");

      if (upButton) {
        upButton.disabled = index === 0;
      }

      if (downButton) {
        downButton.disabled = index === cards.length - 1;
      }
    });
  }

  function moveCardInDom(card, direction) {
    if (direction === "up") {
      const previous = card.previousElementSibling;

      if (previous && previous.matches("[data-content-block-card]")) {
        card.parentNode.insertBefore(card, previous);
        return true;
      }
    }

    if (direction === "down") {
      const next = card.nextElementSibling;

      if (next && next.matches("[data-content-block-card]")) {
        card.parentNode.insertBefore(next, card);
        return true;
      }
    }

    return false;
  }

  moveForms.forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      const card = form.closest("[data-content-block-card]");
      const button = form.querySelector("button");
      const direction = form.dataset.direction;

      if (!card || !button || button.disabled) {
        return;
      }

      button.disabled = true;
      card.classList.add("content-block-card--moving");

      fetch(form.action, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(form),
        },
        body: new FormData(form),
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Move request failed");
          }

          return response.json();
        })
        .then(function (data) {
          if (!data.ok) {
            throw new Error("Move failed");
          }

          if (data.moved) {
            moveCardInDom(card, direction);
            renumberBlocks();
          }

          updateMoveButtons();
        })
        .catch(function () {
          /*
           * Když AJAX selže, radši použijeme původní fallback:
           * klasický POST s reloadem.
           */
          form.removeAttribute("data-block-move-form");
          form.submit();
        })
        .finally(function () {
          card.classList.remove("content-block-card--moving");
          updateMoveButtons();
        });
    });
  });

  updateMoveButtons();
});


// =========================================================
// Gallery image move – AJAX reorder
// =========================================================

document.addEventListener('DOMContentLoaded', function () {
  const galleryList = document.querySelector('.content-gallery-image-list')

  if (!galleryList) return

  function getCards() {
    return Array.from(galleryList.querySelectorAll('[data-gallery-image-card]'))
  }

  function refreshGalleryMoveButtons() {
    const cards = getCards()

    cards.forEach((card, index) => {
      const upButton = card.querySelector('[data-direction="up"] button')
      const downButton = card.querySelector('[data-direction="down"] button')

      if (upButton) {
        upButton.disabled = index === 0
      }

      if (downButton) {
        downButton.disabled = index === cards.length - 1
      }
    })
  }

  function getCsrfToken(form) {
    const input = form.querySelector('input[name="csrfmiddlewaretoken"]')
    return input ? input.value : ''
  }

  galleryList.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-gallery-image-move-form]')

    if (!form) return

    event.preventDefault()

    const card = form.closest('[data-gallery-image-card]')
    const direction = form.dataset.direction

    if (!card || !direction) {
      form.submit()
      return
    }

    card.classList.add('content-block-card--moving')

    fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCsrfToken(form),
      },
      body: new FormData(form),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Move failed')
        }

        return response.json()
      })
      .then(function (data) {
        if (!data.ok) {
          throw new Error('Move failed')
        }

        if (direction === 'up') {
          const previousCard = card.previousElementSibling

          if (previousCard) {
            galleryList.insertBefore(card, previousCard)
          }
        }

        if (direction === 'down') {
          const nextCard = card.nextElementSibling

          if (nextCard) {
            galleryList.insertBefore(nextCard, card)
          }
        }

        refreshGalleryMoveButtons()
      })
      .catch(function () {
        form.submit()
      })
      .finally(function () {
        card.classList.remove('content-block-card--moving')
      })
  })

  refreshGalleryMoveButtons()
})