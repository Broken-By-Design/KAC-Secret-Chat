const socket = io();

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
    return date.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: 'numeric', 
      hour12: true 
    });
  }
  

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

socket.on("connect", function () {
  console.log("Connection Established");
});

fetch("/get_chatlogs")
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
//   const item = document.createElement("li");
//   item.innerHTML = `<b>${HtmlSanitizer.SanitizeHtml(
//     msg.nickname
//   )}:</b> ${HtmlSanitizer.SanitizeHtml(
//     msg.message
//   )} <span id="timestamp">${timeAgo(msg.timestamp)}</span>`;
//   messages.appendChild(item);
//   window.scrollTo(0, document.body.scrollHeight);
    addMessage(msg.message, msg.nickname, msg.timestamp);
}); //
