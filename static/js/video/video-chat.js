document.addEventListener("DOMContentLoaded", () => {
    const socket = io({ reconnection: false });
    const videoGrid = document.getElementById("video-grid");
    const myNickname =
        document.getElementById("user-nickname").dataset.nickname;

    const myVideoWrapper = document.createElement("div");
    myVideoWrapper.classList.add("video-wrapper");
    const myVideo = document.createElement("video");
    myVideo.muted = true;
    myVideo.playsInline = true;
    const myNameTag = document.createElement("div");
    myNameTag.classList.add("nickname");
    myNameTag.innerText = `${myNickname} (You)`;
    myVideoWrapper.append(myVideo, myNameTag);
    videoGrid.append(myVideoWrapper);

    let localStream;
    let peerConnections = {}; // Stores { pc, candidates: [] }

    const servers = {
        iceServers: [
            {
                urls: [
                    "stun:stun1.l.google.com:19302",
                    "stun:stun2.l.google.com:19302",
                ],
            },
        ],
    };

    // --- Main Setup ---
    async function start() {
        try {
            localStream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true,
            });
            myVideo.srcObject = localStream;
            await myVideo.play();
            console.log("Local stream acquired. Joining lounge.");
            socket.emit("join_video_lounge");
        } catch (error) {
            console.error("Error accessing media devices.", error);
            alert("Could not access camera/mic. Please check permissions.");
        }
    }
    start();

    // --- Signaling Handlers ---
    socket.on("all_users", (users) => {
        console.log("Connecting to all existing users:", users);
        users.forEach((user) => handleNewUser(user, false)); // We are NOT the initiator
    });

    socket.on("user_joined_lounge", (user) => {
        console.log("New user joined:", user);
        handleNewUser(user, true); // We ARE the initiator
    });

    socket.on("user_left_lounge", cleanupPeer);
    socket.on("webrtc_offer", handleOffer);
    socket.on("webrtc_answer", handleAnswer);
    socket.on("webrtc_candidate", handleCandidate);

    // --- Core Logic Functions ---
    function handleNewUser(user, isInitiator) {
        if (user.sid === socket.id) return;
        const pc = createPeerConnection(user.sid, user.nickname);
        if (isInitiator) {
            createOffer(pc, user.sid);
        }
    }

    async function handleOffer(data) {
        console.log(`Received offer from ${data.senderNickname}`);
        const pc = createPeerConnection(data.senderSid, data.senderNickname);
        await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
        // After setting remote description, process any queued candidates
        await processQueuedCandidates(data.senderSid);

        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        socket.emit("webrtc_answer", {
            answer: answer,
            targetSid: data.senderSid,
        });
    }

    async function handleAnswer(data) {
        console.log(`Received answer from ${data.senderNickname}`);
        const pc = peerConnections[data.senderSid]?.pc;
        if (pc) {
            await pc.setRemoteDescription(
                new RTCSessionDescription(data.answer)
            );
            // After setting remote description, process any queued candidates
            await processQueuedCandidates(data.senderSid);
        }
    }

    function handleCandidate(data) {
        const pc = peerConnections[data.senderSid]?.pc;
        const candidate = new RTCIceCandidate(data.candidate);
        if (pc && pc.remoteDescription) {
            pc.addIceCandidate(candidate);
        } else {
            peerConnections[data.senderSid]?.candidates.push(candidate);
        }
    }

    // **THIS FUNCTION WAS THE MISSING PIECE**
    async function processQueuedCandidates(sid) {
        const connection = peerConnections[sid];
        if (connection && connection.candidates.length > 0) {
            console.log(
                `Processing ${connection.candidates.length} queued candidates for ${sid}`
            );
            for (const candidate of connection.candidates) {
                try {
                    await connection.pc.addIceCandidate(candidate);
                } catch (e) {
                    console.error("Error adding queued ICE candidate:", e);
                }
            }
            connection.candidates = []; // Clear the queue
        }
    }

    function createPeerConnection(targetSid, targetNickname) {
        if (peerConnections[targetSid]) return peerConnections[targetSid].pc;

        const pc = new RTCPeerConnection(servers);
        peerConnections[targetSid] = { pc, candidates: [] };

        localStream
            ?.getTracks()
            .forEach((track) => pc.addTrack(track, localStream));

        pc.onicecandidate = (event) => {
            if (event.candidate) {
                socket.emit("webrtc_candidate", {
                    candidate: event.candidate,
                    targetSid: targetSid,
                });
            }
        };

        pc.oniceconnectionstatechange = () => {
            const state = pc.iceConnectionState;
            console.log(`Connection state with ${targetNickname}: ${state}`);
            if (["failed", "disconnected", "closed"].includes(state)) {
                cleanupPeer(targetSid);
            }
        };

        pc.ontrack = (event) => {
            console.log(`Track received from ${targetNickname}`);
            addRemoteVideo(targetSid, targetNickname, event.streams[0]);
        };

        return pc;
    }

    async function createOffer(pc, targetSid) {
        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            socket.emit("webrtc_offer", {
                offer: pc.localDescription,
                targetSid: targetSid,
            });
        } catch (err) {
            console.error("Error creating offer:", err);
        }
    }

    function addRemoteVideo(sid, nickname, stream) {
        let remoteVideoWrapper = document.getElementById(`video-${sid}`);
        if (remoteVideoWrapper) return;

        remoteVideoWrapper = document.createElement("div");
        remoteVideoWrapper.id = `video-${sid}`;
        remoteVideoWrapper.classList.add("video-wrapper");
        const remoteVideo = document.createElement("video");
        remoteVideo.autoplay = true;
        remoteVideo.playsInline = true;
        remoteVideo.srcObject = stream;
        const remoteNameTag = document.createElement("div");
        remoteNameTag.classList.add("nickname");
        remoteNameTag.innerText = nickname;
        remoteVideoWrapper.append(remoteVideo, remoteNameTag);
        videoGrid.append(remoteVideoWrapper);
    }

    function cleanupPeer(sid) {
        if (peerConnections[sid]) {
            peerConnections[sid].pc.close();
            delete peerConnections[sid];
        }
        const videoElement = document.getElementById(`video-${sid}`);
        if (videoElement) videoElement.remove();
    }

    // --- UI Controls & Final Cleanup ---
    document.getElementById("toggle-mic").addEventListener("click", (event) => {
        const audioTrack = localStream?.getAudioTracks()[0];
        if (audioTrack) {
            audioTrack.enabled = !audioTrack.enabled;
            event.target.textContent = audioTrack.enabled
                ? "Mute Mic"
                : "Unmute Mic";
        }
    });

    document.getElementById("toggle-cam").addEventListener("click", (event) => {
        const videoTrack = localStream?.getVideoTracks()[0];
        if (videoTrack) {
            videoTrack.enabled = !videoTrack.enabled;
            event.target.textContent = videoTrack.enabled
                ? "Turn Off Cam"
                : "Turn On Cam";
        }
    });

    window.addEventListener("beforeunload", () => {
        socket.disconnect();
    });
});
