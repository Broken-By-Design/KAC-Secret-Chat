const myVideoWrapper = document.createElement('div');
myVideoWrapper.classList.add('video-wrapper');
const myVideo = document.createElement('video');
myVideo.muted = true; // Mute self-view to prevent feedback
const myNameTag = document.createElement('div');
myNameTag.classList.add('nickname');
myNameTag.innerText = `${myNickname} (You)`;
myVideoWrapper.append(myVideo, myNameTag);
videoGrid.append(myVideoWrapper);

let localStream;
let peerConnections = {}; // Key: socketId of the other user

const servers = {
    iceServers: [
        { urls: ['stun:stun1.l.google.com:19302', 'stun:stun2.l.google.com:19302'] }
    ]
};

// --- 1. Get User Media and Join ---
navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    .then(stream => {
        localStream = stream;
        myVideo.srcObject = stream;
        myVideo.play();
        socket.emit('join_video_lounge');
    })
    .catch(error => {
        console.error('Error accessing media devices.', error);
        alert("Could not access your camera or microphone.");
    });

// --- 2. Signaling Logic ---

// When the server tells us who is already in the room
socket.on('all_users', users => {
    console.log("Users already in lounge:", users);
    users.forEach(user => {
        createPeerConnection(user.sid, user.nickname, true); // We are the initiator
    });
});

// When a new user joins
socket.on('user_joined_lounge', user => {
    console.log("New user joined:", user);
    // This user is the initiator for the connection to the new user
    createPeerConnection(user.sid, user.nickname, true);
});

// When we receive an offer from another peer
socket.on('webrtc_offer', async data => {
    console.log("Received WebRTC offer from", data.senderNickname);
    const peerConnection = createPeerConnection(data.senderSid, data.senderNickname, false);
    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);
    socket.emit('webrtc_answer', {
        answer: answer,
        targetSid: data.senderSid
    });
});

// When we receive an answer to our offer
socket.on('webrtc_answer', async data => {
    console.log("Received WebRTC answer from", data.senderNickname);
    const peerConnection = peerConnections[data.senderSid];
    if (peerConnection) {
        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
    }
});

// When we receive an ICE candidate
socket.on('webrtc_candidate', data => {
    const peerConnection = peerConnections[data.senderSid];
    if (peerConnection) {
        peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
    }
});

// When a user leaves
socket.on('user_left_lounge', sid => {
    console.log("User left:", sid);
    if (peerConnections[sid]) {
        peerConnections[sid].close();
        delete peerConnections[sid];
    }
    const videoElement = document.getElementById(`video-${sid}`);
    if (videoElement) {
        videoElement.remove();
    }
});

// --- 3. Helper Function to Create Peer Connection ---
function createPeerConnection(targetSid, targetNickname, isInitiator) {
    if (peerConnections[targetSid]) {
         console.log("Connection with", targetSid, "already exists or is being established.");
         return peerConnections[targetSid];
    }

    const peerConnection = new RTCPeerConnection(servers);
    peerConnections[targetSid] = peerConnection;

    // Add our local stream tracks to the connection
    localStream.getTracks().forEach(track => {
        peerConnection.addTrack(track, localStream);
    });

    // When the remote stream arrives, show it in a new video element
    peerConnection.ontrack = (event) => {
        let remoteVideoWrapper = document.getElementById(`video-${targetSid}`);
        if (!remoteVideoWrapper) {
            remoteVideoWrapper = document.createElement('div');
            remoteVideoWrapper.id = `video-${targetSid}`;
            remoteVideoWrapper.classList.add('video-wrapper');

            const remoteVideo = document.createElement('video');
            remoteVideo.autoplay = true;
            remoteVideo.playsInline = true;
            
            const remoteNameTag = document.createElement('div');
            remoteNameTag.classList.add('nickname');
            remoteNameTag.innerText = targetNickname;

            remoteVideoWrapper.append(remoteVideo, remoteNameTag);
            videoGrid.append(remoteVideoWrapper);
        }
        const videoElem = remoteVideoWrapper.querySelector('video');
        videoElem.srcObject = event.streams[0];
    };

    // Handle ICE candidates
    peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
            socket.emit('webrtc_candidate', {
                candidate: event.candidate,
                targetSid: targetSid
            });
        }
    };

    // If we are the one initiating the connection, create and send an offer
    if (isInitiator) {
        peerConnection.createOffer()
            .then(offer => peerConnection.setLocalDescription(offer))
            .then(() => {
                socket.emit('webrtc_offer', {
                    offer: peerConnection.localDescription,
                    targetSid: targetSid
                });
            })
            .catch(e => console.error("Error creating offer:", e));
    }
    
    return peerConnection;
}

// --- 4. UI Controls ---
const toggleMicBtn = document.getElementById('toggle-mic');
const toggleCamBtn = document.getElementById('toggle-cam');

toggleMicBtn.addEventListener('click', () => {
    const audioTrack = localStream.getAudioTracks()[0];
    audioTrack.enabled = !audioTrack.enabled;
    toggleMicBtn.textContent = audioTrack.enabled ? 'Mute Mic' : 'Unmute Mic';
});

toggleCamBtn.addEventListener('click', () => {
    const videoTrack = localStream.getVideoTracks()[0];
    videoTrack.enabled = !videoTrack.enabled;
    toggleCamBtn.textContent = videoTrack.enabled ? 'Turn Off Cam' : 'Turn On Cam';
});