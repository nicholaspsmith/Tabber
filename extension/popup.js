const BACKEND = "http://localhost:7485";

const btnUrl = document.getElementById("btn-url");
const btnRecord = document.getElementById("btn-record");
const engineSelect = document.getElementById("engine-select");
const statusEl = document.getElementById("status");
const tabTitleEl = document.getElementById("tab-title");

let currentTab = null;
let isRecording = false;

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

function setButtonsEnabled(enabled) {
  btnUrl.disabled = !enabled;
  btnRecord.disabled = !enabled;
}

// Get current tab info on popup open
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0]) {
    currentTab = tabs[0];
    tabTitleEl.textContent = currentTab.title || "Unknown tab";
  }
});

// Check backend health and populate engine options
fetch(`${BACKEND}/health`)
  .then((r) => r.json())
  .then((data) => {
    while (engineSelect.firstChild) {
      engineSelect.removeChild(engineSelect.firstChild);
    }
    for (const eng of data.engines) {
      const opt = document.createElement("option");
      opt.value = eng;
      opt.textContent = eng === "klangio" ? "Klangio" : "Open-source";
      engineSelect.appendChild(opt);
    }
  })
  .catch(() => {
    setStatus("Backend not running", "error");
    setButtonsEnabled(false);
  });

// URL mode: send tab URL to backend
btnUrl.addEventListener("click", async () => {
  if (!currentTab?.url) {
    setStatus("No active tab URL", "error");
    return;
  }

  setStatus("Transcribing...", "processing");
  setButtonsEnabled(false);

  chrome.runtime.sendMessage(
    {
      action: "transcribe_url",
      url: currentTab.url,
      title: currentTab.title || "untitled",
      engine: engineSelect.value,
    },
    (response) => {
      if (response?.success) {
        setStatus("Download started", "done");
      } else {
        setStatus(response?.error || "Transcription failed", "error");
      }
      setButtonsEnabled(true);
    }
  );
});

// Record mode: start/stop tab audio capture
btnRecord.addEventListener("click", () => {
  if (!isRecording) {
    startRecording();
  } else {
    stopRecording();
  }
});

function startRecording() {
  if (!currentTab?.id) {
    setStatus("No active tab", "error");
    return;
  }

  setStatus("Recording...", "recording");
  isRecording = true;
  btnRecord.textContent = "Stop Recording";
  btnRecord.classList.add("recording");
  btnUrl.disabled = true;

  chrome.runtime.sendMessage({
    action: "start_recording",
    tabId: currentTab.id,
  });
}

function stopRecording() {
  setStatus("Processing...", "processing");
  isRecording = false;
  btnRecord.textContent = "Record Tab Audio";
  btnRecord.classList.remove("recording");
  setButtonsEnabled(false);

  chrome.runtime.sendMessage(
    {
      action: "stop_recording",
      title: currentTab?.title || "untitled",
      engine: engineSelect.value,
    },
    (response) => {
      if (response?.success) {
        setStatus("Download started", "done");
      } else {
        setStatus(response?.error || "Transcription failed", "error");
      }
      setButtonsEnabled(true);
    }
  );
}
