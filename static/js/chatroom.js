fetch("/get_chatlogs", { credentials: "include" }) // First thing
  .then((response) => response.json())
  .then((data) => {
    data.forEach((entry) => {
      if (entry.type == "image") {
        addImageMessage(entry.message, entry.nickname, entry.timestamp);
      } else {
        addMessage(entry.message, entry.nickname, entry.timestamp);
      }
    });
  })
  .catch((error) => console.error("Error loading chat logs:", error));

const socket = io();

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

function formatTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "numeric",
    hour12: true,
  });
}

function sendImage(file, nickname, timestamp) {
  const reader = new FileReader();
  reader.readAsDataURL(file); // Convert image to Base64
  reader.onload = function () {
    console.log(reader.result);
      socket.emit('send_image', { image: reader.result, nickname: nickname, timestamp: timestamp });
  };
}


function updateTitle() {
  document.title =
    missedCount > 0 ? `(${missedCount}) ${originalTitle}` : originalTitle;
}

function addMessage(message, nickname, timestamp) {
  // First, convert Markdown links [text](url) to HTML anchor tags.
  const mdLinkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let formattedMessage = message.replace(mdLinkRegex, (match, text, url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });

  // Then, as a fallback, replace any plain URLs with anchor tags.
  // const urlRegex = /(https?:\/\/[^\s]+)/g;
  // const urlRegex = /(?<!href=")(https?:\/\/[^\s<]+)/g;
  const urlRegex = /(^|\s)(https?:\/\/[^\s<]+)/g;
  formattedMessage = formattedMessage.replace(urlRegex, (url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
  });

  const item = document.createElement("li");
  // Note: Make sure your sanitizer is configured to allow <a> tags, or you might see your anchors stripped out.
  item.innerHTML = `<b>${HtmlSanitizer.SanitizeHtml(nickname)}:</b> ${HtmlSanitizer.SanitizeHtml(formattedMessage)} <span id="timestamp">${formatTime(timestamp)}</span>`;
  messages.appendChild(item);
  window.scrollTo(0, document.body.scrollHeight);
}


function addImageMessage(image, nickname, timestamp) {
  const item = document.createElement("li");
  item.innerHTML = `<b id="nickname">${HtmlSanitizer.SanitizeHtml(nickname)}:</b> <img src="${image}" /> <span id="timestamp">${formatTime(timestamp)}</span>`;
  messages.appendChild(item);
  window.scrollTo(0, document.body.scrollHeight);
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

socket.on('send_image', (data) => {
  addImageMessage(data.image, data.nickname, data.timestamp);
  if (document.hidden) {
    missedCount++;
    updateTitle();
  }
});


