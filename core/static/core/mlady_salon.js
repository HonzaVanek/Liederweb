document.addEventListener("DOMContentLoaded", () => {
    const formDialog = document.getElementById(
        "salon-application-dialog"
    );

    const successDialog = document.getElementById(
        "salon-success-dialog"
    );

    document
        .querySelectorAll("[data-open-salon-form]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                formDialog?.showModal();
            });
        });

    document
        .querySelectorAll("[data-close-salon-form]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                formDialog?.close();
            });
        });

    document
        .querySelectorAll("[data-close-success]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                successDialog?.close();
            });
        });

    [formDialog, successDialog].forEach((dialog) => {
        if (!dialog) {
            return;
        }

        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) {
                dialog.close();
            }
        });
    });

    if (successDialog) {
        successDialog.showModal();
    }
});