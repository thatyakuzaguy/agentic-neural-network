const state = {
  runs: [],
  selectedRunId: null,
  selectedPatchName: null,
  selectedPatchMetadata: null,
};

const nodes = {
  runsList: document.querySelector("#runs-list"),
  refreshRuns: document.querySelector("#refresh-runs"),
  runTitle: document.querySelector("#run-title"),
  runTask: document.querySelector("#run-task"),
  statusGrid: document.querySelector("#status-grid"),
  artifactsList: document.querySelector("#artifacts-list"),
  patchesList: document.querySelector("#patches-list"),
  viewerTitle: document.querySelector("#viewer-title"),
  viewerMeta: document.querySelector("#viewer-meta"),
  contentViewer: document.querySelector("#content-viewer"),
  patchMetadata: document.querySelector("#patch-metadata"),
  approvalForm: document.querySelector("#approval-form"),
  approvalToken: document.querySelector("#approval-token"),
  confirmReviewed: document.querySelector("#confirm-reviewed"),
  confirmNoApply: document.querySelector("#confirm-no-apply"),
  approvalNote: document.querySelector("#approval-note"),
  approveButton: document.querySelector("#approve-button"),
  approvalResult: document.querySelector("#approval-result"),
  terminalForm: document.querySelector("#terminal-form"),
  terminalCwd: document.querySelector("#terminal-cwd"),
  terminalCommand: document.querySelector("#terminal-command"),
  terminalConfirm: document.querySelector("#terminal-confirm"),
  terminalOutput: document.querySelector("#terminal-output"),
  nextStepMessage: document.querySelector("#next-step-message"),
  nextStepState: document.querySelector("#next-step-state"),
  nextStepSummary: document.querySelector("#next-step-summary"),
  nextStepSteps: document.querySelector("#next-step-steps"),
  nextStepAllowed: document.querySelector("#next-step-allowed"),
  nextStepBlockedActions: document.querySelector("#next-step-blocked-actions"),
  nextStepPrerequisites: document.querySelector("#next-step-prerequisites"),
  nextStepRisks: document.querySelector("#next-step-risks"),
  nextStepSubsystems: document.querySelector("#next-step-subsystems"),
  nextStepArtifacts: document.querySelector("#next-step-artifacts"),
};

const statusLabels = {
  autonomous_loop_status: "Autonomous Loop",
  patch_quality_decision: "Patch Quality",
  patch_approval_status: "Patch Approval",
  patch_apply_status: "Patch Apply",
  test_runner_status: "Test Runner",
  self_healing_status: "Self Healing",
  merge_readiness_status: "Merge Readiness",
  parallel_review_decision: "Parallel Review",
  consensus_decision: "Consensus",
  action_plan_next_action: "Next Action",
  action_plan_blocked: "Action Blocked",
};

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.text();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `${response.status} ${response.statusText}`);
  }
  return data;
}

function escapeText(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function statusClass(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (["passed", "valid", "approved", "implementation_ready", "completed"].includes(normalized)) {
    return "status-good";
  }
  if (["failed", "rejected", "failed_tests", "failed_permanently"].includes(normalized)) {
    return "status-bad";
  }
  if (["blocked", "needs_revision", "needs_relocation", "unconnected_logic"].includes(normalized)) {
    return "status-warn";
  }
  return "status-unknown";
}

function renderRuns() {
  nodes.runsList.replaceChildren();
  if (!state.runs.length) {
    nodes.runsList.textContent = "No ANN runs found.";
    return;
  }
  for (const run of state.runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `run-card ${run.run_id === state.selectedRunId ? "active" : ""}`;
    button.setAttribute("aria-label", `Open run ${run.run_id}`);
    button.innerHTML = `
      <strong>${escapeText(run.run_id)}</strong>
      <span>${escapeText(run.task)}</span>
      <span>${escapeText(run.patch_quality_decision)} · ${escapeText(run.test_runner_status)}</span>
    `;
    button.addEventListener("click", () => openRun(run.run_id));
    nodes.runsList.append(button);
  }
}

function renderStatuses(statuses = {}) {
  nodes.statusGrid.replaceChildren();
  for (const [key, label] of Object.entries(statusLabels)) {
    const value = statuses[key] ?? "UNKNOWN";
    const card = document.createElement("div");
    card.className = `status-card ${statusClass(value)}`;
    card.innerHTML = `<span>${label}</span><strong>${escapeText(value)}</strong>`;
    nodes.statusGrid.append(card);
  }
}

function renderList(container, items = [], emptyText = "None") {
  container.replaceChildren();
  const values = Array.isArray(items) ? items : [];
  if (!values.length) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    container.append(item);
    return;
  }
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = String(value);
    container.append(item);
  }
}

