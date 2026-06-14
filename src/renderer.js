import './index.css';

const {
  setBackendConfig,
  health,
  createTask,
  getTask,
  assetUrl,
  frameUrl,
} = require('./services/api');

const els = {
  backendStatus: document.getElementById('backendStatus'),
  cameraStatus: document.getElementById('cameraStatus'),
  cameraShell: document.getElementById('cameraShell'),
  cameraViewport: document.getElementById('cameraViewport'),
  cameraVideo: document.getElementById('cameraVideo'),
  cameraSelect: document.getElementById('cameraSelect'),
  btnStartCamera: document.getElementById('btnStartCamera'),
  btnCapture: document.getElementById('btnCapture'),
  capturePreview: document.getElementById('capturePreview'),
  videoPlaceholder: document.getElementById('videoPlaceholder'),
  placeholderSlide: document.getElementById('placeholderSlide'),
  aiVideo: document.getElementById('aiVideo'),
  roi: document.getElementById('roi'),
  videoOverlay: document.getElementById('videoOverlay'),
  overlayText: document.getElementById('overlayText'),
  btnGenerate: document.getElementById('btnGenerate'),
  btnRegenerate: document.getElementById('btnRegenerate'),
  btnPrevStep: document.getElementById('btnPrevStep'),
  btnNextStep: document.getElementById('btnNextStep'),
  stepIndicator: document.getElementById('stepIndicator'),
  stepNav: document.getElementById('stepNav'),
  subtitleBar: document.getElementById('subtitleBar'),
  promptInput: document.getElementById('promptInput'),
  modal: document.getElementById('modal'),
  modalMsg: document.getElementById('modalMsg'),
  modalOk: document.getElementById('modalOk'),
  countdownOverlay: document.getElementById('countdownOverlay'),
  countdownNum: document.getElementById('countdownNum'),
};

const STAGE_TEXT = {
  queued: ['排队中', '准备开始生成，请稍等。'],
  save_input: ['保存图片', '正在整理你拍下的图片。'],
  recognize_subject: ['识别主体', '正在看看画面里最适合教画的东西。'],
  generate_lineart: ['生成线稿', '正在把它变成适合临摹的简笔画。'],
  build_steps: ['拆解步骤', '正在把画法拆成一步一步。'],
  compose_video: ['合成视频', '正在做成教学小视频。'],
  done: ['完成', '可以跟着步骤开始画啦。'],
  error: ['失败', '生成遇到问题，请重试或切换演示模式。'],
};

const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 120000;
const cameraShellImg = new URL('./assets/camera/camera.png', import.meta.url).toString();
const galleryImages = [
  new URL('./assets/gallery/draw1.png', import.meta.url).toString(),
  new URL('./assets/gallery/draw2.jpg', import.meta.url).toString(),
  new URL('./assets/gallery/draw3.jpg', import.meta.url).toString(),
  new URL('./assets/gallery/draw4.jpg', import.meta.url).toString(),
];

let backendConfig = { baseUrl: '', token: '', ready: false, error: '' };
let mediaStream = null;
let capturedBlob = null;
let tutorialSteps = null;
let currentStep = 0;
let currentTaskId = null;
let currentTask = null;
let pollTimer = null;
let pollStartedAt = 0;
let pendingSeekTime = null;
let isGenerating = false;
let galleryIndex = 0;
let galleryTimer = null;

function showModal(msg) {
  els.modalMsg.textContent = msg;
  els.modal.classList.remove('hidden');
}

