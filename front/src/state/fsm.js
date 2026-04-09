// src/state/fsm.js
const State = {
  Idle: "Idle",
  Ready: "Ready",
  Processing: "Processing",
  ResultReady: "ResultReady",
  Error: "Error",
  WaitConfirm: "WAIT_CONFIRM",
  Teaching: "TEACHING",
};

function createStore() {
  const s = {
    state: State.Idle,
    stage: "",            // capture/warp/recognize/...（文档建议可展示）:contentReference[oaicite:21]{index=21}
    progress: 0,
    jobId: null,
    roiImage: null,
    suggestions: [],
    candidates: [],
    error: null,
    tutorial: null,
    steps: null,
    stepIndex: 0,
  };

  return {
    get: () => ({ ...s }),
    set: (patch) => Object.assign(s, patch),
    State,
  };
}

module.exports = { createStore };
