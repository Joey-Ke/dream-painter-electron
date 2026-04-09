/**
 * This file will automatically be loaded by webpack and run in the "renderer" context.
 * To learn more about the differences between the "main" and the "renderer" context in
 * Electron, visit:
 *
 * https://electronjs.org/docs/tutorial/process-model
 *
 * By default, Node.js integration in this file is disabled. When enabling Node.js integration
 * in a renderer process, please be aware of potential security implications. You can read
 * more about security risks here:
 *
 * https://electronjs.org/docs/tutorial/security
 *
 * To enable Node.js integration in this file, open up `main.js` and enable the `nodeIntegration`
 * flag:
 *
 * ```
 *  // Create the browser window.
 *  mainWindow = new BrowserWindow({
 *    width: 800,
 *    height: 600,
 *    webPreferences: {
 *      nodeIntegration: true
 *    }
 *  });
 * ```
 */

import './index.css';



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

let mediaStream = null;
let capturedBlob = null;
let tutorialSteps = null;  // { stepCount, timestamps[], prompts[] }
let currentStep = 0;
let pendingSeekTime = null; // 视频 metadata 未加载完成时暂存要跳的时间
const cameraShellImg = new URL('./assets/camera/camera.png', import.meta.url).toString();
const galleryImages = [
  new URL('./assets/gallery/draw1.png', import.meta.url).toString(),
  new URL('./assets/gallery/draw2.jpg', import.meta.url).toString(),
  new URL('./assets/gallery/draw3.jpg', import.meta.url).toString(),
  new URL('./assets/gallery/draw4.jpg', import.meta.url).toString(),
];

let galleryIndex = 0;
let galleryTimer = null;

function showModal(msg) {
  els.modalMsg.textContent = msg;
  els.modal.classList.remove('hidden');
}
els.modalOk.onclick = () => els.modal.classList.add('hidden');

function setVideoState(state, videoUrl) {
  if (state === 'idle') {
    if (els.videoPlaceholder) els.videoPlaceholder.classList.remove('hidden');
    if (els.aiVideo) els.aiVideo.style.display = 'none';
    if (els.videoOverlay) els.videoOverlay.classList.add('hidden');
    if (els.btnRegenerate) els.btnRegenerate.classList.add('hidden');
    if (els.overlayText) els.overlayText.textContent = '正在生成视频/生成图片中...';
    startGallery();
  }

  if (state === 'captured') {
    if (els.videoPlaceholder) els.videoPlaceholder.classList.remove('hidden');
    if (els.aiVideo) els.aiVideo.style.display = 'none';
    if (els.videoOverlay) els.videoOverlay.classList.add('hidden');
    if (els.btnGenerate) els.btnGenerate.disabled = false;
    if (els.btnRegenerate) els.btnRegenerate.classList.add('hidden');
    showStepControls(false);
    startGallery();
  }

  if (state === 'generating') {
    if (els.videoPlaceholder) els.videoPlaceholder.classList.remove('hidden');
    if (els.aiVideo) els.aiVideo.style.display = 'none';
    if (els.videoOverlay) els.videoOverlay.classList.remove('hidden');
    if (els.overlayText) els.overlayText.textContent = '正在生成视频/生成图片中...';
    if (els.btnGenerate) els.btnGenerate.disabled = true;
    stopGallery();
  }

  if (state === 'ready') {
    if (els.videoOverlay) els.videoOverlay.classList.add('hidden');
    if (els.videoPlaceholder) els.videoPlaceholder.classList.add('hidden');
    if (els.aiVideo) {
      els.aiVideo.style.display = 'block';
      if (videoUrl) els.aiVideo.src = videoUrl;
    }
    if (els.btnRegenerate) els.btnRegenerate.classList.remove('hidden');
    if (els.btnGenerate) els.btnGenerate.disabled = false;
    stopGallery();
  }

  if (state === 'error') {
    if (els.videoOverlay) els.videoOverlay.classList.add('hidden');
    if (els.videoPlaceholder) els.videoPlaceholder.classList.remove('hidden');
    if (els.aiVideo) els.aiVideo.style.display = 'none';
    if (els.btnGenerate) els.btnGenerate.disabled = false;
    startGallery();
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
  if (!els.stepNav) return;

  els.btnPrevStep?.classList.toggle("hidden", !hasSteps);
  els.btnNextStep?.classList.toggle("hidden", !hasSteps);
  els.stepIndicator?.classList.toggle("hidden", !hasSteps);
  els.btnRegenerate?.classList.toggle("hidden", !hasSteps);

  els.btnGenerate?.classList.toggle("hidden", hasSteps);
}




function normalizeSteps(rawSteps) {
  if (!rawSteps) return null;

  // 兼容 timestamps: 数组 或 对象（如 {"0":0,"1":2.5,"2":5.1}）
  let timestamps = [];
  if (Array.isArray(rawSteps.timestamps)) {
    timestamps = rawSteps.timestamps;
  } else if (rawSteps.timestamps && typeof rawSteps.timestamps === 'object') {
    timestamps = Object.keys(rawSteps.timestamps)
      .map(k => Number(k))
      .sort((a, b) => a - b)
      .map(k => Number(rawSteps.timestamps[k]));
  }

  // prompts 同理（可选）
  let prompts = [];
  if (Array.isArray(rawSteps.prompts)) prompts = rawSteps.prompts;
  else if (rawSteps.prompts && typeof rawSteps.prompts === 'object') {
    prompts = Object.keys(rawSteps.prompts)
      .map(k => Number(k))
      .sort((a, b) => a - b)
      .map(k => String(rawSteps.prompts[k]));
  }

  const stepCount =
    Number(rawSteps.stepCount) ||
    timestamps.length ||
    prompts.length ||
    0;

  return { stepCount, timestamps, prompts };
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

  // 底部字幕：优先用 prompts，没有就显示步骤号
  const promptText = tutorialSteps.prompts?.[idx];
  els.subtitleBar.textContent = promptText ? `第${idx + 1}步：${promptText}` : `已切换到第 ${idx + 1}/${total} 步`;
}

function gotoStep(nextIndex) {
  if (!tutorialSteps) return;

  const total = tutorialSteps.stepCount;
  if (total <= 0) return;

  // clamp 到合法范围
  currentStep = Math.max(0, Math.min(total - 1, nextIndex));
  updateStepUI();

  // 时间点跳转（同一个 mp4 视频里 seek）
  const t = tutorialSteps.timestamps?.[currentStep];
  const seekTime = Number.isFinite(t) ? t : 0;

  // 如果 metadata 还没加载好，先存起来，等 loadedmetadata 再跳
  if (els.aiVideo.readyState >= 1) {
    els.aiVideo.currentTime = seekTime;
    els.aiVideo.play().catch(() => {});
  } else {
    pendingSeekTime = seekTime;
    els.aiVideo.load();
  }
}


async function listCameras() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cams = devices.filter(d => d.kind === 'videoinput');

  els.cameraSelect.innerHTML = '';
  cams.forEach((cam, idx) => {
    const opt = document.createElement('option');
    opt.value = cam.deviceId;
    opt.textContent = cam.label || `摄像头 ${idx + 1}`;
    els.cameraSelect.appendChild(opt);
  });

  if (cams.length === 0) showModal('未检测到摄像头设备。');
}

