(function () {
    "use strict";

    const SCRIPT_URL =
        "https://dv-ai-quiz-generator.onrender.com/embed.js";

    const script =
        document.currentScript ||
        document.querySelector('script[src="' + SCRIPT_URL + '"]');

    if (!script) {
        console.error("DV AI Quiz Generator: embed script not found.");
        return;
    }

    // Prevent duplicate widgets
    if (document.getElementById("dv-ai-quiz-generator-widget")) {
        return;
    }

    const container = document.createElement("div");
    container.id = "dv-ai-quiz-generator-widget";

    container.style.width = "100%";
    container.style.maxWidth = "1200px";
    container.style.margin = "20px auto";
    container.style.position = "relative";

    const iframe = document.createElement("iframe");

    iframe.src = "https://dv-ai-quiz-generator.onrender.com/";
    iframe.title = "DV Digital AI Quiz Generator";
    iframe.loading = "lazy";

    iframe.style.width = "100%";
    iframe.style.height = "900px";
    iframe.style.border = "0";
    iframe.style.display = "block";
    iframe.style.borderRadius = "12px";
    iframe.style.background = "transparent";

    iframe.setAttribute(
        "allow",
        "clipboard-write"
    );

    container.appendChild(iframe);

    script.parentNode.insertBefore(container, script.nextSibling);
})();