function renderSteps(container, steps = []) {
  container.replaceChildren();
  const values = Array.isArray(steps) ? steps : [];
  if (!values.length) {
    const item = document.createElement("li");
    item.textContent = "No steps available.";
    container.append(item);
    return;
  }
  for (const step of values) {
    const item = document.createElement("li");
    const description = step.description || "Review action plan.";
    const subsystem = step.subsystem ? ` · ${step.subsystem}` : "";
    const actionType = step.action_type ? ` · ${step.action_type}` : "";
    item.textContent = `${description}${subsystem}${actionType}`;
    container.append(item);
  }
}

function renderActionPlan(plan = {}) {
  const blocked = plan.blocked === true;
  const executable = plan.executable === true;
  nodes.nextStepMessage.textContent = plan.user_message || "No action plan is available for this run yet.";
  nodes.nextStepState.textContent = blocked ? "Blocked" : executable ? "Executable plan" : "Planning only";
  nodes.nextStepState.className = `next-step-state ${blocked ? "blocked" : executable ? "ready" : "idle"}`;
  const requires = plan.requires || {};
  nodes.nextStepSummary.innerHTML = `
    <dt>Next action</dt><dd>${escapeText(plan.next_action || "missing_action_plan")}</dd>
    <dt>Status</dt><dd>${escapeText(plan.status || "UNKNOWN")}</dd>
    <dt>Executable</dt><dd>${executable ? "yes" : "no"}</dd>
    <dt>Blocked</dt><dd>${blocked ? "yes" : "no"}</dd>
    <dt>Requires</dt><dd>${[
      requires.human ? "human" : "",
      requires.terminal ? "terminal" : "",
      requires.approval ? "approval" : "",
      requires.apply ? "apply" : "",
    ].filter(Boolean).join(", ") || "none"}</dd>
  `;
  renderSteps(nodes.nextStepSteps, plan.planned_steps || []);
  renderList(nodes.nextStepAllowed, plan.allowed_actions || []);
  renderList(nodes.nextStepBlockedActions, plan.blocked_actions || []);
  renderList(nodes.nextStepPrerequisites, plan.prerequisites || []);
  renderList(nodes.nextStepRisks, plan.risks || []);
  renderList(nodes.nextStepSubsystems, plan.responsible_subsystems || []);
  renderList(nodes.nextStepArtifacts, plan.expected_artifacts || []);
}

function renderFiles(container, files, type, runId) {
  container.replaceChildren();
  if (!files.length) {
    container.textContent = type === "artifact" ? "No artifacts found." : "No patches found.";
    return;
  }
  for (const file of files) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-button";
    button.setAttribute("aria-label", `Open ${type} ${file.name}`);
    button.innerHTML = `
      <strong>${escapeText(file.name)}</strong>
      <span>${Number(file.size).toLocaleString()} bytes</span>
    `;
    button.addEventListener("click", () => openFile(runId, type, file.name));
    container.append(button);
  }
}

function renderDiff(text) {
  nodes.contentViewer.replaceChildren();
  const fragment = document.createDocumentFragment();
  for (const line of text.split("\n")) {
    const row = document.createElement("div");
    row.className = "diff-line";
    if (line.startsWith("+") && !line.startsWith("+++")) {
      row.classList.add("diff-add");
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      row.classList.add("diff-remove");
    } else if (line.startsWith("@@")) {
      row.classList.add("diff-hunk");
    } else if (line.startsWith("---") || line.startsWith("+++")) {
      row.classList.add("diff-file");
    }
    row.textContent = line || " ";
    fragment.append(row);
  }
  nodes.contentViewer.append(fragment);
}

function renderText(text) {
  nodes.contentViewer.replaceChildren();
  nodes.contentViewer.textContent = text;
}

function renderMetadata(metadata) {
  state.selectedPatchMetadata = metadata;
  const blocked = !metadata.can_be_approved_from_ui;
  nodes.approveButton.disabled = blocked || !state.selectedPatchName;
  nodes.patchMetadata.innerHTML = `
    <dl>
      <dt>Patch</dt><dd>${escapeText(metadata.patch_name)}</dd>
      <dt>Files touched</dt><dd>${escapeText((metadata.files_touched || []).join(", ") || "none")}</dd>
      <dt>Creates files</dt><dd>${metadata.creates_files ? "yes" : "no"}</dd>
      <dt>Deletes files</dt><dd>${metadata.deletes_files ? "yes" : "no"}</dd>
      <dt>Protected path</dt><dd>${metadata.protected_path_detected ? "blocked" : "no"}</dd>
      <dt>C drive</dt><dd>${metadata.c_drive_detected ? "blocked" : "no"}</dd>
      <dt>Model/training path</dt><dd>${metadata.model_dataset_training_detected ? "blocked" : "no"}</dd>
      <dt>Patch Quality</dt><dd>${escapeText(metadata.patch_quality_decision)}</dd>
      <dt>Patch Approval</dt><dd>${escapeText(metadata.patch_approval_decision)}</dd>
      <dt>UI Approval</dt><dd>${metadata.can_be_approved_from_ui ? "allowed" : "blocked"}</dd>
    </dl>
    <ul>${(metadata.reasons || []).map((reason) => `<li>${escapeText(reason)}</li>`).join("")}</ul>
  `;
}