function hideModal() {
  els.modal.classList.add('hidden');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function startGallery() {
  if (!els.placeholderSlide || galleryImages.length === 0) return;

  stopGallery();
  els.placeholderSlide.src = galleryImages[galleryIndex];
  galleryTimer = setInterval(() => {
    galleryIndex = (galleryIndex + 1) % galleryImages.length;
    els.placeholderSlide.src = galleryImages[galleryIndex];
  }, 2500);
}

function stopGallery() {
  if (galleryTimer) {
    clearInterval(galleryTimer);
    galleryTimer = null;
  }
}

function showStepControls(hasSteps) {
  els.btnPrevStep.classList.toggle('hidden', !hasSteps);
  els.btnNextStep.classList.toggle('hidden', !hasSteps);
  els.stepIndicator.classList.toggle('hidden', !hasSteps);
  els.btnRegenerate.classList.toggle('hidden', !hasSteps);
  els.btnGenerate.classList.toggle('hidden', hasSteps);
}

function setControlsBusy(busy) {
  isGenerating = busy;
  els.btnGenerate.disabled = busy || !capturedBlob;
  els.btnRegenerate.disabled = busy || !capturedBlob;
  els.btnCapture.disabled = busy || !mediaStream;
  els.btnStartCamera.disabled = busy;
}

function setVideoState(state, videoUrl = '') {
  if (state === 'idle' || state === 'captured' || state === 'error') {
    els.videoPlaceholder.classList.remove('hidden');
    els.aiVideo.style.display = 'none';
    els.roi.classList.add('hidden');
    els.videoOverlay.classList.add('hidden');
    startGallery();
  }

  if (state === 'idle') {
    showStepControls(false);
    els.btnGenerate.disabled = true;
    els.btnRegenerate.classList.add('hidden');
    els.overlayText.textContent = '正在生成教学视频...';
  }

  if (state === 'captured') {
    showStepControls(false);
    els.btnGenerate.classList.remove('hidden');
    els.btnGenerate.disabled = false;
    els.btnRegenerate.classList.add('hidden');
  }

  if (state === 'generating') {
    els.videoPlaceholder.classList.remove('hidden');
    els.aiVideo.style.display = 'none';
    els.roi.classList.add('hidden');
    els.videoOverlay.classList.remove('hidden');
    els.overlayText.textContent = '正在创建 AI 教学任务...';
    stopGallery();
  }

  if (state === 'ready') {
    els.videoOverlay.classList.add('hidden');
    els.videoPlaceholder.classList.add('hidden');
    els.roi.classList.add('hidden');
    els.aiVideo.style.display = 'block';
    if (videoUrl) {
      els.aiVideo.src = videoUrl;
      els.aiVideo.load();
    }
    stopGallery();
  }
}

function stageCopy(stage, status = '') {
  if (status === 'error') return STAGE_TEXT.error;
  return STAGE_TEXT[stage] || [stage || '处理中', '正在继续处理，请稍等。'];
}

function progressText(task) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(task.progress || 0) * 100)));
  const [title, hint] = stageCopy(task.stage, task.status);
  return `${title} ${pct}%\n${hint}`;
}

function normalizeErrorMessage(error) {
  const raw = String(error?.message || error || '').trim();
  if (!raw) return '发生未知错误，请重试。';

  if (/SiliconFlow|SILICONFLOW|Seedream|SEEDREAM|VOLCENGINE|ARK_API_KEY|LAS_API_KEY/i.test(raw)) {
    return '缺少或无法使用线稿生成 API Key。请在后端 .env 中配置 SILICONFLOW_API_KEY，并设置 LINEART_BACKEND=siliconflow 后重新启动后端。';
  }

  if (/DASHSCOPE|OPENAI_API_KEY|Qwen|recognizer/i.test(raw)) {
    return '识别模型配置不可用。可以配置 DASHSCOPE_API_KEY，或使用 RECOGNIZER_BACKEND=auto/local。';
  }

  if (/Failed to fetch|NetworkError|Backend baseUrl/i.test(raw)) {
    return `无法连接后端：${backendConfig.baseUrl || '未配置'}。\n请先启动后端：\ncd backend/backend\n.\\.venv311\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`;
  }

  return raw;
}

