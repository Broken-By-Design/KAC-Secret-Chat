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

function updateTitle() {
  document.title =
    missedCount > 0 ? `(${missedCount}) ${originalTitle}` : originalTitle;
}

// function addMessage(message, nickname, timestamp) {
//   const item = document.createElement("li");
//   item.innerHTML = `<b>${HtmlSanitizer.SanitizeHtml(nickname)}:</b> ${HtmlSanitizer.SanitizeHtml(message)} <span id="timestamp">${formatTime(timestamp)}</span>`;
//   messages.appendChild(item);
//   window.scrollTo(0, document.body.scrollHeight);
// }


function addMessage(message, nickname, timestamp) {
  const item = document.createElement("li");
  item.innerHTML = `<b>${HtmlSanitizer.SanitizeHtml(
    nickname
  )}:</b> ${HtmlSanitizer.SanitizeHtml(
    message
  )} <span id="timestamp">${formatTime(timestamp)}</span>`;
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

fetch("/get_chatlogs", { credentials: "include" })
  .then((response) => response.json())
  .then((data) => {
    data.forEach((entry) => {
      addMessage(entry.message, entry.nickname, entry.timestamp);
    });
  })
  .catch((error) => console.error("Error loading chat logs:", error));

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

socket.on("chat_message", (msg) => {
  addMessage(msg.message, msg.nickname, msg.timestamp);
  if (document.hidden) {
    missedCount++;
    updateTitle();
  }
});
