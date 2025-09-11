// Creates the main application object if it doesn't exist.
var ChatApp = window.ChatApp || {};

// We wrap our main logic in a DOMContentLoaded listener.
// This is a best practice that ensures all HTML elements are loaded
// before our JavaScript tries to find and use them.
document.addEventListener("DOMContentLoaded", function () {
    cloak();
    // --- DEPENDENCIES ---
    // Establish shorter, readable aliases for the other modules.
    const ui = ChatApp.ui;
    const socket = ChatApp.socket.instance; // Note: we get the 'instance' property
    const utils = ChatApp.utils;

    const testingMode = false;

    // --- PRIVATE STATE (for this file only) ---
    let typing = false;
    let lastTypingTime = 0;
    const TYPING_TIMER_LENGTH = 2000; // 2 seconds

    let emoji = new EmojiConvertor();
    // emoji.text_mode = true;
    emoji.replace_mode = "unified";
    emoji.allow_native = true;

    // --- INITIALIZATION ---

    // 1. Set up the socket event listeners (for receiving messages, etc.)
    ChatApp.socket.initializeListeners();

    // 2. Fetch the initial chat logs from the server
    fetch("/get_chatlogs", { credentials: "include" })
        .then((res) => res.json())
        .then((data) => {
            const renderComplete = [];

            data.forEach((entry) => {
                if (
                    entry == null ||
                    entry.type == null ||
                    entry.nickname == null ||
                    entry.timestamp == null ||
                    (entry.type !== "image" && entry.message == null)
                ) {
                    // console.log("Invalid entry:", entry);
                    return;
                }

                if (entry.type === "image") {
                    const item = document.createElement("li");
                    const anchor = document.createElement("a");
                    const img = document.createElement("img");


                    const imageUri = `/get_image/${entry.id}`;
                    anchor.href = imageUri;

                    if (inDangerMode === true && testingMode === true) {
                        // In Danger Mode, we want to cloak the URL on click.
                        anchor.addEventListener("click", function (event) {
                            // Prevent the browser from following the link normally.
                            event.preventDefault();

                            // Call the cloakURL function with the image's URL.
                            if (typeof cloakURL === "function") {
                                cloakURL(imageUri);
                            } else {
                                console.error("Error: cloakURL() is not defined.");
                            }
                        });
                    } else {
                        // In normal mode, the link should open in a new, uncloaked tab.
                        anchor.target = "_blank";
                        anchor.rel = "noopener noreferrer";
                    }

                    // img.loading = "lazy";
                    img.id = entry.id;
                    img.src = imageUri;

                    const imageLoad = new Promise((resolve) => {
                        // img.onload = resolve;
                        img.onload = resolve;
                        img.onerror = resolve;
                    });

                    anchor.appendChild(img);

                    item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
                        entry.nickname
                    )}: </b>`;
                    item.appendChild(anchor);
                    item.innerHTML += ` <span id="timestamp">${utils.formatTime(
                        entry.timestamp
                    )}</span>`;

                    messages.appendChild(item);
                    renderComplete.push(imageLoad);
                } else if (entry.type === "highlight") {
                    const p = new Promise((resolve) => {
                        ui.addHighlightedMessage(
                            entry.message,
                            entry.nickname,
                            entry.timestamp
                        );
                        requestAnimationFrame(resolve);
                    });
                    renderComplete.push(p);
                } else if (entry.type === "system") {
                    const p = new Promise((resolve) => {
                        ui.addSystemMessage(
                            entry.message,
                            entry.nickname,
                            entry.timestamp
                        );
                        requestAnimationFrame(resolve);
                    });
                    renderComplete.push(p);
                } else {
                    const p = new Promise((resolve) => {
                        ui.addMessage(
                            entry.message,
                            entry.nickname,
                            entry.timestamp
                        );
                        requestAnimationFrame(resolve);
                    });
                    renderComplete.push(p);
                }
            });

            Promise.all(renderComplete)
                .then(() => {
                    // console.log("Maybe")
                    requestAnimationFrame(() => {
                        // console.log('Forcing scroll after initial load (rAF)'); // For debugging
                        ui.scrollToBottom(true); // Now force scroll
                    });
                    // scrollToBottom(true); // Ensure full scroll after all items load/render
                })
                .catch((error) => {
                    // It's good practice to catch potential errors from Promise.all
                    console.error(
                        "Error during initial message rendering:",
                        error
                    );
                    // You might still want to attempt a scroll even if some elements failed
                    requestAnimationFrame(() => {
                        // console.log('Forcing scroll after initial load (rAF in catch)'); // For debugging
                        ui.scrollToBottom(true);
                    });
                });
        });

    // --- EVENT LISTENERS (The "Glue") ---

    // Handle form submission for sending messages
    ui.form.addEventListener("submit", (e) => {
        e.preventDefault();
        if (typing) {
            socket.emit("stop_typing", {
                // nickname: utils.getCookie("nickname"),
            });
            typing = false;
        }

        if (ui.readyJumpscare === true) {
            ui.triggerJumpscare();
            ui.readyJumpscare = false;
            socket.emit("user_jumpscared", {});
        }

        if (ui.readyCrash === true) {
            window.open(`https://${location.hostname}/crash`, '_blank');
            ui.readyCrash = false;
            socket.emit("user_crashed", {});
        }

        //* Handle client side slash commands...

        if (ui.input.value.startsWith("/cloak ")) {
            ui.input.value = "";
            url = ui.input.value.replace("/cloak ", "").trim();
            cloakURL(url);
            return;
        }
        if (ui.input.value === "/refresh" || ui.input.value === "/reload") {
            location.reload();
            return;
        }
        if (ui.input.value === "/gamble") {
            openURI("game-gamble-d6eca0");
            ui.input.value = "";
            return;
        }

        // Send the chat message
        if (ui.input.value) {
            var contents = ui.input.value;
            contents = emoji.replace_colons(contents);
            // console.log(contents)
            socket.emit("chat_message", {
                message: contents,
                // nickname: utils.getCookie("nickname"),
                timestamp: new Date().toISOString(),
            });
            ui.input.value = "";
        }
    });

    // Handle typing indicator logic
    ui.input.addEventListener("input", () => {
        if (!typing) {
            typing = true;
            socket.emit("typing", {});
        }
        lastTypingTime = Date.now();

        setTimeout(() => {
            const timeDiff = Date.now() - lastTypingTime;
            if (typing && timeDiff >= TYPING_TIMER_LENGTH) {
                socket.emit("stop_typing", {
                    // nickname: utils.getCookie("nickname"),
                });
                typing = false;
            }
        }, TYPING_TIMER_LENGTH);
    });

    ui.input.addEventListener("blur", () => {
        if (typing) {
            socket.emit("stop_typing", {
                //nickname: utils.getCookie("nickname"),
            });
            typing = false;
        }
    });

    // Handle image upload flow
    document.getElementById("openFile").addEventListener("click", function () {
        document.getElementById("fileInput").click();
    });

    document
        .getElementById("fileInput")
        .addEventListener("change", function (event) {
            let file = event.target.files[0];
            if (file) {
                ui.openImageOptions(file);
            }
        });

    ui.cancelBtn.addEventListener("click", () => {
        ui.closeImageOptions();
    });

    ui.sendImageBtn.addEventListener("click", () => {
        const file = ui.imageOption._file; // Get the stashed file from the UI module
        const question = ui.botCheckbox.checked
            ? ui.botQuestion.value.trim()
            : null;
        if (!file) return;

        // Tell the socket module to handle the compression and sending
        ChatApp.socket.compressAndSendImage(
            file,
            // utils.getCookie("nickname"),
            new Date().toISOString(),
            question
        );

        // Tell the UI module to close the modal
        ui.closeImageOptions();
    });

    // Handle window focus for missed message count
    window.addEventListener("focus", () => {
        ui.resetMissedCount();
        ui.updateTitle();
        ui.scrollToBottom();
    });
});
