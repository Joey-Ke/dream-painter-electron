const { setBackendConfig, captureAndRecognize, confirmTarget, getJob, fileUrl } = require("../services/api");
const { connectWs } = require("../services/ws");
const { createStore } = require("../state/fsm");

const store = createStore();

function $(id) { return document.getElementById(id); }

function render() {
  const s = store.get();

  $("status").innerText = `${s.state} ${s.stage ? `(${s.stage})` : ""} ${Math.round(s.progress * 100)}%`;

  $("btnCapture").disabled = !(s.state === store.State.Ready || s.state === store.State.ResultReady || s.state === store.State.Error);

  // 控制显示内容
  if (s.roiImage) {
    $("roi").src = fileUrl(s.roiImage);
    $("roi").style.display = "block";
    $("aiVideo").style.display = "none";
    $("videoPlaceholder").style.display = "none";
  } else {
    $("roi").style.display = "none";
    $("aiVideo").style.display = "block";
    // videoPlaceholder的显示由其他逻辑控制
  }

  $("subtitle").innerText = (s.suggestions || []).slice(0, 4).join("\n");

  // WAIT_CONFIRM 弹窗
  $("confirmModal").style.display = (s.state === store.State.WaitConfirm) ? "block" : "none";

  // 分享面板：只在 ResultReady 状态显示
  $("sharePanel").style.display = (s.state === store.State.ResultReady) ? "block" : "none";
}

async function main() {
  // 1) 从 preload 拿到 baseUrl/token
  const cfg = await window.backend.getConfig();
  setBackendConfig(cfg);

  // 2) 初始状态 Ready（主进程已经 health ok 了；如果你改成 renderer 自己 health，则这里做轮询）
  store.set({ state: store.State.Ready });
  render();

  // 3) 建 WS：打印事件 + 驱动状态机
  connectWs({
    baseUrl: cfg.baseUrl,
    token: cfg.token,
    onEvent: async (evt) => {
      // 事件类型按你后端实际字段来，这里按文档的事件名写 :contentReference[oaicite:26]{index=26}
      const type = evt.type || evt.event || evt.name;

      if (type === "job_progress") {
        store.set({ state: store.State.Processing, progress: evt.progress ?? 0, stage: evt.stage ?? "" });
      }

      if (type === "job_error") {
        store.set({ state: store.State.Error, error: evt, progress: 0, stage: "" });
        // 你可以用弹窗显示错误码/建议（文档有错误码建议）:contentReference[oaicite:27]{index=27}
        alert(`${evt.code}\n${evt.hint || ""}`);
      }

      if (type === "job_wait_confirm") {
        store.set({ state: store.State.WaitConfirm, candidates: evt.candidates || [] });
      }

      if (type === "job_done") {
        // job_done 后拉取结果路径并展示 roi + 建议 :contentReference[oaicite:28]{index=28}
        const jobId = store.get().jobId || evt.jobId;
        const detail = await getJob(jobId);
        store.set({
          state: store.State.ResultReady,
          roiImage: detail.artifacts?.roiImage || detail.roiImage,
          suggestions: detail.suggestions || [],
          progress: 1,
          stage: "",
        });
      }

      render();
    }
  });

  // 4) 按钮：拍照识别 -> POST /capture-and-recognize -> 得到 jobId :contentReference[oaicite:29]{index=29}
  $("btnCapture").onclick = async () => {
    try {
      store.set({ state: store.State.Processing, progress: 0, stage: "capture" });
      render();

      const { jobId } = await captureAndRecognize("p123"); // projectId 按你约定传
      store.set({ jobId });
      render();
    } catch (e) {
      store.set({ state: store.State.Error, error: { code: "HTTP_FAIL", hint: e.message } });
      render();
    }
  };

  // 5) 识别确认弹窗：确认 -> POST /confirm-target :contentReference[oaicite:30]{index=30}
  $("btnConfirm").onclick = async () => {
    const s = store.get();
    const target = $("targetInput").value.trim();
    if (!target) return;

    store.set({ state: store.State.Processing, stage: "generate_sketch", progress: 0 });
    render();

    await confirmTarget(s.jobId, target);
    // 后端会继续推 job_progress/job_done；你这里只要进入 Processing 即可
  };

  // 6) 分享功能
  $("btnSaveImage").onclick = async () => {
    const s = store.get();
    if (!s.roiImage) return;

    try {
      // 获取图片数据
      const response = await fetch(fileUrl(s.roiImage));
      const blob = await response.blob();
      
      // 使用Electron dialog保存文件
      const result = await window.electronAPI.showSaveDialog({
        title: '保存作品图片',
        defaultPath: `dream-painter-${Date.now()}.png`,
        filters: [
          { name: 'PNG图片', extensions: ['png'] },
          { name: '所有文件', extensions: ['*'] }
        ]
      });

      if (!result.canceled) {
        // 将blob写入文件
        const arrayBuffer = await blob.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);
        await window.electronAPI.writeFile(result.filePath, buffer);
        alert('图片保存成功！');
      }
    } catch (error) {
      console.error('保存图片失败:', error);
      alert('保存图片失败，请重试');
    }
  };

  $("btnShareWechat").onclick = async () => {
    const s = store.get();
    if (!s.roiImage) return;

    try {
      // 生成分享链接或二维码
      const shareUrl = `${window.location.origin}/share?image=${encodeURIComponent(s.roiImage)}&suggestions=${encodeURIComponent((s.suggestions || []).join(','))}`;
      
      // 复制到剪贴板
      await navigator.clipboard.writeText(shareUrl);
      alert('分享链接已复制到剪贴板！\n\n在微信中粘贴链接即可分享');
    } catch (error) {
      console.error('分享失败:', error);
      alert('分享失败，请重试');
    }
  };

  $("btnShareQQ").onclick = async () => {
    const s = store.get();
    if (!s.roiImage) return;

    try {
      // 生成分享链接
      const shareUrl = `${window.location.origin}/share?image=${encodeURIComponent(s.roiImage)}&suggestions=${encodeURIComponent((s.suggestions || []).join(','))}`;
      
      // 复制到剪贴板
      await navigator.clipboard.writeText(shareUrl);
      alert('分享链接已复制到剪贴板！\n\n在QQ中粘贴链接即可分享');
    } catch (error) {
      console.error('分享失败:', error);
      alert('分享失败，请重试');
    }
  };
}

window.addEventListener("DOMContentLoaded", main);