async function startCamera(deviceId) {
  try {
    if (mediaStream) {
      mediaStream.getTracks().forEach(t => t.stop());
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

    // 显示实时画面
    els.capturePreview.style.display = 'none';

    // 权限拿到后再枚举一次，很多系统这时才会有 label
    await listCameras();
  } catch (e) {
    els.cameraStatus.textContent = '摄像头：开启失败';
    showModal(
      `无法开启摄像头：${e.name}\n${e.message}\n\n排查：\n1) Windows 隐私设置是否关闭摄像头\n2) 微信/QQ/Teams 是否占用摄像头\n3) 权限弹窗是否点了拒绝`
    );
  }
}


function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function runCountdown(from = 3) {
  if (!els.countdownOverlay || !els.countdownNum) return;

  els.countdownOverlay.classList.remove('hidden');

  for (let s = from; s >= 1; s--) {
    els.countdownNum.textContent = String(s);
    await sleep(900);
  }

  els.countdownOverlay.classList.add('hidden');
}




async function captureFrame() {
  if (!mediaStream) return;

  const video = els.cameraVideo;
  if (video.videoWidth === 0) {
    showModal('摄像头尚未准备好，请稍等 1 秒再试。');
    return;
  }

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0);

  capturedBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));

  els.capturePreview.src = URL.createObjectURL(capturedBlob);
  els.capturePreview.style.display = 'block';
  els.cameraVideo.style.display = 'none';
  els.cameraViewport.classList.remove('hidden');

  els.btnGenerate.disabled = false;
  els.subtitleBar.textContent = '已采集图片，可点击“开始生成”。';
}

async function mockGenerate() {
  if (!capturedBlob) {
    showModal('请先点击“采集一张”，再开始生成。');
    return;
  }

  // 清空旧步骤
  tutorialSteps = null;
  currentStep = 0;
  pendingSeekTime = null;
  showStepControls(false);

  setVideoState('generating');
  els.subtitleBar.textContent = '正在生成中（模拟 3 秒）...';

  await new Promise(r => setTimeout(r, 3000));

  // 这里用一个公开示例视频做演示（你接后端后换成后端返回的 tutorial.mp4）
  const demoVideo = 'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4';

  // 模拟 steps.json（真实后端会返回 timestamps/prompts）
  const mockSteps = {
    stepCount: 6,
    timestamps: [0, 2, 4, 6, 8, 10],
    prompts: [
      '先画一个大圆',
      '加上两只耳朵',
      '画眼睛和鼻子',
      '补上胡须',
      '画身体轮廓',
      '最后涂上颜色',
    ],
  };

  setVideoState('ready', demoVideo);

  tutorialSteps = normalizeSteps(mockSteps);
  updateStepUI();
  gotoStep(0); // 默认跳到第 1 步
}


els.aiVideo.addEventListener('loadedmetadata', () => {
  if (pendingSeekTime != null) {
    els.aiVideo.currentTime = pendingSeekTime;
    pendingSeekTime = null;
    els.aiVideo.play().catch(() => {});
  }
});



els.btnStartCamera.onclick = async () => {
  await listCameras();
  await startCamera(els.cameraSelect.value);
};
els.cameraSelect.onchange = async () => startCamera(els.cameraSelect.value);

els.btnCapture.onclick = async () => {
  if (!mediaStream) {
    showModal('请先开启摄像头。');
    return;
  }

  // 防止连点
  els.btnCapture.disabled = true;

  try {
    await runCountdown(3);
    await captureFrame();
  } finally {
    // 无论成功失败都恢复按钮
    els.btnCapture.disabled = false;
  }
};


els.btnGenerate.onclick = mockGenerate;
els.btnRegenerate.onclick = mockGenerate;
els.btnPrevStep.onclick = () => gotoStep(currentStep - 1);
els.btnNextStep.onclick = () => gotoStep(currentStep + 1);


els.cameraShell.src = cameraShellImg;
els.cameraViewport.classList.add('hidden');
setVideoState('idle');
els.backendStatus.textContent = '后端：未连接（先把前端跑通）';
listCameras().catch(() => {});
showStepControls(false);

