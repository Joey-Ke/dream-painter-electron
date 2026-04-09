import "./index.css";

const HARDWARE_BASE = "http://127.0.0.1:18080";

const els = {
  backendStatus: document.getElementById("backendStatus"),
  cameraStatus: document.getElementById("cameraStatus"),
  cameraVideo: document.getElementById("cameraVideo"),
  cameraSelect: document.getElementById("cameraSelect"),
  btnStartCamera: document.getElementById("btnStartCamera"),
  btnCapture: document.getElementById("btnCapture"),
  capturePreview: document.getElementById("capturePreview"),
  videoPlaceholder: document.getElementById("videoPlaceholder"),
  aiVideo: document.getElementById("aiVideo"),
  videoOverlay: document.getElementById("videoOverlay"),
  overlayText: document.getElementById("overlayText"),
  btnGenerate: document.getElementById("btnGenerate"),
  btnRegenerate: document.getElementById("btnRegenerate"),
  btnPrevStep: document.getElementById("btnPrevStep"),
  btnNextStep: document.getElementById("btnNextStep"),
  stepIndicator: document.getElementById("stepIndicator"),
  stepNav: document.getElementById("stepNav"),
  subtitleBar: document.getElementById("subtitleBar"),
  promptInput: document.getElementById("promptInput"),
  modal: document.getElementById("modal"),
  modalMsg: document.getElementById("modalMsg"),
  modalOk: document.getElementById("modalOk"),
  countdownOverlay: document.getElementById("countdownOverlay"),
  countdownNum: document.getElementById("countdownNum"),
};

let aiBackend = {
  baseUrl: "",
  token: "",
  ready: false,
  error: null,
};

let capturedBlob = null;
let tutorialSteps = null;
let currentStep = 0;
let pendingSeekTime = null;
let backendCameraOpened = false;
let previewTimerId = null;
let isGenerating = false;
let lastTaskId = null;

function showModal(msg) {
  els.modalMsg.textContent = msg;
  els.modal.classList.remove("hidden");
}

els.modalOk.onclick = () => els.modal.classList.add("hidden");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function aiHeaders(extra = {}) {
  return {
    ...extra,
    ...(aiBackend.token ? { "X-Token": aiBackend.token } : {}),
  };
}

function setVideoState(state, videoUrl) {
  if (state === "idle") {
    els.videoPlaceholder.classList.remove("hidden");
    els.aiVideo.style.display = "none";
    els.videoOverlay.classList.add("hidden");
    els.btnRegenerate.classList.add("hidden");
  }

  if (state === "captured") {
    els.videoPlaceholder.classList.remove("hidden");
    els.aiVideo.style.display = "none";
    els.videoOverlay.classList.add("hidden");
    els.btnRegenerate.classList.add("hidden");
    showStepControls(false);
  }

  if (state === "generating") {
    els.videoOverlay.classList.remove("hidden");
    els.btnGenerate.disabled = true;
    els.btnRegenerate.disabled = true;
  }

  if (state === "ready") {
    els.videoOverlay.classList.add("hidden");
    els.videoPlaceholder.classList.add("hidden");
    els.aiVideo.style.display = "block";
    if (videoUrl) {
      els.aiVideo.src = videoUrl;
    }
    els.btnRegenerate.classList.remove("hidden");
    els.btnGenerate.disabled = false;
    els.btnRegenerate.disabled = false;
  }

  if (state === "error") {
    els.videoOverlay.classList.add("hidden");
    els.videoPlaceholder.classList.remove("hidden");
    els.aiVideo.style.display = "none";
    els.btnGenerate.disabled = false;
    els.btnRegenerate.disabled = false;
  }
}

function showStepControls(hasSteps) {
  if (!els.stepNav) {
    return;
  }

  els.btnPrevStep.classList.toggle("hidden", !hasSteps);
  els.btnNextStep.classList.toggle("hidden", !hasSteps);
  els.stepIndicator.classList.toggle("hidden", !hasSteps);
  els.btnRegenerate.classList.toggle("hidden", !hasSteps);
  els.btnGenerate.classList.toggle("hidden", hasSteps);
}