function normalizeSteps(rawSteps) {
  if (!rawSteps) return { stepCount: 0, timestamps: [], prompts: [] };

  let timestamps = [];
  if (Array.isArray(rawSteps.timestamps)) {
    timestamps = rawSteps.timestamps.map(Number);
  } else if (rawSteps.timestamps && typeof rawSteps.timestamps === 'object') {
    timestamps = Object.keys(rawSteps.timestamps)
      .map((key) => Number(key))
      .sort((a, b) => a - b)
      .map((key) => Number(rawSteps.timestamps[key]));
  }

  let prompts = [];
  if (Array.isArray(rawSteps.prompts)) {
    prompts = rawSteps.prompts.map(String);
  } else if (rawSteps.prompts && typeof rawSteps.prompts === 'object') {
    prompts = Object.keys(rawSteps.prompts)
      .map((key) => Number(key))
      .sort((a, b) => a - b)
      .map((key) => String(rawSteps.prompts[key]));
  }

  const stepCount = Number(rawSteps.stepCount || rawSteps.count || timestamps.length || prompts.length || 0);
  while (timestamps.length < stepCount) timestamps.push(timestamps.length);
  while (prompts.length < stepCount) prompts.push(`跟着视频完成第 ${prompts.length + 1} 步。`);

  return { stepCount, timestamps, prompts };
}

function showFrameFallback(index) {
  if (!currentTaskId) return;
  els.roi.src = frameUrl(currentTaskId, index);
  els.roi.classList.remove('hidden');
}

function updateStepUI() {
  if (!tutorialSteps || tutorialSteps.stepCount <= 0) {
    showStepControls(false);
    return;
  }

  showStepControls(true);

  const total = tutorialSteps.stepCount;
  const idx = Math.max(0, Math.min(total - 1, currentStep));
  els.stepIndicator.textContent = `步骤 ${idx + 1}/${total}`;
  els.btnPrevStep.disabled = idx <= 0;
  els.btnNextStep.disabled = idx >= total - 1;
  els.subtitleBar.textContent = `第 ${idx + 1} 步：${tutorialSteps.prompts[idx]}`;
}

function gotoStep(nextIndex) {
  if (!tutorialSteps || tutorialSteps.stepCount <= 0) return;

  currentStep = Math.max(0, Math.min(tutorialSteps.stepCount - 1, nextIndex));
  updateStepUI();

  const t = Number(tutorialSteps.timestamps[currentStep]);
  const seekTime = Number.isFinite(t) ? t : 0;

  if (els.aiVideo.style.display === 'none') {
    showFrameFallback(currentStep);
    return;
  }

  if (els.aiVideo.readyState >= 1) {
    els.aiVideo.currentTime = seekTime;
    els.aiVideo.play().catch(() => {});
  } else {
    pendingSeekTime = seekTime;
  }
}

function handleTaskDone(task) {
  currentTask = task;
  tutorialSteps = normalizeSteps(task.steps);
  currentStep = 0;

  if (!task.video_asset?.url) {
    throw new Error('后端任务已完成，但没有返回 tutorial.mp4。');
  }

  setVideoState('ready', assetUrl(task.video_asset.url));
  setControlsBusy(false);
  updateStepUI();
  gotoStep(0);
}

function handleTaskError(task) {
  clearPoll();
  currentTask = task;
  setVideoState('error');
  setControlsBusy(false);
  const err = normalizeErrorMessage(task.error || '任务生成失败。');
  els.subtitleBar.textContent = `生成失败：${err}`;
  showModal(`生成失败：\n${err}`);
}

async function pollTask(taskId) {
  clearPoll();

  if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
    handleTaskError({
      status: 'error',
      stage: 'error',
      error: '任务超过 120 秒未完成。请检查后端日志、网络连接或 API Key 配置。',
    });
    return;
  }

  try {
    const task = await getTask(taskId);
    currentTask = task;

    if (task.status === 'done') {
      clearPoll();
      handleTaskDone(task);
      return;
    }

    if (task.status === 'error') {
      handleTaskError(task);
      return;
    }

    const text = progressText(task);
    els.overlayText.textContent = text;
    els.subtitleBar.textContent = text.replace('\n', ' ');
    pollTimer = setTimeout(() => pollTask(taskId), POLL_INTERVAL_MS);
  } catch (error) {
    handleTaskError({
      status: 'error',
      stage: 'error',
      error: normalizeErrorMessage(error),
    });
  }
}

