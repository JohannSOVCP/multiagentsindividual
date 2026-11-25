const canvas = document.getElementById("room");
const context = canvas.getContext("2d");
const agentSelect = document.getElementById("agent-count");
const statusElement = document.getElementById("status");
const summaryElement = document.getElementById("summary");
const colors = ["#2563eb", "#dc2626", "#7c3aed", "#ea580c", "#16834a", "#a21caf"];
const speed = 3;

let room;
let routes = {};
let elapsed = 0;
let running = false;
let lastFrame = 0;

function resizeCanvas() {
  const scale = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  context.setTransform(scale, 0, 0, scale, 0, 0);
  draw();
}

function layout() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const cellSize = Math.min((width - 72) / room.columns, (height - 72) / room.rows);
  return {
    cellSize,
    left: (width - cellSize * room.columns) / 2,
    top: (height - cellSize * room.rows) / 2,
  };
}

function pointFor(node, grid) {
  return [
    grid.left + (node.point[0] + 0.5) * grid.cellSize,
    grid.top + (node.point[1] + 0.5) * grid.cellSize,
  ];
}

function routeProgress(route) {
  return Math.min(Math.max(0, elapsed * speed), Math.max(0, route.length - 1));
}

function draw() {
  if (!room) return;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#f3f4f6";
  context.fillRect(0, 0, width, height);

  const grid = layout();
  const nodeById = new Map(room.nodes.map((node) => [node.node, node]));
  const visited = new Set();
  const progressByAgent = new Map();
  for (const [agentId, route] of Object.entries(routes)) {
    const progress = routeProgress(route);
    progressByAgent.set(agentId, progress);
    for (let index = 0; index <= Math.floor(progress) && index < route.length; index += 1) {
      visited.add(route[index]);
    }
  }

  for (const node of room.nodes) {
    const x = grid.left + node.point[0] * grid.cellSize;
    const y = grid.top + node.point[1] * grid.cellSize;
    const inset = Math.max(1, grid.cellSize * 0.035);
    context.fillStyle = node.locked
      ? "#888888"
      : node.dirt && visited.has(node.node)
        ? "#a8d5ba"
        : node.dirt
          ? "#ffe28a"
          : "#ffffff";
    context.fillRect(x + inset, y + inset, grid.cellSize - inset * 2, grid.cellSize - inset * 2);
    context.strokeStyle = "#555555";
    context.lineWidth = 1;
    context.strokeRect(x + inset, y + inset, grid.cellSize - inset * 2, grid.cellSize - inset * 2);
    if (node.locked) {
      context.strokeStyle = "#c8d0db";
      context.beginPath();
      context.moveTo(x + grid.cellSize * 0.3, y + grid.cellSize * 0.3);
      context.lineTo(x + grid.cellSize * 0.7, y + grid.cellSize * 0.7);
      context.moveTo(x + grid.cellSize * 0.7, y + grid.cellSize * 0.3);
      context.lineTo(x + grid.cellSize * 0.3, y + grid.cellSize * 0.7);
      context.stroke();
    } else if (node.dirt && !visited.has(node.node)) {
      context.fillStyle = "#8b5a12";
      context.beginPath();
      context.arc(x + grid.cellSize / 2, y + grid.cellSize / 2, grid.cellSize * 0.12, 0, Math.PI * 2);
      context.fill();
    }
    if (grid.cellSize >= 34) {
      context.fillStyle = node.locked ? "#ffffff" : "#222222";
      context.font = `${Math.max(8, grid.cellSize * 0.19)}px Segoe UI, Arial`;
      context.textAlign = "left";
      context.textBaseline = "top";
      context.fillText(String(node.node), x + 4, y + 3);
    }
  }

  const agentEntries = Object.entries(routes);
  agentEntries.forEach(([agentId, route], agentIndex) => {
    const color = colors[agentIndex % colors.length];
    context.strokeStyle = `${color}80`;
    context.lineWidth = Math.max(2, grid.cellSize * 0.045);
    context.lineJoin = "round";
    context.lineCap = "round";
    context.beginPath();
    route.forEach((nodeId, index) => {
      const node = nodeById.get(nodeId);
      if (!node) return;
      const [x, y] = pointFor(node, grid);
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();

    const progress = progressByAgent.get(agentId) || 0;
    const segment = Math.min(Math.floor(progress), Math.max(0, route.length - 1));
    const currentNode = nodeById.get(route[segment]);
    const nextNode = nodeById.get(route[Math.min(segment + 1, route.length - 1)]);
    if (!currentNode || !nextNode) return;
    const fraction = Math.min(1, progress - segment);
    const [x0, y0] = pointFor(currentNode, grid);
    const [x1, y1] = pointFor(nextNode, grid);
    const x = x0 + (x1 - x0) * fraction;
    const y = y0 + (y1 - y0) * fraction;
    context.fillStyle = color;
    context.strokeStyle = "#333333";
    context.lineWidth = 2;
    context.beginPath();
    context.arc(x, y, Math.max(7, grid.cellSize * 0.28), 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.fillStyle = "#ffffff";
    context.font = `bold ${Math.max(9, grid.cellSize * 0.22)}px Segoe UI, Arial`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(agentId, x, y);
  });

  const dirtyCount = room.nodes.filter((node) => node.dirt && !visited.has(node.node)).length;
  const duration = Math.max(0, ...Object.values(routes).map((route) => (route.length - 1) / speed));
  const status = running ? "Playing" : elapsed >= duration && duration > 0 ? "Finished" : "Paused";
  statusElement.textContent = `${status} · ${agentEntries.length} agent(s) · ${elapsed.toFixed(1)} s`;
  summaryElement.textContent = `${room.rows} × ${room.columns} grid · ${dirtyCount} dirty cell(s) remaining`;
}

async function loadTeam(agentCount) {
  statusElement.textContent = "Loading routes…";
  const response = await fetch(`/api/data?agents=${encodeURIComponent(agentCount)}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.description || payload.message || "Could not load route data.");
  room = payload;
  routes = payload.routes;
  elapsed = 0;
  running = false;
  draw();
}

async function start() {
  const response = await fetch("/api/config");
  const config = await response.json();
  if (!response.ok) throw new Error(config.description || config.message || "Could not load configuration.");
  for (const count of config.agent_counts) {
    const option = document.createElement("option");
    option.value = count;
    option.textContent = `${count} agent(s)`;
    agentSelect.appendChild(option);
  }
  if (!config.agent_counts.length) throw new Error("Generate simulation results before opening the viewer.");
  await loadTeam(config.agent_counts.includes(1) ? 1 : config.agent_counts[0]);
  requestAnimationFrame(animate);
}

function animate(timestamp) {
  if (lastFrame && running) elapsed += Math.min((timestamp - lastFrame) / 1000, 0.05);
  lastFrame = timestamp;
  const duration = Math.max(0, ...Object.values(routes).map((route) => (route.length - 1) / speed));
  if (duration && elapsed >= duration) {
    elapsed = duration;
    running = false;
  }
  draw();
  requestAnimationFrame(animate);
}

document.getElementById("play").addEventListener("click", () => {
  const duration = Math.max(0, ...Object.values(routes).map((route) => (route.length - 1) / speed));
  if (duration && elapsed >= duration) elapsed = 0;
  running = true;
});
document.getElementById("pause").addEventListener("click", () => { running = false; });
document.getElementById("reset").addEventListener("click", () => {
  elapsed = 0;
  running = false;
  draw();
});
agentSelect.addEventListener("change", () => {
  loadTeam(agentSelect.value).catch((error) => { statusElement.textContent = error.message; });
});
window.addEventListener("resize", resizeCanvas);
start()
  .then(resizeCanvas)
  .catch((error) => {
    statusElement.textContent = error.message;
    statusElement.id = "error";
  });
