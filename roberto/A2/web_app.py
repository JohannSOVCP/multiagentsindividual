"""Flask API and local browser viewer for exported simulation routes."""

import ast
import csv
import re
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


BASE_DIR = Path(__file__).resolve().parent
VISUALIZATION_DIR = BASE_DIR / "results" / "visualization"
app = Flask(__name__)


@app.errorhandler(HTTPException)
def handle_http_error(error: HTTPException):
    if request.path.startswith("/api/"):
        return jsonify({"message": error.description}), error.code
    return error


def _available_agent_counts() -> list[int]:
    counts = []
    for path in VISUALIZATION_DIR.iterdir() if VISUALIZATION_DIR.exists() else ():
        match = re.fullmatch(r"agents_(\d+)", path.name)
        if path.is_dir() and match:
            counts.append(int(match.group(1)))
    return sorted(counts)


def _read_nodes(path: Path) -> dict[int, dict[str, object]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        expected = {"Node", "Points", "Dirt", "Locked"}
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain the columns: {', '.join(sorted(expected))}.")

        nodes = {}
        for row in reader:
            node_id = int(row["Node"])
            point = ast.literal_eval(row["Points"])
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                raise ValueError(f"Node {node_id} has invalid 3D coordinates.")
            if node_id in nodes:
                raise ValueError(f"Node {node_id} is duplicated in {path}.")
            nodes[node_id] = {
                "node": node_id,
                "point": [float(value) for value in point],
                "dirt": int(row["Dirt"]),
                "locked": int(row["Locked"]),
            }
    return nodes


def _read_routes(path: Path, nodes: dict[int, dict[str, object]]) -> dict[str, list[int]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"Node", "Agent"}.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain the columns Node and Agent.")

        routes: dict[str, list[int]] = {}
        for row in reader:
            node_id = int(row["Node"])
            agent_id = int(row["Agent"])
            if node_id not in nodes:
                raise ValueError(f"Route references unknown node {node_id}.")
            if nodes[node_id]["locked"]:
                raise ValueError(f"Route for agent {agent_id} enters locked node {node_id}.")
            routes.setdefault(str(agent_id), []).append(node_id)
    return routes


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def config():
    counts = _available_agent_counts()
    if not counts:
        abort(404, description="Run cleaning_sim.py first to create visualization CSV files.")
    return jsonify({"agent_counts": counts})


@app.get("/api/data")
def data():
    raw_agent_count = request.args.get("agents", "1")
    try:
        agent_count = int(raw_agent_count)
    except ValueError:
        abort(400, description="The agents parameter must be a positive integer.")
    if agent_count < 1:
        abort(400, description="The agents parameter must be a positive integer.")

    directory = VISUALIZATION_DIR / f"agents_{agent_count}"
    nodes_path = directory / "Nodes.csv"
    routes_path = directory / "Routes.csv"
    if not nodes_path.is_file() or not routes_path.is_file():
        abort(404, description=f"No exported routes were found for {agent_count} agents.")

    nodes = _read_nodes(nodes_path)
    routes = _read_routes(routes_path, nodes)
    columns = max(int(node["point"][0]) for node in nodes.values()) + 1
    rows = max(int(node["point"][1]) for node in nodes.values()) + 1
    return jsonify(
        {
            "rows": rows,
            "columns": columns,
            "nodes": list(nodes.values()),
            "routes": routes,
        }
    )


if __name__ == "__main__":
    if not _available_agent_counts():
        raise SystemExit("Run cleaning_sim.py first to generate results\\visualization route files.")
    app.run(host="127.0.0.1", port=5000, debug=False)