async function mockGenerate(reason) {
  const message = [
    reason || '后端当前不可用。',
    '',
    '请启动本地 mock 后端后再生成：',
    'cd backend/backend',
    '$env:LINEART_BACKEND="mock"',
    'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
  ].join('\n');
  setVideoState('error');
  setControlsBusy(false);
  els.subtitleBar.textContent = '后端未连接，请先启动 mock 后端。';
  showModal(message);
}

async function runGenerate({ isRegenerate = false } = {}) {
  if (isGenerating) return;

  if (!capturedBlob) {
    showModal('请先开启摄像头并采集一张照片，再开始生成。');
    return;
  }

  clearPoll();
  tutorialSteps = null;
  currentStep = 0;
  currentTaskId = null;
  currentTask = null;
  pendingSeekTime = null;

  setVideoState('generating');
  setControlsBusy(true);

  try {
    if (!backendConfig.ready) {
      await updateBackendStatus();
    }

    if (!backendConfig.ready) {
      await mockGenerate(backendConfig.error || '后端健康检查未通过。');
      return;
    }

    const prompt = els.promptInput.value.trim();
    els.overlayText.textContent = isRegenerate ? '正在重新创建任务...' : '正在创建任务...';
    els.subtitleBar.textContent = '正在提交照片和主题，请稍等。';

    const created = await createTask({ imageBlob: capturedBlob, prompt });
    currentTaskId = created.taskId;
    pollStartedAt = Date.now();
    els.subtitleBar.textContent = `任务已创建：${currentTaskId}，正在生成。`;
    pollTimer = setTimeout(() => pollTask(currentTaskId), 200);
  } catch (error) {
    handleTaskError({
      status: 'error',
      stage: 'error',
      error: normalizeErrorMessage(error),
    });
  }
}

async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    els.cameraStatus.textContent = '摄像头：当前环境不支持摄像头';
    showModal('当前环境无法枚举摄像头设备。');
    return;
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  const cams = devices.filter((device) => device.kind === 'videoinput');

  els.cameraSelect.innerHTML = '';
  cams.forEach((cam, idx) => {
    const opt = document.createElement('option');
    opt.value = cam.deviceId;
    opt.textContent = cam.label || `摄像头 ${idx + 1}`;
    els.cameraSelect.appendChild(opt);
  });

  if (cams.length === 0) {
    els.cameraStatus.textContent = '摄像头：未检测到设备';
  }
}

async function startCamera(deviceId) {
  try {
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }

    els.cameraViewport.classList.remove('hidden');
    els.capturePreview.style.display = 'none';
    els.cameraVideo.style.display = 'block';
    els.cameraStatus.textContent = '摄像头：请求权限中...';

    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: deviceId ? { deviceId: { exact: deviceId } } : true,
      audio: false,
    });

    els.cameraVideo.srcObject = mediaStream;
    els.cameraStatus.textContent = '摄像头：已开启';
    els.btnCapture.disabled = false;
    await listCameras();
  } catch (error) {
    els.cameraStatus.textContent = '摄像头：开启失败';
    showModal(
      `无法开启摄像头：${error.name || ''}\n${error.message || error}\n\n请检查：\n1. Windows 隐私设置是否允许摄像头。\n2. 其他软件是否正在占用摄像头。\n3. 权限弹窗是否被拒绝。`
    );
  }
}

async function runCountdown(from = 3) {
  els.countdownOverlay.classList.remove('hidden');
  for (let s = from; s >= 1; s -= 1) {
    els.countdownNum.textContent = String(s);
    await sleep(900);
  }
  els.countdownOverlay.classList.add('hidden');
}

