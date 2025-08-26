// Creates the main application object if it doesn't exist.
var ChatApp = window.ChatApp || {};

// This IIFE creates a private scope for our UI module.
(function () {
    // --- DEPENDENCIES ---
    // Establish a shorter alias for the utils module, which must be loaded first.
    const utils = ChatApp.utils;

    // --- PRIVATE VARIABLES (accessible only within this file) ---

    // const markedRenderer = new marked.Renderer();

    // Override the link rendering
    const renderer = new marked.Renderer();
    renderer.link = function (data) {
        console.log(data.href)
        const t = data.title ? ` title="${data.title}"` : "";
        return `<a href="${data.href}"${t} target="_blank" rel="noopener noreferrer">${data.text}</a>`;
    };

    marked.setOptions({ renderer });

    // DOM Element Selections
    const form = document.getElementById("form");
    const input = document.getElementById("input");
    const messages = document.getElementById("messages");
    const typingIndicator = document.getElementById("typing");

    const imageOption = document.getElementById("imageOption");
    const imagePreview = document.getElementById("imagePreview");
    const botCheckbox = document.getElementById("botCheckbox");
    const botQuestion = document.getElementById("botQuestion");
    const sendImageBtn = document.getElementById("sendImage");
    const cancelBtn = document.getElementById("cancelUpload");

    // UI State
    let missedCount = 0;
    const originalTitle = document.title;

    // --- PRIVATE FUNCTIONS (helper functions used only by this module) ---

    function scrollToBottom(force = false, minHeight = 200) {
        const atBottom =
            window.innerHeight + window.scrollY >=
            document.body.scrollHeight - minHeight;

        if (force || atBottom) {
            window.scrollTo({
                top: document.body.scrollHeight,
                behavior: "smooth",
            });
        }
    }

    // --- PUBLIC FUNCTIONS (will be exposed via ChatApp.ui) ---

    function addMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        // const formattedMessage = utils.linkify(message);
        const formattedMessage = marked.parseInline(
            HtmlSanitizer.SanitizeHtml(message)
        );
        const item = document.createElement("li");

        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
            nickname
        )}:</b> ${formattedMessage} <span id="timestamp">${utils.formatTime(
            timestamp
        )}</span>`;
        messages.appendChild(item);

        const elementHeight = item.offsetHeight;
        const dynamicThreshold = elementHeight + 200;
        scrollToBottom(false, dynamicThreshold);
    }

    function addHighlightedMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        const formattedMessage = utils.linkify(message);
        const item = document.createElement("li");
        item.classList.add("highlight");
        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
            nickname
        )}:</b> ${HtmlSanitizer.SanitizeHtml(
            formattedMessage
        )} <span id="timestamp">${utils.formatTime(timestamp)}</span>`;
        messages.appendChild(item);

        const elementHeight = item.offsetHeight;
        const dynamicThreshold = elementHeight + 200;
        scrollToBottom(false, dynamicThreshold);
    }

    function addSystemMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        const formattedMessage = utils.linkify(message);
        const item = document.createElement("li");
        item.innerHTML = `<b id="nickname">${nickname}:</b> ${formattedMessage} <span id="timestamp">${utils.formatTime(
            timestamp
        )}</span>`;
        messages.appendChild(item);

        const elementHeight = item.offsetHeight;
        const dynamicThreshold = elementHeight + 200;
        scrollToBottom(false, dynamicThreshold);
    }

    function addImageMessage(id, nickname, timestamp) {
        const item = document.createElement("li");
        const img = document.createElement("img");
        img.id = id;
        img.src = `/get_image/${id}`;
        img.alt = id;

        const anchor = document.createElement("a");
        anchor.href = `/get_image/${id}`;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        anchor.appendChild(img);

        const imagePromise = new Promise((resolve) => {
            img.onload = resolve;
            img.onerror = resolve; // Resolve on error too so the page still scrolls
        });

        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
            nickname
        )}:</b> `;
        item.appendChild(anchor);
        item.innerHTML += ` <span id="timestamp">${utils.formatTime(
            timestamp
        )}</span>`;

        messages.appendChild(item);

        imagePromise.then(() => {
            const elementHeight = item.offsetHeight;
            const dynamicThreshold = elementHeight + 50;
            scrollToBottom(false, dynamicThreshold);
        });
    }

    function addUserConnectedMessage(nickname) {
        const item = document.createElement("li");
        item.innerHTML = `Welcome! <b>${HtmlSanitizer.SanitizeHtml(
            nickname
        )}</b> has joined the chat.`;
        messages.appendChild(item);
        scrollToBottom();
    }

    function openImageOptions(file) {
        if (file.size > 5 * 1024 * 1024) {
            alert("No image larger than 5mb allowed!");
            return false; // Indicate failure
        }
        imageOption.style.display = "block";
        imagePreview.src = URL.createObjectURL(file);
        botCheckbox.checked = false;
        botQuestion.value = "";
        botQuestion.style.display = "none";

        // Stash the file on the DOM element for later retrieval
        imageOption._file = file;
        return true; // Indicate success
    }

    function closeImageOptions() {
        imageOption.style.display = "none";
        imagePreview.src = "";
        botQuestion.style.display = "none";
        document.getElementById("fileInput").value = null;
        delete imageOption._file;
    }

    function updateTitle() {
        document.title =
            missedCount > 0
                ? `(${missedCount}) ${originalTitle}`
                : originalTitle;
    }

    function updateTypingIndicator(users) {
        if (users.length === 0) {
            typingIndicator.innerHTML = "";
            typingIndicator.style.display = "none";
            return;
        }

        typingIndicator.style.display = "block";
        let text = "";
        if (users.length === 1) {
            text = `<b>${HtmlSanitizer.SanitizeHtml(users[0])}</b> is typing`;
        } else if (users.length === 2) {
            text = `<b>${HtmlSanitizer.SanitizeHtml(
                users[0]
            )}</b> and <b>${HtmlSanitizer.SanitizeHtml(
                users[1]
            )}</b> are typing`;
        } else {
            const last = users.pop();
            text = `${users
                .map((u) => `<b>${HtmlSanitizer.SanitizeHtml(u)}</b>`)
                .join(", ")}, and <b>${HtmlSanitizer.SanitizeHtml(
                last
            )}</b> are typing`;
        }
        typingIndicator.innerHTML = text;
    }

    // A dedicated function to attach event listeners owned by this module.
    function initializeEventListeners() {
        botCheckbox.addEventListener("change", () => {
            botQuestion.style.display = botCheckbox.checked ? "block" : "none";
        });
    }

    // Run the initialization
    initializeEventListeners();

    // --- PUBLIC INTERFACE ---
    // This is the "public shelf" for our UI module. Other files can only
    // access what we explicitly place here.
    ChatApp.ui = {
        // Expose DOM elements that other modules need to listen to or manipulate.
        form: form,
        input: input,
        messages: messages,
        imageOption: imageOption,
        botCheckbox: botCheckbox,
        botQuestion: botQuestion,
        sendImageBtn: sendImageBtn,
        cancelBtn: cancelBtn,

        // Expose functions that other modules need to call.
        addMessage: addMessage,
        addHighlightedMessage: addHighlightedMessage,
        addSystemMessage: addSystemMessage,
        addImageMessage: addImageMessage,
        addUserConnectedMessage: addUserConnectedMessage,
        openImageOptions: openImageOptions,
        closeImageOptions: closeImageOptions,
        updateTypingIndicator: updateTypingIndicator,
        clearChat: function () {
            messages.innerHTML = "";
        },

        // Expose functions to manage the UI state.
        scrollToBottom: scrollToBottom,
        updateTitle: updateTitle,
        incrementMissedCount: function () {
            missedCount++;
        },
        resetMissedCount: function () {
            missedCount = 0;
        },
    };
})();