function normalizeSteps(rawSteps) {
  if (!rawSteps) {
    return null;
  }

  let timestamps = [];
  if (Array.isArray(rawSteps.timestamps)) {
    timestamps = rawSteps.timestamps;
  } else if (rawSteps.timestamps && typeof rawSteps.timestamps === "object") {
    timestamps = Object.keys(rawSteps.timestamps)
      .map((key) => Number(key))
      .sort((a, b) => a - b)
      .map((key) => Number(rawSteps.timestamps[key]));
  }

  let prompts = [];
  if (Array.isArray(rawSteps.prompts)) {
    prompts = rawSteps.prompts;
  } else if (rawSteps.prompts && typeof rawSteps.prompts === "object") {
    prompts = Object.keys(rawSteps.prompts)
      .map((key) => Number(key))
      .sort((a, b) => a - b)
      .map((key) => String(rawSteps.prompts[key]));
  }

  const stepCount = Number(rawSteps.stepCount) || timestamps.length || prompts.length || 0;
  return { stepCount, timestamps, prompts };
}

function resetTutorial() {
  tutorialSteps = null;
  currentStep = 0;
  pendingSeekTime = null;
  els.aiVideo.removeAttribute("src");
  els.aiVideo.load();
  showStepControls(false);
}

function updateStepUI() {
  if (!tutorialSteps || tutorialSteps.stepCount <= 0) {
    showStepControls(false);
    return;
  }

  showStepControls(true);
  const total = tutorialSteps.stepCount;
  const idx = currentStep;
  els.stepIndicator.textContent = `步骤 ${idx + 1}/${total}`;
  els.btnPrevStep.disabled = idx <= 0;
  els.btnNextStep.disabled = idx >= total - 1;

  const promptText = tutorialSteps.prompts?.[idx];
  els.subtitleBar.textContent = promptText
    ? `第 ${idx + 1} 步：${promptText}`
    : `已切换到第 ${idx + 1}/${total} 步`;
}

function gotoStep(nextIndex) {
  if (!tutorialSteps) {
    return;
  }

  const total = tutorialSteps.stepCount;
  if (total <= 0) {
    return;
  }

  currentStep = Math.max(0, Math.min(total - 1, nextIndex));
  updateStepUI();

  const t = tutorialSteps.timestamps?.[currentStep];
  const seekTime = Number.isFinite(t) ? t : 0;

  if (els.aiVideo.readyState >= 1) {
    els.aiVideo.currentTime = seekTime;
    els.aiVideo.play().catch(() => {});
  } else {
    pendingSeekTime = seekTime;
    els.aiVideo.load();
  }
}

async function dataUrlToBlob(dataUrl) {
  const res = await fetch(dataUrl);
  return res.blob();
}

async function updateAiBackendStatus() {
  try {
    const res = await fetch(`${aiBackend.baseUrl}/health`, {
      headers: aiHeaders(),
    });
    aiBackend.ready = res.ok;
    aiBackend.error = res.ok ? null : `HTTP ${res.status}`;
  } catch (error) {
    aiBackend.ready = false;
    aiBackend.error = error.message;
  }

  els.backendStatus.textContent = aiBackend.ready
    ? `AI 后端：已连接 (${aiBackend.baseUrl})`
    : `AI 后端：未连接${aiBackend.error ? ` - ${aiBackend.error}` : ""}`;
}

async function initAiBackend() {
  if (!window.backend?.getConfig) {
    els.backendStatus.textContent = "AI 后端：未注入配置";
    return;
  }

  const cfg = await window.backend.getConfig();
  aiBackend = {
    baseUrl: cfg.baseUrl || "",
    token: cfg.token || "",
    ready: Boolean(cfg.ready),
    error: cfg.error || null,
  };

  await updateAiBackendStatus();
}

