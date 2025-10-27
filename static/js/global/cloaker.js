const inDangerMode = true; //true; // set to true to harden security

if (inDangerMode === true) {
    let inFrame;
    try {
        inFrame = window !== top;
    } catch (e) {
        inFrame = true;
    }
    if (!inFrame) {
        // document.body.innerHTML = "";
        cloak()
    }
    document.title = "TeacherEase: Student Main";
    const link = document.createElement("link");
    link.rel = "icon";
    link.href = "https://www.teacherease.com/favicon.ico";
    document.head.appendChild(link);
}

function cloak() {
    let inFrame;
    try {
        inFrame = window !== top;
    } catch (e) {
        inFrame = true;
    }
    if (!inFrame && !navigator.userAgent.includes("Firefox")) {
        const popup = open("about:blank", "_blank");
        if (!popup || popup.closed) {
            document.body.innerHTML = "";
            alert(
                "An unexpected error occured, please try again later.\nError Code 50112"
            );
            location.replace("https://www.google.com");
        } else {
            popup.document.title = "TeacherEase: Student Main";
            const link = popup.document.createElement("link");
            link.rel = "icon";
            link.href = "https://www.teacherease.com/favicon.ico";
            popup.document.head.appendChild(link);
            const iframe = popup.document.createElement("iframe");
            iframe.style.position = "fixed";
            iframe.style.top =
                iframe.style.bottom =
                iframe.style.left =
                iframe.style.right =
                    "0";
            iframe.style.width = iframe.style.height = "100%";
            iframe.style.margin = "0";
            iframe.style.border = iframe.style.outline = "none";
            iframe.src = location.href;
            popup.document.body.appendChild(iframe);
            location.replace("https://www.google.com");
        }
    }
}

function openGame(uri) {
    // let inFrame;
    // try {
    //   inFrame = window !== top;
    // } catch (e) {
    //   inFrame = true;
    // }
    if (!navigator.userAgent.includes("Firefox")) {
        const popup = open("about:blank", "_blank");
        if (!popup || popup.closed) {
            document.body.innerHTML = "";
            alert(
                "An unexpected error occured, please try again later.\nError Code 50112"
            );
            location.replace("https://www.google.com");
        } else {
            popup.document.title = "Home - Google Drive";
            const link = popup.document.createElement("link");
            link.rel = "icon";
            link.href =
                "https://ssl.gstatic.com/docs/doclist/images/drive_2022q3_32dp.png";
            popup.document.head.appendChild(link);
            const iframe = popup.document.createElement("iframe");
            iframe.style.position = "fixed";
            iframe.style.top =
                iframe.style.bottom =
                iframe.style.left =
                iframe.style.right =
                    "0";
            iframe.style.width = iframe.style.height = "100%";
            iframe.style.margin = "0";
            iframe.style.border = iframe.style.outline = "none";
            iframe.src = `https://${location.hostname}/${uri}`;
            popup.document.body.appendChild(iframe);
        }
    }
}

function customCloak(icon, title) {
    let inFrame;
    try {
        inFrame = window !== top;
    } catch (e) {
        inFrame = true;
    }
    if (!inFrame && !navigator.userAgent.includes("Firefox")) {
        const popup = open("about:blank", "_blank");
        if (!popup || popup.closed) {
            document.body.innerHTML = "";
            alert(
                "An unexpected error occured, please try again later.\nError Code 50112"
            );
            location.replace("https://www.google.com");
        } else {
            popup.document.title = title;
            const link = popup.document.createElement("link");
            link.rel = "icon";
            link.href = icon;
            popup.document.head.appendChild(link);
            const iframe = popup.document.createElement("iframe");
            iframe.style.position = "fixed";
            iframe.style.top =
                iframe.style.bottom =
                iframe.style.left =
                iframe.style.right =
                    "0";
            iframe.style.width = iframe.style.height = "100%";
            iframe.style.margin = "0";
            iframe.style.border = iframe.style.outline = "none";
            iframe.src = location.href;
            popup.document.body.appendChild(iframe);
            location.replace("https://www.google.com");
        }
    }
}

function cloakURI(uri) {
    if (!navigator.userAgent.includes("Firefox")) {
        const popup = open("about:blank", "_blank");
        if (!popup || popup.closed) {
            document.body.innerHTML = "";
            alert(
                "An unexpected error occured, please try again later.\nError Code 50112"
            );
            location.replace("https://www.google.com");
        } else {
            popup.document.title = "Home - Google Drive";
            const link = popup.document.createElement("link");
            link.rel = "icon";
            link.href =
                "https://ssl.gstatic.com/docs/doclist/images/drive_2022q3_32dp.png";
            popup.document.head.appendChild(link);
            const iframe = popup.document.createElement("iframe");
            iframe.style.position = "fixed";
            iframe.style.top =
                iframe.style.bottom =
                iframe.style.left =
                iframe.style.right =
                    "0";
            iframe.style.width = iframe.style.height = "100%";
            iframe.style.margin = "0";
            iframe.style.border = iframe.style.outline = "none";
            iframe.src = `https://${location.hostname}/${uri}`;
            popup.document.body.appendChild(iframe);
        }
    }
}

function cloakURL(url) {
    if (!navigator.userAgent.includes("Firefox")) {
        const popup = open("about:blank", "_blank");
        if (!popup || popup.closed) {
            document.body.innerHTML = "";
            alert(
                "An unexpected error occured, please try again later.\nError Code 50112"
            );
            location.replace("https://www.google.com");
        } else {
            popup.document.title = "Home - Google Drive";
            const link = popup.document.createElement("link");
            link.rel = "icon";
            link.href =
                "https://ssl.gstatic.com/docs/doclist/images/drive_2022q3_32dp.png";
            popup.document.head.appendChild(link);
            const iframe = popup.document.createElement("iframe");
            iframe.style.position = "fixed";
            iframe.style.top =
                iframe.style.bottom =
                iframe.style.left =
                iframe.style.right =
                    "0";
            iframe.style.width = iframe.style.height = "100%";
            iframe.style.margin = "0";
            iframe.style.border = iframe.style.outline = "none";
            if (url.startsWith("http://") || url.startsWith("https://")) {
              iframe.src = url;
            } else {
              iframe.src = `https://${url}`;
            }
            popup.document.body.appendChild(iframe);
        }
    }
}
