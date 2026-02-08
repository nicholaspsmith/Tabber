const BACKEND = "http://localhost:7485";

let recordingTabId = null;

// Ensure offscreen document exists
async function ensureOffscreen() {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });
  if (contexts.length === 0) {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Recording tab audio for guitar transcription",
    });
  }
}

// Handle messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "transcribe_url") {
    handleTranscribeUrl(msg).then(sendResponse);
    return true; // async response
  }

  if (msg.action === "start_recording") {
    handleStartRecording(msg.tabId).then(sendResponse);
    return true;
  }

  if (msg.action === "stop_recording") {
    handleStopRecording(msg.title, msg.engine).then(sendResponse);
    return true;
  }

  // Message from offscreen with recorded audio
  if (msg.action === "recording_complete") {
    // Stored for when stop_recording is called
    self._recordedBlob = msg.blob;
  }
});

async function handleTranscribeUrl({ url, title, engine }) {
  try {
    const resp = await fetch(`${BACKEND}/transcribe/url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title, engine }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return { success: false, error: err.detail || `Server error ${resp.status}` };
    }

    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    const safeName = title.replace(/[^\w\-.]/g, "_").replace(/^_+|_+$/g, "") || "untitled";

    await chrome.downloads.download({
      url: objectUrl,
      filename: `${safeName}.gp5`,
      saveAs: false,
    });

    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function handleStartRecording(tabId) {
  try {
    recordingTabId = tabId;
    self._recordedBlob = null;

    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId,
    });

    await ensureOffscreen();

    chrome.runtime.sendMessage({
      action: "offscreen_start_recording",
      streamId,
    });

    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function handleStopRecording(title, engine) {
  try {
    // Tell offscreen to stop recording — it will post back the blob as base64
    chrome.runtime.sendMessage({ action: "offscreen_stop_recording" });

    // Wait for the recorded data to arrive
    const audioBase64 = await waitForRecording(10000);
    if (!audioBase64) {
      return { success: false, error: "No audio data received" };
    }

    // Convert base64 to blob
    const byteString = atob(audioBase64);
    const bytes = new Uint8Array(byteString.length);
    for (let i = 0; i < byteString.length; i++) {
      bytes[i] = byteString.charCodeAt(i);
    }
    const audioBlob = new Blob([bytes], { type: "audio/webm" });

    // Upload to backend
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    formData.append("title", title);
    formData.append("engine", engine);

    const resp = await fetch(`${BACKEND}/transcribe/audio`, {
      method: "POST",
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return { success: false, error: err.detail || `Server error ${resp.status}` };
    }

    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    const safeName = title.replace(/[^\w\-.]/g, "_").replace(/^_+|_+$/g, "") || "untitled";

    await chrome.downloads.download({
      url: objectUrl,
      filename: `${safeName}.gp5`,
      saveAs: false,
    });

    recordingTabId = null;
    return { success: true };
  } catch (e) {
    recordingTabId = null;
    return { success: false, error: e.message };
  }
}

function waitForRecording(timeoutMs) {
  return new Promise((resolve) => {
    const start = Date.now();

    function check() {
      if (self._recordedBase64) {
        const data = self._recordedBase64;
        self._recordedBase64 = null;
        resolve(data);
        return;
      }
      if (Date.now() - start > timeoutMs) {
        resolve(null);
        return;
      }
      setTimeout(check, 200);
    }

    check();
  });
}

// Listen for base64 audio data from offscreen
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "recording_data") {
    self._recordedBase64 = msg.data;
  }
});