async function listCameras() {
  try {
    const res = await fetch(`${HARDWARE_BASE}/api/camera/devices`);
    const json = await res.json();

    if (!json.success) {
      els.cameraStatus.textContent = "摄像头：硬件服务异常";
      showModal(`获取摄像头列表失败：${json.code}\n${json.message || ""}`);
      return;
    }

    const cams = json.data?.devices || [];
    els.cameraSelect.innerHTML = "";

    cams.forEach((cam, idx) => {
      const opt = document.createElement("option");
      opt.value = String(cam.index);
      opt.textContent = cam.name || `摄像头 ${idx + 1}`;
      els.cameraSelect.appendChild(opt);
    });

    els.cameraStatus.textContent = cams.length > 0
      ? "摄像头：硬件服务已连接"
      : "摄像头：未检测到设备";
  } catch (error) {
    console.error("listCameras error", error);
    els.cameraStatus.textContent = "摄像头：硬件服务未连接";
  }
}

async function startCamera() {
  try {
    const index = Number(els.cameraSelect.value);
    if (!Number.isFinite(index)) {
      showModal("请先选择要开启的摄像头。");
      return;
    }

    els.cameraStatus.textContent = "摄像头：开启中...";
    capturedBlob = null;
    els.btnGenerate.disabled = true;

    const res = await fetch(`${HARDWARE_BASE}/api/camera/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deviceIndex: index }),
    });
    const json = await res.json();

    if (!json.success || json.data?.state !== "PREVIEWING") {
      backendCameraOpened = false;
      els.cameraStatus.textContent = "摄像头：开启失败";
      showModal(`开启摄像头失败：${json.code}\n${json.message || ""}`);
      return;
    }

    backendCameraOpened = true;
    els.cameraStatus.textContent = "摄像头：预览中";
    els.btnCapture.disabled = false;
    els.cameraVideo.style.display = "none";
    els.capturePreview.style.display = "block";
    startPreviewPolling();
  } catch (error) {
    console.error("startCamera error", error);
    backendCameraOpened = false;
    els.cameraStatus.textContent = "摄像头：开启失败";
    showModal(`无法开启摄像头：${error.message || error}`);
  }
}

function stopPreviewPolling() {
  if (previewTimerId) {
    clearInterval(previewTimerId);
    previewTimerId = null;
  }
}

function startPreviewPolling() {
  stopPreviewPolling();

  previewTimerId = setInterval(async () => {
    try {
      const res = await fetch(`${HARDWARE_BASE}/api/camera/preview/latest`);
      const json = await res.json();

      if (!json.success) {
        if (json.code === "CAMERA_NOT_OPEN") {
          backendCameraOpened = false;
          els.cameraStatus.textContent = "摄像头：未开启";
          stopPreviewPolling();
        }
        return;
      }

      const img = json.data?.imageBase64;
      if (img) {
        els.capturePreview.src = img;
        els.capturePreview.style.display = "block";
        els.cameraVideo.style.display = "none";
      }
    } catch (error) {
      console.error("preview polling error", error);
    }
  }, 300);
}

async function captureFrame() {
  if (!backendCameraOpened) {
    showModal("请先开启摄像头。");
    return;
  }

  try {
    const res = await fetch(`${HARDWARE_BASE}/api/capture/snapshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const json = await res.json();

    if (!json.success) {
      showModal(`采集失败：${json.code}\n${json.message || ""}`);
      return;
    }

    if (!els.capturePreview.src) {
      throw new Error("未拿到可上传的预览图像");
    }

    capturedBlob = await dataUrlToBlob(els.capturePreview.src);
    els.btnGenerate.disabled = false;
    els.subtitleBar.textContent = "已采集图像，可以开始生成教学视频了。";
    setVideoState("captured");
  } catch (error) {
    console.error("captureFrame error", error);
    showModal(`采集失败：${error.message || error}`);
  }
}

async function createTask() {
  const form = new FormData();
  form.append("image", capturedBlob, "capture.jpg");
  form.append("prompt", els.promptInput.value.trim());

  const res = await fetch(`${aiBackend.baseUrl}/tasks`, {
    method: "POST",
    headers: aiHeaders(),
    body: form,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`创建任务失败: HTTP ${res.status} ${text}`);
  }

  return res.json();
}

async function getTask(taskId) {
  const res = await fetch(`${aiBackend.baseUrl}/tasks/${taskId}`, {
    headers: aiHeaders(),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`获取任务状态失败: HTTP ${res.status} ${text}`);
  }

  return res.json();
}

async function pollTaskUntilDone(taskId) {
  while (true) {
    const task = await getTask(taskId);
    const percent = Math.round((task.progress || 0) * 100);
    els.overlayText.textContent = `AI 正在生成中：${task.stage || "running"} ${percent}%`;
    els.subtitleBar.textContent = `任务状态：${task.stage || task.status}`;

    if (task.status === "done") {
      return task;
    }

    if (task.status === "error") {
      throw new Error(task.error || "任务执行失败");
    }

    await sleep(1500);
  }
}

async function generateTutorial() {
  if (isGenerating) {
    return;
  }

  if (!capturedBlob) {
    showModal("请先点击“采集一张”，再开始生成。");
    return;
  }

  if (!aiBackend.baseUrl) {
    showModal("AI 后端配置不存在。");
    return;
  }

  await updateAiBackendStatus();
  if (!aiBackend.ready) {
    showModal(`AI 后端还没准备好：${aiBackend.error || aiBackend.baseUrl}`);
    return;
  }

  isGenerating = true;
  resetTutorial();
  setVideoState("generating");
  els.overlayText.textContent = "AI 正在生成中...";
  els.subtitleBar.textContent = "已提交任务，等待后端处理。";

  try {
    const { taskId } = await createTask();
    lastTaskId = taskId;
    const task = await pollTaskUntilDone(taskId);

    const videoUrl = task.video_asset?.url
      ? `${aiBackend.baseUrl}${task.video_asset.url}`
      : "";

    if (!videoUrl) {
      throw new Error("任务已完成，但没有返回视频地址");
    }

    tutorialSteps = normalizeSteps(task.steps);
    setVideoState("ready", videoUrl);
    els.subtitleBar.textContent = task.recognized_subject?.label
      ? `识别结果：${task.recognized_subject.label}`
      : "视频生成完成。";

    if (tutorialSteps) {
      updateStepUI();
      gotoStep(0);
    }
  } catch (error) {
    console.error("generateTutorial error", error);
    setVideoState("error");
    els.subtitleBar.textContent = `生成失败：${error.message || error}`;
    showModal(`生成失败：${error.message || error}${lastTaskId ? `\n任务 ID: ${lastTaskId}` : ""}`);
  } finally {
    isGenerating = false;
  }
}

async function runCountdown(from = 3) {
  if (!els.countdownOverlay || !els.countdownNum) {
    return;
  }

  els.countdownOverlay.classList.remove("hidden");
  for (let s = from; s >= 1; s -= 1) {
    els.countdownNum.textContent = String(s);
    await sleep(900);
  }
  els.countdownOverlay.classList.add("hidden");
}

els.aiVideo.addEventListener("loadedmetadata", () => {
  if (pendingSeekTime != null) {
    els.aiVideo.currentTime = pendingSeekTime;
    pendingSeekTime = null;
    els.aiVideo.play().catch(() => {});
  }
});

els.btnStartCamera.onclick = async () => {
  await startCamera();
};

els.btnCapture.onclick = async () => {
  if (!backendCameraOpened) {
    showModal("请先开启摄像头。");
    return;
  }

  els.btnCapture.disabled = true;
  try {
    await runCountdown(3);
    await captureFrame();
  } finally {
    els.btnCapture.disabled = false;
  }
};

els.btnGenerate.onclick = generateTutorial;
els.btnRegenerate.onclick = generateTutorial;
els.btnPrevStep.onclick = () => gotoStep(currentStep - 1);
els.btnNextStep.onclick = () => gotoStep(currentStep + 1);

async function bootstrap() {
  setVideoState("idle");
  showStepControls(false);
  els.backendStatus.textContent = "AI 后端：初始化中...";
  els.cameraStatus.textContent = "摄像头：初始化中...";
  await initAiBackend();
  await listCameras();
}

bootstrap().catch((error) => {
  console.error("bootstrap error", error);
  els.backendStatus.textContent = `初始化失败：${error.message || error}`;
});
