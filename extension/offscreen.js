let mediaRecorder = null;
let chunks = [];

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "offscreen_start_recording") {
    startRecording(msg.streamId);
  } else if (msg.action === "offscreen_stop_recording") {
    stopRecording();
  }
});

async function startRecording(streamId) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
  });

  // Route audio through AudioContext so the user still hears it
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  source.connect(ctx.destination);

  chunks = [];
  mediaRecorder = new MediaRecorder(stream, {
    mimeType: "audio/webm;codecs=opus",
  });

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) {
      chunks.push(e.data);
    }
  };

  mediaRecorder.onstop = async () => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    chunks = [];

    // Convert to base64 and send to service worker
    const reader = new FileReader();
    reader.onloadend = () => {
      // reader.result is data:audio/webm;base64,XXXX — extract the base64 part
      const base64 = reader.result.split(",")[1];
      chrome.runtime.sendMessage({
        action: "recording_data",
        data: base64,
      });
    };
    reader.readAsDataURL(blob);

    // Stop all tracks
    stream.getTracks().forEach((t) => t.stop());
    ctx.close();
  };

  mediaRecorder.start(1000); // Collect data every second
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
}
