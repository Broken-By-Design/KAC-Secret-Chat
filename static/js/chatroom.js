// fetch("/get_chatlogs", { credentials: "include" }) // First thing
//   .then((response) => response.json())
//   .then((data) => {
//     data.forEach((entry) => {
//       if (entry.type == "image") {
//         addImageMessage(entry.id, entry.nickname, entry.timestamp);
//       } else {
//         addMessage(entry.message, entry.nickname, entry.timestamp);
//       }
//     });
//   })
//   .catch((error) => console.error("Error loading chat logs:", error));

fetch("/get_chatlogs", { credentials: "include" })
  .then(res => res.json())
  .then(data => {
    const fragment = document.createDocumentFragment();
    const imagePromises = [];
    data.forEach(entry => {
      const item = document.createElement("li");
      if (entry.type === "image") {
        const anchor = document.createElement('a');
        anchor.href = `/get_image/${entry.id}`;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";

        // Create <img> element
        const img = document.createElement('img');
        img.id = entry.id;
        img.src = `/get_image/${entry.id}`;
        const imagePromise = new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;  // Handle image loading errors
        });

        // Append the image to the anchor
        anchor.appendChild(img);

        // Construct the item
        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(entry.nickname)}: </b>`;
        item.appendChild(anchor);  // Append the anchor (with the image) to the item
        item.innerHTML += ` <span id="timestamp">${formatTime(entry.timestamp)}</span>`;

        // item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(entry.nickname)}: </b> <a href="/get_image/${entry.id}" target="_blank" rel="noopener noreferrer" id="${entry.id}"></a> <span id="timestamp">${formatTime(entry.timestamp)}</span>`;

        imagePromises.push(imagePromise);
      } else {
        const msg = linkify(entry.message);
        item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(entry.nickname)}:</b> ${HtmlSanitizer.SanitizeHtml(msg)} <span id="timestamp">${formatTime(entry.timestamp)}</span>`;
      }
      fragment.appendChild(item);
    });
    messages.appendChild(fragment);
    // window.scrollTo(0, document.body.scrollHeight);
    Promise.all(imagePromises).then(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });

  });


const socket = io({
  query: {
    nickname: getCookie("nickname"),
  }
});


let missedCount = 0; // Count of messages received while tab is unfocused
const originalTitle = document.title; // Save the original tab title

function getCookie(name) {
  const cookies = document.cookie.split(";");
  for (let cookie of cookies) {
    let [key, value] = cookie.split("=");
    if (key && key.trim() === name) {
      return value;
    }
  }
  return null;
}

function linkify(text) {
  const urlRegex = /(?:(?:https?|ftp):\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)/gi;

  const markdownLinkRegex = /\[([^\]]+)\]\(([^)]+)\)/gi;

  const replaceURL = (url) => {
    const href = url.startsWith('http') || url.startsWith('ftp') ? url : `http://${url}`;
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${url}</a>`;
  };

  const replaceMarkdownLink = (match, text, url) => {
    const href = url.startsWith('http') || url.startsWith('ftp') ? url : `http://${url}`;
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  };

  const textWithMarkdownLinks = text.replace(markdownLinkRegex, replaceMarkdownLink);

  const textWithLinks = textWithMarkdownLinks.replace(urlRegex, replaceURL);

  return textWithLinks;
}

function formatTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "numeric",
    hour12: true,
  });
}

function sendImage(file, nickname, timestamp) {
  console.log(file);
  const reader = new FileReader();
  reader.readAsArrayBuffer(file);
  reader.onload = () => {
    const arrayBuffer = reader.result;
    const metadata = { nickname, timestamp, name: file.name };
    // Send metadata and raw bytes
    socket.emit('send_image', metadata, arrayBuffer);
  };
}


function updateTitle() {
  document.title =
    missedCount > 0 ? `(${missedCount}) ${originalTitle}` : originalTitle;
}

function addMessage(message, nickname, timestamp) {
  if (!message) return;
  if (!nickname) return;
  if (!timestamp) return;

  const formattedMessage = linkify(message);

  const item = document.createElement("li");
  // Note: Make sure your sanitizer is configured to allow <a> tags, or you might see your anchors stripped out.
  item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(nickname)}:</b> ${HtmlSanitizer.SanitizeHtml(formattedMessage)} <span id="timestamp">${formatTime(timestamp)}</span>`;
  messages.appendChild(item);
  window.scrollTo(0, document.body.scrollHeight);
}


function addImageMessage(id, nickname, timestamp) {
  const item = document.createElement("li");
  item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(nickname)}:</b> <a href="/get_image/${id}" target="_blank" rel="noopener noreferrer"><img src="/get_image/${id}" /></a> <span id="timestamp">${formatTime(timestamp)}</span>`;
  messages.appendChild(item);
  img.onload = () => {
    window.scrollTo(0, document.body.scrollHeight);
  };
}


window.addEventListener("focus", () => {
  missedCount = 0;
  updateTitle();
});

socket.on("connect", function () {
  console.log("Connection Established");
});

const form = document.getElementById("form");
const input = document.getElementById("input");
const messages = document.getElementById("messages");

form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (input.value) {
    socket.emit("chat_message", {
      message: input.value,
      nickname: getCookie("nickname"),
      timestamp: new Date().toISOString(),
    });
    input.value = "";
  }
});

document.getElementById("openFile").addEventListener("click", function () {
  document.getElementById("fileInput").click();
});

document.getElementById("fileInput").addEventListener("change", function (event) {
  let file = event.target.files[0];
  sendImage(file, getCookie("nickname"), new Date().toISOString());
});

socket.on("chat_message", (msg) => {
  addMessage(msg.message, msg.nickname, msg.timestamp);
  if (document.hidden) {
    missedCount++;
    updateTitle();
  }
});

socket.on("clear_chat", () => {
  messages.innerHTML = "";
});

socket.on('add_image', (data) => {
  addImageMessage(data.id, data.nickname, data.timestamp);
  if (document.hidden) {
    missedCount++;
    updateTitle();
  }
});

socket.on("user_connected", (nickname) => {
  const item = document.createElement("li");
  item.innerHTML = `Welcome! <b>${HtmlSanitizer.SanitizeHtml(nickname)}</b> has joined the chat.`;
  messages.appendChild(item);
  window.scrollTo(0, document.body.scrollHeight);
});