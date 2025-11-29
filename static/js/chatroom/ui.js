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
        // console.log(data.href);
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

    // Jumpscare info
    const jumpscareAudio = new Audio("/jumpscare/sound.wav");
    jumpscareAudio.preload = "auto";
    jumpscareAudio.load();

    const jumpscareImage = new Image();
    jumpscareImage.src = "/jumpscare/image.png";
    var readyJumpscare = false;

    var readyCrash = false;

    document.getElementById("input").disabled = true;
    document.getElementById("input").placeholder = "Connecting...";
    document.querySelector('button[type="submit"]').disabled = true;
    document.getElementById("openFile").disabled = true;

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

    function createEmbed(message) {
        // const spotifyRegex =
        //     /(?:https?:\/\/)?open\.spotify\.com\/track\/([a-zA-Z0-9]+)/;
        // const spotifyMatch = message.match(spotifyRegex);

        // if (spotifyMatch && spotifyMatch[1]) {
        //     const trackId = spotifyMatch[1];
        //     return `${message}<br><iframe style="border-radius:12px" src="https://open.spotify.com/embed/track/${trackId}?utm_source=generator" width="50%" height="152" frameBorder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"></iframe>`;
        // }
        const spotifyRegex =
            /(<a href=")?(https?:\/\/open\.spotify\.com\/(track|album|playlist|artist|show|episode)\/([a-zA-Z0-9]+))[^"]*(">[^<]+<\/a>)?/i;
        const spotifyMatch = message.match(spotifyRegex);

        if (spotifyMatch && spotifyMatch[2]) {
            const type = spotifyMatch[3]; // e.g., "track", "album"
            const id = spotifyMatch[4]; // The Spotify ID
            let height = 352; // Default height for albums, playlists

            // Adjust height based on content type for a better fit
            switch (type) {
                case "track":
                    height = 152; // Compact player for single tracks
                    break;
                case "show":
                case "episode":
                    height = 232; // Standard height for podcasts
                    break;
            }

            const embedIframe = `${message}<br><iframe style="border-radius:12px" src="https://open.spotify.com/embed/${type}/${id}?utm_source=generator" width="50%" height="${height}" frameBorder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>`;
            // Replace the original link with the iframe
            return embedIframe;
        }

        // If no match, return the original message (sanitized)
        return message;
    }

    function addMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        // Don't add public messages when in DM view
        if (activeDMUser) return;

        const currentUserNickname = document.body.dataset.nickname;

        let processedMessage = utils.linkify(
            marked.parseInline(HtmlSanitizer.SanitizeHtml(message))
        );

        // Highlight mentions of the current user's nickname
        if (currentUserNickname) {
            const mentionRegex = new RegExp(`@${currentUserNickname}\\b`, "gi");
            processedMessage = processedMessage.replace(
                mentionRegex,
                (match) => `<span class="mention-highlight">${match}</span>`
            );
        }

        const item = document.createElement("li");

        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
            nickname
        )}:</b> ${createEmbed(
            processedMessage
        )} <span id="timestamp">${utils.formatTime(timestamp)}</span>`;
        messages.appendChild(item);

        const elementHeight = item.offsetHeight;
        const dynamicThreshold = elementHeight + 200;
        scrollToBottom(false, dynamicThreshold);
    }

    function addHighlightedMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        // Don't add public messages when in DM view
        if (activeDMUser) return;

        const formattedMessage = createEmbed(
            marked.parseInline(HtmlSanitizer.SanitizeHtml(message))
        );
        const item = document.createElement("li");
        item.classList.add("highlight");
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

    function addSystemMessage(message, nickname, timestamp) {
        if (!message || !nickname || !timestamp) return;

        // Don't add public messages when in DM view
        if (activeDMUser) return;

        const formattedMessage = utils.linkify(marked.parseInline(message));
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
        // Don't add public messages when in DM view
        if (activeDMUser) return;

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
        // Don't add public messages when in DM view
        if (activeDMUser) return;

        const item = document.createElement("li");
        item.innerHTML = `Welcome! <b>${HtmlSanitizer.SanitizeHtml(
            nickname
        )}</b> has joined the chat.`;
        messages.appendChild(item);
        scrollToBottom();
    }

    function addSystemMessageNoUser(message) {
        // Don't add public messages when in DM view
        if (activeDMUser) return;

        const item = document.createElement("li");
        item.innerHTML = utils.linkify(marked.parseInline(message));
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
        input.focus();
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

    function showBannedMessage(expires_at = null) {
        if (expires_at) {
            const encoded = encodeURIComponent(expires_at);
            location.replace(`/banned?expires_at=${encoded}`);
        } else {
            location.replace("/banned");
        }
        return;
    }

    function addPinnedMessage(message, nickname) {
        // Remove any existing pinned message first
        const existingPinnedMessage = document.getElementById("pinned-message");
        if (existingPinnedMessage) {
            existingPinnedMessage.remove();
        }

        const formattedMessage = utils.linkify(
            marked.parseInline(HtmlSanitizer.SanitizeHtml(message))
        );

        const pinnedMessageContainer = document.createElement("div");
        pinnedMessageContainer.id = "pinned-message";

        const messageContent = document.createElement("span");
        messageContent.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
            nickname
        )}:</b> ${formattedMessage}`;
        pinnedMessageContainer.appendChild(messageContent);

        const closeButton = document.createElement("button");
        closeButton.innerHTML = "&times;"; // A simple "x"
        closeButton.onclick = () => {
            pinnedMessageContainer.remove();
            document.body.style.paddingTop = "0";
        };
        pinnedMessageContainer.appendChild(closeButton);

        document.body.insertBefore(
            pinnedMessageContainer,
            document.body.firstChild
        );

        // Add padding to the body to prevent the pinned message from overlapping the chat content
        document.body.style.paddingTop = `${pinnedMessageContainer.offsetHeight}px`;
    }

    function enableInputs() {
        document.getElementById("input").disabled = false;
        document.getElementById("input").placeholder = "Type Here";
        document.querySelector('button[type="submit"]').disabled = false;
        document.getElementById("openFile").disabled = false;
    }

    function disableInputs(text) {
        document.getElementById("input").disabled = true;
        document.getElementById("input").placeholder = text;
        document.querySelector('button[type="submit"]').disabled = true;
        document.getElementById("openFile").disabled = true;
    }

    function triggerJumpscare(
        imagePath = "/jumpscare/image.png",
        soundPath = "/jumpscare/sound.wav",
        duration = 3000
    ) {
        // Use preloaded audio or create a new one if a different path is provided
        const audio =
            soundPath === jumpscareAudio.src
                ? jumpscareAudio
                : new Audio(soundPath);

        // Play the sound
        audio.currentTime = 0.3;
        audio.play().catch((error) => {
            // Autoplay was prevented.
            console.error("Jumpscare sound could not be played:", error);
        });

        // Create the jumpscare image element
        const jumpscareImg = document.createElement("img");
        // Use the preloaded image src or a new one
        jumpscareImg.src =
            imagePath === jumpscareImage.src ? jumpscareImage.src : imagePath;
        jumpscareImg.alt = "Jumpscare";
        jumpscareImg.id = "jumpscare-image"; // Assign an ID for easier CSS targeting

        // Append the image to the body
        document.body.appendChild(jumpscareImg);

        // Remove the image after the specified duration
        setTimeout(() => {
            const imgToRemove = document.getElementById("jumpscare-image");
            if (imgToRemove) {
                document.body.removeChild(imgToRemove);
            }
        }, duration);
    }

    // --- DM FUNCTIONS ---

    let activeDMUser = null; // Tracks the currently open DM conversation

    function addPrivateMessage(message, from, to, timestamp) {
        const currentUserNickname = document.body.dataset.nickname;

        // Only show the DM if we're in a DM view with this user
        if (activeDMUser && (from === activeDMUser || to === activeDMUser)) {
            const isFromMe = from === currentUserNickname;
            const displayNickname = isFromMe ? from : from;

            let processedMessage = utils.linkify(
                marked.parseInline(HtmlSanitizer.SanitizeHtml(message))
            );

            const item = document.createElement("li");
            // Don't add special classes - let it follow the regular alternating pattern

            item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(
                displayNickname
            )}:</b> ${createEmbed(
                processedMessage
            )} <span id="timestamp">${utils.formatTime(timestamp)}</span>`;
            messages.appendChild(item);

            const elementHeight = item.offsetHeight;
            const dynamicThreshold = elementHeight + 200;
            scrollToBottom(false, dynamicThreshold);
        } else if (!activeDMUser) {
            // Show a notification if not in DM view
            showDMNotification(from === currentUserNickname ? to : from);
        }
    }

    function showDMNotification(from) {
        // Create a simple notification for new DM
        const notification = document.createElement("div");
        notification.classList.add("dm-notification");
        notification.innerHTML = `New message from <b>${HtmlSanitizer.SanitizeHtml(
            from
        )}</b>`;
        notification.onclick = () => {
            openDMView(from);
            notification.remove();
        };
        document.body.appendChild(notification);

        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

    function showDMError(error) {
        alert(error);
    }

    function openDMView(username) {
        activeDMUser = username;
        messages.innerHTML = ""; // Clear current messages

        // Add a header showing who we're DMing with
        const header = document.createElement("div");
        header.id = "dm-header";
        header.innerHTML = `
            <button id="back-to-public">← Back to Public Chat</button>
            <span>Direct Message with <b>${HtmlSanitizer.SanitizeHtml(
                username
            )}</b></span>
        `;
        messages.parentNode.insertBefore(header, messages);

        // Add padding to body to prevent header overlap
        document.body.style.paddingTop = `${header.offsetHeight}px`;

        // Add event listener for back button
        document
            .getElementById("back-to-public")
            .addEventListener("click", closeDMView);

        // Load DM history
        fetch(`/get_dm_logs?with=${encodeURIComponent(username)}`, {
            credentials: "include",
        })
            .then((res) => res.json())
            .then((data) => {
                data.forEach((entry) => {
                    if (entry.type === "dm" && entry.message) {
                        addPrivateMessage(
                            entry.message,
                            entry.nickname,
                            entry.recipient,
                            entry.timestamp
                        );
                    }
                });
                scrollToBottom(true);
            })
            .catch((error) => {
                console.error("Error loading DM history:", error);
            });
    }

    function closeDMView() {
        activeDMUser = null;

        // Remove DM header
        const header = document.getElementById("dm-header");
        if (header) {
            header.remove();
        }

        // Reset body padding
        document.body.style.paddingTop = "0";

        messages.innerHTML = ""; // Clear DM messages

        // Reload public chat
        window.location.reload();
    }

    function createUserListForDM() {
        // Check if modal already exists and prevent duplicate
        if (document.getElementById("dm-user-list")) {
            return;
        }

        // This function will be called to create a user list UI for starting DMs
        const userListContainer = document.createElement("div");
        userListContainer.id = "dm-user-list";
        userListContainer.innerHTML = `
            <h3>Send Direct Message</h3>
            <div id="dm-users"></div>
            <button id="close-dm-list">Cancel</button>
        `;

        document.body.appendChild(userListContainer);

        // Fetch connected users
        fetch("/get_connected_users", { credentials: "include" })
            .then((res) => res.json())
            .then((users) => {
                const currentUser = document.body.dataset.nickname;
                const userListDiv = document.getElementById("dm-users");

                users.forEach((user) => {
                    if (user !== currentUser) {
                        const userBtn = document.createElement("button");
                        userBtn.textContent = user;
                        userBtn.classList.add("dm-user-btn");
                        userBtn.onclick = () => {
                            openDMView(user);
                            userListContainer.remove();
                        };
                        userListDiv.appendChild(userBtn);
                    }
                });
            })
            .catch((error) => {
                console.error("Error fetching users:", error);
            });

        document.getElementById("close-dm-list").onclick = () => {
            userListContainer.remove();
        };
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
        readyJumpscare: readyJumpscare,

        // Expose functions that other modules need to call.
        addMessage: addMessage,
        addHighlightedMessage: addHighlightedMessage,
        addSystemMessage: addSystemMessage,
        addImageMessage: addImageMessage,
        addUserConnectedMessage: addUserConnectedMessage,
        addSystemMessageNoUser: addSystemMessageNoUser,
        addPinnedMessage: addPinnedMessage,
        showBannedMessage: showBannedMessage,
        enableInputs: enableInputs,
        disableInputs: disableInputs,
        openImageOptions: openImageOptions,
        closeImageOptions: closeImageOptions,
        updateTypingIndicator: updateTypingIndicator,
        clearChat: function () {
            messages.innerHTML = "";
        },
        triggerJumpscare: triggerJumpscare,

        // DM functions
        addPrivateMessage: addPrivateMessage,
        showDMError: showDMError,
        openDMView: openDMView,
        closeDMView: closeDMView,
        createUserListForDM: createUserListForDM,
        getActiveDMUser: function () {
            return activeDMUser;
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
