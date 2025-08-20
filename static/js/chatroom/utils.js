

var ChatApp = window.ChatApp || {};

(function () {
  /**
   * Retrieves a cookie value by its name.
   * @param {string} name - The name of the cookie to retrieve.
   * @returns {string|null} The cookie value, or null if not found.
   */
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

  /**
   * Converts URLs and Markdown-style links in a string to HTML <a> tags.
   * @param {string} text - The input text to linkify.
   * @returns {string} The text with HTML links.
   */
  function linkify(text) {
    const markdownLinkRegex = /\[([^\]]+)\]\(([^)]+)\)/gi;
    const urlRegex = /(?:(?:https?|ftp):\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)/gi;

    const html = text.replace(markdownLinkRegex, (_, txt, url) => {
      const href = /^(?:https?|ftp):\/\//i.test(url) ? url : `http://${url}`;
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${txt}</a>`;
    });

    const parts = html.split(/(<a\b[^>]*>[\s\S]*?<\/a>)/gi);

    for (let i = 0; i < parts.length; i++) {
      if (!parts[i].startsWith('<a')) {
        parts[i] = parts[i].replace(urlRegex, (url) => {
          const href = /^(?:https?|ftp):\/\//i.test(url) ? url : `http://${url}`;
          return `<a href="${href}" target="_blank" rel="noopener noreferrer">${url}</a>`;
        });
      }
    }

    return parts.join('');
  }

  /**
   * Formats an ISO date string into a localized time string (e.g., "3:45 PM").
   * @param {string} dateString - The ISO date string to format.
   * @returns {string} The formatted time.
   */
  function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "numeric",
      hour12: true,
    });
  }

  ChatApp.utils = {
    getCookie: getCookie,
    linkify: linkify,
    formatTime: formatTime
  };

})();