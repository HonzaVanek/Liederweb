document.addEventListener("DOMContentLoaded", function () {
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
});