function resetApprovalPanel() {
  state.selectedPatchName = null;
  state.selectedPatchMetadata = null;
  nodes.approveButton.disabled = true;
  nodes.approvalResult.textContent = "";
  nodes.patchMetadata.textContent = "Select a patch to inspect approval metadata.";
}

async function loadRuns() {
  try {
    const payload = await fetchJson("/api/runs");
    state.runs = payload.runs ?? [];
    renderRuns();
  } catch (error) {
    nodes.runsList.textContent = `Failed to load runs: ${error.message}`;
  }
}

async function openRun(runId) {
  state.selectedRunId = runId;
  resetApprovalPanel();
  renderRuns();
  renderText("Loading run...");
  try {
    const run = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
    nodes.runTitle.textContent = run.run_id;
    nodes.runTask.textContent = run.task;
    renderStatuses(run.statuses ?? {});
    renderActionPlan(run.action_plan_view ?? {});
    renderFiles(nodes.artifactsList, run.artifacts ?? [], "artifact", run.run_id);
    renderFiles(nodes.patchesList, run.patches ?? [], "patch", run.run_id);
    nodes.viewerTitle.textContent = "summary.json";
    nodes.viewerMeta.textContent = run.path;
    renderText(JSON.stringify(run.summary ?? {}, null, 2));
  } catch (error) {
    renderText(`Failed to open run: ${error.message}`);
  }
}

async function openFile(runId, type, name) {
  const encodedName = name.split("/").map(encodeURIComponent).join("/");
  const endpoint = type === "artifact" ? "artifact" : "patch";
  nodes.viewerTitle.textContent = name;
  nodes.viewerMeta.textContent = type === "artifact" ? "Artifact" : "Patch diff";
  renderText("Loading...");
  try {
    const content = await fetchText(`/api/runs/${encodeURIComponent(runId)}/${endpoint}/${encodedName}`);
    if (type === "patch") {
      state.selectedPatchName = name;
      renderDiff(content);
      const metadata = await fetchJson(
        `/api/runs/${encodeURIComponent(runId)}/patch/${encodedName}/metadata`,
      );
      renderMetadata(metadata);
    } else {
      resetApprovalPanel();
      renderText(content);
    }
  } catch (error) {
    renderText(`Failed to load ${type}: ${error.message}`);
  }
}

async function submitApproval(event) {
  event.preventDefault();
  if (!state.selectedRunId || !state.selectedPatchName) {
    nodes.approvalResult.textContent = "Select a patch first.";
    return;
  }
  nodes.approvalResult.textContent = "Submitting approval...";
  try {
    const response = await postJson(`/api/runs/${encodeURIComponent(state.selectedRunId)}/approve`, {
      patch_name: state.selectedPatchName,
      approval_token: nodes.approvalToken.value,
      confirm_reviewed: nodes.confirmReviewed.checked,
      confirm_no_apply: nodes.confirmNoApply.checked,
      note: nodes.approvalNote.value,
    });
    nodes.approvalResult.textContent = `${response.status}: ${response.artifact}. Applied: ${response.applied}`;
    nodes.approvalToken.value = "";
  } catch (error) {
    nodes.approvalResult.textContent = `Approval failed: ${error.message}`;
  }
}

async function submitTerminal(event) {
  event.preventDefault();
  let command;
  try {
    command = JSON.parse(nodes.terminalCommand.value);
  } catch (error) {
    nodes.terminalOutput.textContent = `Invalid command JSON: ${error.message}`;
    return;
  }
  nodes.terminalOutput.textContent = "Running safe terminal command...";
  try {
    const response = await postJson("/api/terminal/run", {
      run_id: state.selectedRunId,
      cwd: nodes.terminalCwd.value,
      command,
      timeout_seconds: 120,
      confirm_execute: nodes.terminalConfirm.checked,
    });
    nodes.terminalOutput.textContent = JSON.stringify(response, null, 2);
  } catch (error) {
    nodes.terminalOutput.textContent = `Terminal failed: ${error.message}`;
  }
}

nodes.refreshRuns.addEventListener("click", loadRuns);
nodes.approvalForm.addEventListener("submit", submitApproval);
nodes.terminalForm.addEventListener("submit", submitTerminal);
loadRuns();