async function captureFrame() {
  if (!mediaStream) {
    showModal('请先开启摄像头。');
    return;
  }

  const video = els.cameraVideo;
  if (video.videoWidth === 0) {
    showModal('摄像头还没有准备好，请稍等 1 秒再试。');
    return;
  }

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);

  capturedBlob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  if (!capturedBlob) {
    showModal('采集照片失败，请重试。');
    return;
  }

  els.capturePreview.src = URL.createObjectURL(capturedBlob);
  els.capturePreview.style.display = 'block';
  els.cameraVideo.style.display = 'none';
  els.cameraViewport.classList.remove('hidden');
  els.subtitleBar.textContent = '已采集照片，可以点击“开始生成”。';
  setVideoState('captured');
}

async function updateBackendStatus() {
  if (!window.backend?.getConfig) {
    backendConfig = { baseUrl: '', token: '', ready: false, error: 'preload 未注入 backend 配置。' };
    els.backendStatus.textContent = '后端：未注入配置';
    setBackendConfig(backendConfig);
    return;
  }

  els.backendStatus.textContent = '后端：初始化中...';

  try {
    const cfg = await window.backend.getConfig();
    backendConfig = {
      baseUrl: cfg.baseUrl || '',
      token: cfg.token || '',
      ready: Boolean(cfg.ready),
      error: cfg.error || '',
    };
    setBackendConfig(backendConfig);

    if (!backendConfig.baseUrl) {
      backendConfig.ready = false;
      backendConfig.error = '后端地址缺失。';
      els.backendStatus.textContent = '后端：配置地址缺失';
      return;
    }

    const ok = await health();
    backendConfig.ready = ok;
    backendConfig.error = ok ? '' : backendConfig.error || `Health check failed: ${backendConfig.baseUrl}`;

    if (ok) {
      els.backendStatus.textContent = `后端：已连接 (${backendConfig.baseUrl})`;
    } else {
      els.backendStatus.textContent = `后端：未连接 (${backendConfig.baseUrl})`;
      els.subtitleBar.textContent = '后端未连接。可启动 mock 后端后再生成。';
    }
  } catch (error) {
    backendConfig.ready = false;
    backendConfig.error = normalizeErrorMessage(error);
    els.backendStatus.textContent = `后端：未连接 (${backendConfig.baseUrl || '未知地址'})`;
    els.subtitleBar.textContent = backendConfig.error;
  }
}

els.modalOk.onclick = hideModal;

els.aiVideo.addEventListener('loadedmetadata', () => {
  if (pendingSeekTime != null) {
    els.aiVideo.currentTime = pendingSeekTime;
    pendingSeekTime = null;
    els.aiVideo.play().catch(() => {});
  }
});

els.aiVideo.addEventListener('error', () => {
  if (!currentTaskId) return;
  els.aiVideo.style.display = 'none';
  showFrameFallback(currentStep);
  els.subtitleBar.textContent = '视频加载失败，已切换为步骤帧预览。请检查后端 tutorial.mp4 是否存在。';
});

els.btnStartCamera.onclick = async () => {
  await listCameras();
  await startCamera(els.cameraSelect.value);
};

els.cameraSelect.onchange = async () => {
  if (els.cameraSelect.value) await startCamera(els.cameraSelect.value);
};

els.btnCapture.onclick = async () => {
  if (!mediaStream) {
    showModal('请先开启摄像头。');
    return;
  }

  els.btnCapture.disabled = true;
  try {
    await runCountdown(3);
    await captureFrame();
  } finally {
    els.btnCapture.disabled = isGenerating || !mediaStream;
  }
};

els.btnGenerate.onclick = () => runGenerate({ isRegenerate: false });
els.btnRegenerate.onclick = () => runGenerate({ isRegenerate: true });
els.btnPrevStep.onclick = () => gotoStep(currentStep - 1);
els.btnNextStep.onclick = () => gotoStep(currentStep + 1);

els.cameraShell.src = cameraShellImg;
els.cameraViewport.classList.add('hidden');
setVideoState('idle');
updateBackendStatus();
listCameras().catch(() => {});
