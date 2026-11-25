"""Create MP4 route replays from the exported simulation CSV files."""

import argparse
import ast
import csv
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
WIDTH = 960
HEIGHT = 720
FPS = 12
FRAMES_PER_MOVE = 4
COLORS = ("#2563eb", "#dc2626", "#7c3aed", "#ea580c", "#16834a", "#a21caf")
ROUTE_COLORS = ("#9bb8f5", "#f0a2a2", "#b8a8e8", "#edbc9e", "#9acaa9", "#d4a0d4")


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = ("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_route_data(agent_count: int) -> tuple[list[dict[str, object]], dict[int, list[int]]]:
    directory = RESULTS_DIR / "visualization" / f"agents_{agent_count}"
    nodes_path = directory / "Nodes.csv"
    routes_path = directory / "Routes.csv"
    if not nodes_path.is_file() or not routes_path.is_file():
        raise FileNotFoundError(
            f"Missing route data for {agent_count} agents. Run cleaning_sim.py first."
        )

    nodes = []
    with nodes_path.open("r", newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            point = ast.literal_eval(row["Points"])
            nodes.append(
                {
                    "id": int(row["Node"]),
                    "x": float(point[0]),
                    "y": float(point[1]),
                    "dirt": int(row["Dirt"]),
                    "locked": int(row["Locked"]),
                }
            )
    nodes_by_id = {int(node["id"]): node for node in nodes}

    routes: dict[int, list[int]] = {}
    with routes_path.open("r", newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            node_id = int(row["Node"])
            agent_id = int(row["Agent"])
            if node_id not in nodes_by_id:
                raise ValueError(f"Route for agent {agent_id} references unknown node {node_id}.")
            if nodes_by_id[node_id]["locked"]:
                raise ValueError(f"Route for agent {agent_id} enters locked node {node_id}.")
            routes.setdefault(agent_id, []).append(node_id)
    if set(routes) != set(range(1, agent_count + 1)):
        raise ValueError(f"Expected route data for agents 1 through {agent_count}.")
    return nodes, routes


def _draw_frame(
    nodes: list[dict[str, object]],
    routes: dict[int, list[int]],
    progress: float,
    title: str,
    team_size: int,
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((32, 24), title, fill="#222222", font=_font(28, bold=True))
    draw.text(
        (32, 64),
        f"Trial 1 · {team_size} agent(s) · route replay",
        fill="#444444",
        font=_font(18),
    )

    rows = int(max(float(node["y"]) for node in nodes)) + 1
    columns = int(max(float(node["x"]) for node in nodes)) + 1
    cell_size = min(560 // columns, 560 // rows)
    grid_width = cell_size * columns
    grid_height = cell_size * rows
    left = (WIDTH - grid_width) // 2
    top = 112 + (560 - grid_height) // 2
    node_by_id = {int(node["id"]): node for node in nodes}
    visited: set[int] = set()
    route_positions: dict[int, tuple[float, float]] = {}

    for agent_id, route in routes.items():
        agent_progress = min(progress, max(0, len(route) - 1))
        segment = min(int(agent_progress), max(0, len(route) - 1))
        visited.update(route[: segment + 1])
        start_node = node_by_id[route[segment]]
        next_node = node_by_id[route[min(segment + 1, len(route) - 1)]]
        fraction = agent_progress - segment
        route_positions[agent_id] = (
            float(start_node["x"]) + (float(next_node["x"]) - float(start_node["x"])) * fraction,
            float(start_node["y"]) + (float(next_node["y"]) - float(start_node["y"])) * fraction,
        )

    for node in nodes:
        x = left + int(float(node["x"]) * cell_size)
        y = top + int(float(node["y"]) * cell_size)
        box = (x + 1, y + 1, x + cell_size - 1, y + cell_size - 1)
        if node["locked"]:
            color = "#888888"
        elif node["dirt"] and int(node["id"]) in visited:
            color = "#a8d5ba"
        elif node["dirt"]:
            color = "#ffe28a"
        else:
            color = "#ffffff"
        draw.rectangle(box, fill=color, outline="#555555", width=2)
        if node["locked"]:
            margin = cell_size // 4
            draw.line((x + margin, y + margin, x + cell_size - margin, y + cell_size - margin), fill="white", width=2)
            draw.line((x + cell_size - margin, y + margin, x + margin, y + cell_size - margin), fill="white", width=2)
        elif node["dirt"] and int(node["id"]) not in visited:
            radius = max(3, cell_size // 9)
            center = (x + cell_size // 2, y + cell_size // 2)
            draw.ellipse(
                (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                fill="#8b5a12",
            )

    for agent_id, route in routes.items():
        color_index = (agent_id - 1) % len(COLORS)
        points = [
            (
                left + int(float(node_by_id[node_id]["x"]) * cell_size) + cell_size // 2,
                top + int(float(node_by_id[node_id]["y"]) * cell_size) + cell_size // 2,
            )
            for node_id in route
        ]
        if len(points) > 1:
            draw.line(points, fill=ROUTE_COLORS[color_index], width=3, joint="curve")
        route_x, route_y = route_positions[agent_id]
        center_x = left + int((route_x + 0.5) * cell_size)
        center_y = top + int((route_y + 0.5) * cell_size)
        radius = max(10, cell_size // 4)
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=COLORS[color_index],
            outline="#222222",
            width=2,
        )
        draw.text(
            (center_x, center_y),
            str(agent_id),
            fill="#ffffff",
            font=_font(14, bold=True),
            anchor="mm",
        )

    dirty_total = sum(bool(node["dirt"]) for node in nodes)
    dirt_remaining = sum(
        bool(node["dirt"]) and int(node["id"]) not in visited for node in nodes
    )
    draw.text(
        (32, HEIGHT - 40),
        f"Dirty cells cleaned: {dirty_total - dirt_remaining} / {dirty_total}",
        fill="#333333",
        font=_font(18),
    )
    return image


def _write_video(path: Path, frames: list[Image.Image]) -> None:
    writer = imageio_ffmpeg.write_frames(
        str(path),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        quality=8,
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
    )
    writer.send(None)
    try:
        for frame in frames:
            writer.send(frame.tobytes())
    finally:
        writer.close()


def make_video(agent_count: int, output_dir: Path) -> Path:
    nodes, routes = _load_route_data(agent_count)
    max_moves = max(len(route) - 1 for route in routes.values())
    progress_steps = max(1, max_moves * FRAMES_PER_MOVE)
    title = f"Room cleaning: {agent_count} agent(s)"
    frames = [
        _draw_frame(nodes, routes, 0, title, agent_count)
        for _ in range(FPS)
    ]
    for frame_index in range(progress_steps + 1):
        progress = frame_index / FRAMES_PER_MOVE
        frames.append(_draw_frame(nodes, routes, progress, title, agent_count))
    final_frame = _draw_frame(nodes, routes, max_moves, title, agent_count)
    frames.extend(final_frame.copy() for _ in range(FPS * 2))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"cleaning_{agent_count}_agent{'s' if agent_count != 1 else ''}.mp4"
    _write_video(output_path, frames)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-counts", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR / "videos")
    args = parser.parse_args()
    if not args.agent_counts or any(count < 1 for count in args.agent_counts):
        parser.error("--agent-counts must contain positive integers.")
    for count in args.agent_counts:
        video_path = make_video(count, args.output_dir)
        print(f"Generated {video_path}")


if __name__ == "__main__":
    main()
