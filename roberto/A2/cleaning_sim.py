"""Reproducible grid-room cleaning simulation and assignment report generator."""

from __future__ import annotations

import argparse
import ast
import csv
from html import escape
import math
import random
import statistics
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

Cell = tuple[int, int]
STRATEGIES = ("zigzag", "random", "local_search")


def _grid_neighbors(rows: int, columns: int, locked: set[Cell], cell: Cell) -> Iterable[Cell]:
    row, column = cell
    for row_offset in (-1, 0, 1):
        for column_offset in (-1, 0, 1):
            if row_offset == 0 and column_offset == 0:
                continue
            candidate = (row + row_offset, column + column_offset)
            candidate_row, candidate_column = candidate
            if (
                0 <= candidate_row < rows
                and 0 <= candidate_column < columns
                and candidate not in locked
            ):
                yield candidate


@dataclass
class GridEnvironment:
    rows: int
    columns: int
    locked: set[Cell]
    dirty: set[Cell]

    @classmethod
    def random(
        cls, rows: int, columns: int, dirty_percent: float, locked_percent: float, seed: int
    ) -> GridEnvironment:
        if rows < 1 or columns < 1:
            raise ValueError("Grid dimensions must be positive.")
        if not 0 <= dirty_percent <= 100 or not 0 <= locked_percent <= 100:
            raise ValueError("Dirty and locked percentages must be between 0 and 100.")
        rng = random.Random(seed)
        cells = [(row, column) for row in range(rows) for column in range(columns)]
        locked_count = min(len(cells), math.floor(len(cells) * locked_percent / 100 + 0.5))
        locked = set(rng.sample(cells, locked_count))
        available = [cell for cell in cells if cell not in locked]
        dirty_count = min(len(available), math.floor(len(cells) * dirty_percent / 100 + 0.5))
        dirty = set(rng.sample(available, dirty_count))
        return cls(rows, columns, locked, dirty)


@dataclass
class SimulationConfig:
    rows: int = 12
    columns: int = 12
    num_agents: int = 1
    dirty_percent: float = 20
    locked_percent: float = 10
    max_time: int = 2000
    battery_capacity: int = 80
    strategy: str = "local_search"

    def validate(self) -> None:
        if self.rows < 1 or self.columns < 1:
            raise ValueError("Grid dimensions must be positive.")
        if self.num_agents < 1:
            raise ValueError("At least one agent is required.")
        if self.max_time < 1 or self.battery_capacity < 1:
            raise ValueError("Maximum time and battery capacity must be positive.")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"Strategy must be one of: {', '.join(STRATEGIES)}.")
        if not 0 <= self.dirty_percent <= 100 or not 0 <= self.locked_percent <= 100:
            raise ValueError("Dirty and locked percentages must be between 0 and 100.")


@dataclass
class Agent:
    agent_id: int
    start: Cell
    position: Cell
    battery: int
    rng: random.Random
    moves: int = 0
    recharge_count: int = 0
    visited: set[Cell] = field(default_factory=set)
    cleaned: set[Cell] = field(default_factory=set)
    returning_to_charge: bool = False
    trajectory: list[Cell] = field(default_factory=list)


@dataclass
class SimulationResult:
    seed: int
    agent_count: int
    strategy: str
    status: str
    time_ticks: int
    initial_dirty: int
    cleaned_cells: int
    visited_percent: float
    cleaned_percent: float
    movements_total: int
    locked_cells: int
    accessible_cells: int
    agents: list[dict[str, int | float]]
    trajectories: list[list[Cell]]


class CleaningSimulation:
    """Agents take one action each tick, with sequential collision resolution."""

    def __init__(
        self,
        config: SimulationConfig,
        seed: int,
        environment: GridEnvironment | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.seed = seed
        source_environment = environment or GridEnvironment.random(
            config.rows, config.columns, config.dirty_percent, config.locked_percent, seed
        )
        self.environment = GridEnvironment(
            source_environment.rows,
            source_environment.columns,
            set(source_environment.locked),
            set(source_environment.dirty),
        )
        if (self.environment.rows, self.environment.columns) != (config.rows, config.columns):
            raise ValueError("Environment dimensions do not match the simulation configuration.")
        accessible = sorted(
            (row, column)
            for row in range(config.rows)
            for column in range(config.columns)
            if (row, column) not in self.environment.locked
        )
        if config.num_agents > len(accessible):
            raise ValueError("There are not enough accessible cells for distinct agent starts.")
        rng = random.Random(seed + 1)
        starts = rng.sample(accessible, config.num_agents)
        self.agents = [
            Agent(
                i + 1,
                start,
                start,
                config.battery_capacity,
                random.Random(rng.randrange(2**32)),
                trajectory=[start],
            )
            for i, start in enumerate(starts)
        ]
        self.charging_stations = set(starts)
        self.initial_dirty = len(self.environment.dirty)
        self.accessible_cells = len(accessible)
        self.reserve = max(1, math.ceil(config.battery_capacity * 0.05))

    def _neighbors(self, cell: Cell) -> Iterable[Cell]:
        yield from _grid_neighbors(
            self.config.rows,
            self.config.columns,
            self.environment.locked,
            cell,
        )

    def _path(self, start: Cell, goal: Cell, blocked: set[Cell] | None = None) -> list[Cell] | None:
        if start == goal:
            return []
        blocked_cells = blocked or set()
        queue = deque([start])
        previous: dict[Cell, Cell | None] = {start: None}
        while queue:
            current = queue.popleft()
            for neighbor in self._neighbors(current):
                if neighbor in previous or neighbor in blocked_cells:
                    continue
                previous[neighbor] = current
                if neighbor == goal:
                    path: list[Cell] = []
                    step = goal
                    while step != start:
                        path.append(step)
                        parent = previous[step]
                        assert parent is not None
                        step = parent
                    path.reverse()
                    return path
                queue.append(neighbor)
        return None

    def _nearest_station_path(self, position: Cell, blocked: set[Cell] | None = None) -> list[Cell] | None:
        options = [
            path
            for station in self.charging_stations
            if (path := self._path(position, station, blocked)) is not None
        ]
        return min(options, key=len) if options else None

    def _available_targets(self, agent: Agent, occupied: set[Cell]) -> list[tuple[Cell, list[Cell]]]:
        targets = []
        for target in self.environment.dirty:
            if target in occupied:
                continue
            path = self._path(agent.position, target, occupied)
            if path is None:
                continue
            home_path = self._nearest_station_path(target)
            if home_path is None:
                continue
            if len(path) + len(home_path) + self.reserve <= agent.battery:
                targets.append((target, path))
        return targets

    def _choose_target(self, agent: Agent, targets: list[tuple[Cell, list[Cell]]]) -> tuple[Cell, list[Cell]]:
        if self.config.strategy == "random":
            return agent.rng.choice(targets)
        if self.config.strategy == "zigzag":
            def sweep_key(item: tuple[Cell, list[Cell]]) -> tuple[int, int]:
                row, column = item[0]
                return row, column if row % 2 == 0 else -column

            return min(targets, key=sweep_key)
        return min(targets, key=lambda item: (len(item[1]), item[0]))

    def _clean_current(self, agent: Agent) -> bool:
        agent.visited.add(agent.position)
        if agent.position in self.environment.dirty:
            self.environment.dirty.remove(agent.position)
            agent.cleaned.add(agent.position)
            return True
        return False

    def _move(self, agent: Agent, next_cell: Cell) -> bool:
        if agent.battery <= 0:
            return False
        agent.position = next_cell
        agent.battery -= 1
        agent.moves += 1
        agent.visited.add(next_cell)
        agent.trajectory.append(next_cell)
        return True

    def _return_or_recharge(self, agent: Agent, occupied: set[Cell]) -> tuple[bool, bool]:
        if agent.position in self.charging_stations:
            if agent.returning_to_charge:
                agent.battery = self.config.battery_capacity
                agent.recharge_count += 1
                agent.returning_to_charge = False
                return False, True
            return False, False
        agent.returning_to_charge = True
        path = self._nearest_station_path(agent.position, occupied)
        if not path or len(path) > agent.battery:
            return False, False
        return self._move(agent, path[0]), False

    def run(self) -> SimulationResult:
        if not self.environment.dirty:
            return self._build_result("complete", 0)

        time_ticks = 0
        status = "time_limit"
        for tick in range(1, self.config.max_time + 1):
            moved = cleaned = recharged = False
            order = self.agents[tick % len(self.agents):] + self.agents[:tick % len(self.agents)]
            for agent in order:
                occupied = {other.position for other in self.agents if other is not agent}
                cleaned |= self._clean_current(agent)
                if not self.environment.dirty:
                    break
                if agent.returning_to_charge:
                    agent_moved, agent_recharged = self._return_or_recharge(agent, occupied)
                    moved |= agent_moved
                    recharged |= agent_recharged
                else:
                    targets = self._available_targets(agent, occupied)
                    if targets:
                        _, path = self._choose_target(agent, targets)
                        if path:
                            moved |= self._move(agent, path[0])
                            cleaned |= self._clean_current(agent)
                    elif agent.position not in self.charging_stations:
                        agent.returning_to_charge = True
                        agent_moved, agent_recharged = self._return_or_recharge(agent, occupied)
                        moved |= agent_moved
                        recharged |= agent_recharged
                if not self.environment.dirty:
                    break
            time_ticks = tick
            if not self.environment.dirty:
                status = "complete"
                break
            if not moved and not cleaned and not recharged:
                status = "battery_or_access_limited"
                break

        return self._build_result(status, time_ticks)

    def _build_result(self, status: str, time_ticks: int) -> SimulationResult:
        cleaned_cells = self.initial_dirty - len(self.environment.dirty)
        visited_cells = set().union(*(agent.visited for agent in self.agents))
        return SimulationResult(
            seed=self.seed,
            agent_count=len(self.agents),
            strategy=self.config.strategy,
            status=status,
            time_ticks=time_ticks,
            initial_dirty=self.initial_dirty,
            cleaned_cells=cleaned_cells,
            visited_percent=100 * len(visited_cells) / self.accessible_cells if self.accessible_cells else 0,
            cleaned_percent=100 * cleaned_cells / self.initial_dirty if self.initial_dirty else 100,
            movements_total=sum(agent.moves for agent in self.agents),
            locked_cells=len(self.environment.locked),
            accessible_cells=self.accessible_cells,
            trajectories=[list(agent.trajectory) for agent in self.agents],
            agents=[
                {
                    "agent_id": agent.agent_id,
                    "start_row": agent.start[0],
                    "start_column": agent.start[1],
                    "movements": agent.moves,
                    "unique_cells_visited": len(agent.visited),
                    "cells_cleaned": len(agent.cleaned),
                    "recharges": agent.recharge_count,
                    "battery_remaining": agent.battery,
                }
                for agent in self.agents
            ],
        )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_matrix(path: Path, matrix: list[list[int | float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Node", *range(len(matrix))])
        for node, values in enumerate(matrix):
            writer.writerow([node, *values])


def _write_visualization_files(
    output_dir: Path,
    config: SimulationConfig,
    environment: GridEnvironment,
    result: SimulationResult,
) -> None:
    directory = output_dir / "visualization" / f"agents_{result.agent_count}"
    directory.mkdir(parents=True, exist_ok=True)
    node_rows = []
    for row in range(config.rows):
        for column in range(config.columns):
            cell = (row, column)
            node_rows.append(
                {
                    "Node": row * config.columns + column,
                    "Points": f"({column}, {row}, 0)",
                    "Dirt": int(cell in environment.dirty),
                    "Locked": int(cell in environment.locked),
                }
            )
    route_rows = [
        {"Node": row * config.columns + column, "Agent": agent_id}
        for agent_id, trajectory in enumerate(result.trajectories, start=1)
        for row, column in trajectory
    ]
    _write_csv(directory / "Nodes.csv", node_rows)
    _write_csv(directory / "Routes.csv", route_rows)

    cells = [
        (row, column)
        for row in range(config.rows)
        for column in range(config.columns)
    ]
    adjacency = [[0] * len(cells) for _ in cells]
    for source, cell in enumerate(cells):
        if cell in environment.locked:
            continue
        for neighbor in _grid_neighbors(config.rows, config.columns, environment.locked, cell):
            target = neighbor[0] * config.columns + neighbor[1]
            adjacency[source][target] = 1
    distances = [
        [
            round(0.3 * math.dist(source, target), 6)
            for target in cells
        ]
        for source in cells
    ]
    probabilities = []
    for row in adjacency:
        degree = sum(row)
        probabilities.append([value / degree if degree else 0 for value in row])
    _write_matrix(directory / "S.csv", adjacency)
    _write_matrix(directory / "D.csv", distances)
    _write_matrix(directory / "P.csv", probabilities)


def run_experiment(
    output_dir: Path,
    trials: int = 20,
    rows: int = 12,
    columns: int = 12,
    dirty_percent: float = 20,
    locked_percent: float = 10,
    max_time: int = 2000,
    battery_capacity: int = 80,
    strategy: str = "local_search",
    agent_counts: tuple[int, ...] = (1, 2, 4),
    base_seed: int = 20261111,
    visualization_trial: int = 1,
) -> tuple[list[SimulationResult], list[dict[str, float | int]]]:
    if trials < 1 or not agent_counts:
        raise ValueError("At least one trial and one agent count are required.")
    if not 1 <= visualization_trial <= trials:
        raise ValueError("Visualization trial must be between 1 and the number of trials.")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[SimulationResult] = []
    run_rows: list[dict[str, object]] = []
    agent_rows: list[dict[str, object]] = []
    for trial in range(trials):
        trial_seed = base_seed + trial
        environment = GridEnvironment.random(rows, columns, dirty_percent, locked_percent, trial_seed)
        for count in agent_counts:
            config = SimulationConfig(
                rows, columns, count, dirty_percent, locked_percent, max_time, battery_capacity, strategy
            )
            result = CleaningSimulation(config, trial_seed, environment).run()
            if trial + 1 == visualization_trial:
                _write_visualization_files(output_dir, config, environment, result)
            results.append(result)
            run_rows.append(
                {
                    "trial": trial + 1,
                    "seed": result.seed,
                    "agent_count": result.agent_count,
                    "strategy": result.strategy,
                    "status": result.status,
                    "time_ticks": result.time_ticks,
                    "initial_dirty": result.initial_dirty,
                    "cleaned_cells": result.cleaned_cells,
                    "cleaned_percent": round(result.cleaned_percent, 2),
                    "visited_percent": round(result.visited_percent, 2),
                    "movements_total": result.movements_total,
                    "locked_cells": result.locked_cells,
                    "accessible_cells": result.accessible_cells,
                }
            )
            for metrics in result.agents:
                agent_rows.append(
                    {"trial": trial + 1, "seed": trial_seed, "agent_count": count, **metrics}
                )
    _write_csv(output_dir / "run_results.csv", run_rows)
    _write_csv(output_dir / "agent_metrics.csv", agent_rows)
    return results, summarize_results(results)


def summarize_results(results: list[SimulationResult]) -> list[dict[str, float | int]]:
    summary = []
    for count in sorted({result.agent_count for result in results}):
        group = [result for result in results if result.agent_count == count]
        summary.append(
            {
                "agents": count,
                "trials": len(group),
                "complete_trials": sum(result.status == "complete" for result in group),
                "mean_time_ticks": statistics.mean(result.time_ticks for result in group),
                "sd_time_ticks": statistics.stdev(result.time_ticks for result in group) if len(group) > 1 else 0.0,
                "mean_visited_percent": statistics.mean(result.visited_percent for result in group),
                "mean_cleaned_percent": statistics.mean(result.cleaned_percent for result in group),
                "mean_movements": statistics.mean(result.movements_total for result in group),
                "mean_cells_cleaned": statistics.mean(result.cleaned_cells for result in group),
            }
        )
    return summary


def generate_pdf_report(
    path: Path,
    summary: list[dict[str, float | int]],
    config: SimulationConfig,
    trials: int,
    video_url: str | None = None,
    student_name: str = "Add your name before submission",
    student_id: str = "Add your student ID before submission",
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.graphics.charts.barcharts import VerticalBarChart
    except ImportError as exc:
        raise RuntimeError("PDF generation requires reportlab. Install the requirements.txt dependencies.") from exc

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#17324D")
    blue = colors.HexColor("#2878A5")
    ink = colors.HexColor("#263746")
    pale = colors.HexColor("#EDF3F8")
    styles["BodyText"].fontName = "Helvetica"
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12.5
    styles["BodyText"].textColor = ink
    styles["BodyText"].spaceAfter = 5
    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].fontSize = 13
    styles["Heading1"].leading = 16
    styles["Heading1"].textColor = navy
    styles["Heading1"].spaceBefore = 9
    styles["Heading1"].spaceAfter = 4
    styles.add(ParagraphStyle(
        name="CoverTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="CoverEyebrow", parent=styles["BodyText"], alignment=TA_CENTER,
        fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#B9D7E8"),
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle", parent=styles["BodyText"], alignment=TA_CENTER,
        fontSize=10, leading=14, textColor=colors.HexColor("#E0EAF1"),
    ))
    styles.add(ParagraphStyle(
        name="StudentDetails", parent=styles["BodyText"], fontSize=9, leading=13,
    ))
    styles.add(ParagraphStyle(
        name="FlowBox", parent=styles["BodyText"], alignment=TA_CENTER,
        fontSize=8, leading=10, spaceAfter=0,
    ))
    styles.add(ParagraphStyle(name="SmallNote", parent=styles["BodyText"], fontSize=8, leading=10))
    document = SimpleDocTemplate(
        str(path), pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch,
        topMargin=0.62 * inch, bottomMargin=0.62 * inch,
        title="Multi-Agent Room Cleaning Simulation - Assignment A2",
        author=student_name,
        subject="Room-cleaning multi-agent simulation experiment",
    )
    hero = Table(
        [
            [
            Paragraph("TC2008B  |  ASSIGNMENT A2", styles["CoverEyebrow"]),
            ],
            [
            Paragraph("Multi-Agent Room<br/>Cleaning Simulation", styles["CoverTitle"]),
            ],
            [
            Paragraph("Recorded experiment report", styles["CoverSubtitle"]),
            ],
        ],
        colWidths=[7.2 * inch],
    )
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), navy),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    student_details = Table(
        [[
            Paragraph(f"<b>Student</b><br/>{escape(student_name)}", styles["StudentDetails"]),
            Paragraph(f"<b>Student ID</b><br/>{escape(student_id)}", styles["StudentDetails"]),
        ]],
        colWidths=[4.6 * inch, 2.6 * inch],
    )
    student_details.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D5E0E8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story = [
        hero,
        Spacer(1, 10),
        student_details,
        Spacer(1, 4),
        Paragraph("1. Introduction", styles["Heading1"]),
        Paragraph(
            "The room is an M x N grid. Agents clean dirty cells and cannot enter locked cells. "
            "The experiment compares one, two, and four agents on the same randomly generated maps.",
            styles["BodyText"],
        ),
        Paragraph("2. Problem and solution", styles["Heading1"]),
        Paragraph(
            "The goal is to clean as much dirt as possible before time runs out. The program finds paths through "
            "open cells, avoids occupied cells, and keeps at least 5% battery for returning to a charger. "
            "Every agent's starting cell can be used to recharge. A run stops when the room is clean, the time "
            "limit is reached, or no agent can continue.",
            styles["BodyText"],
        ),
        Paragraph("3. Methods and environment", styles["Heading1"]),
        Paragraph(
            f"Each room is {config.rows} rows by {config.columns} columns. In each trial, locked cells and "
            f"dirt cells are sampled uniformly without replacement; dirt is sampled only from unlocked cells. "
            f"The requested dirt density is {config.dirty_percent:g}% and locked density is "
            f"{config.locked_percent:g}%. Agent starts are distinct random accessible cells. Maximum duration "
            f"is {config.max_time} ticks and battery capacity is {config.battery_capacity} moves "
            f"({max(1, math.ceil(config.battery_capacity * 0.05))} moves reserved, at least 5%). "
            f"The trajectory policy is {config.strategy}.",
            styles["BodyText"],
        ),
        Paragraph(
            f"There are {trials} paired trials for each team size. Each paired set uses the same dirt/obstacle "
            "map for each team size. Each tick gives every agent one movement opportunity. Agents take turns "
            "in a rotating order, so they do not move into a cell occupied by another agent. Starts are random "
            "open cells and are shared charging points. Movement includes diagonal neighbors; locked cells are "
            "not valid destinations.",
            styles["BodyText"],
        ),
    ]
    room_drawing = _room_map_drawing(
        path.parent / "visualization" / "agents_1" / "Nodes.csv",
        Drawing,
        Rect,
        String,
        colors,
    )
    if room_drawing is not None:
        story.extend([
            Paragraph("Trial 1 room layout (one-agent case)", styles["BodyText"]),
            room_drawing,
            Spacer(1, 4),
        ])
    flow_diagram = Table(
        [[
            Paragraph("<b>1 · Observe</b><br/>Read the map and find remaining dirt", styles["FlowBox"]),
            Paragraph("›", styles["FlowBox"]),
            Paragraph("<b>2 · Plan</b><br/>Choose reachable dirt; reserve 5% battery", styles["FlowBox"]),
            Paragraph("›", styles["FlowBox"]),
            Paragraph("<b>3 · Act</b><br/>Move, avoid obstacles, and clean", styles["FlowBox"]),
            Paragraph("›", styles["FlowBox"]),
            Paragraph("<b>4 · Recharge</b><br/>Return to any agent start cell", styles["FlowBox"]),
        ]],
        colWidths=[1.68 * inch, 0.12 * inch, 1.68 * inch, 0.12 * inch, 1.68 * inch, 0.12 * inch, 1.68 * inch],
    )
    flow_diagram.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), pale),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#E5F1F4")),
        ("BACKGROUND", (4, 0), (4, 0), pale),
        ("BACKGROUND", (6, 0), (6, 0), colors.HexColor("#E5F1F4")),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#D5E0E8")),
        ("BOX", (2, 0), (2, 0), 0.5, colors.HexColor("#D5E0E8")),
        ("BOX", (4, 0), (4, 0), 0.5, colors.HexColor("#D5E0E8")),
        ("BOX", (6, 0), (6, 0), 0.5, colors.HexColor("#D5E0E8")),
        ("TEXTCOLOR", (1, 0), (5, 0), blue),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([
        Paragraph("4. Agent objective, architecture, and interaction", styles["Heading1"]),
        Paragraph(
            "An agent's goal is to clean available dirt. The default local-search strategy chooses the nearest "
            "reachable dirty cell. The program also has zigzag and random target strategies. Agents share the "
            "same map, clean cells they enter, avoid other agents, and can recharge at any starting point. "
            "The program records each agent's moves, visited cells, cleaned cells, recharges, and battery.",
            styles["BodyText"],
        ),
        flow_diagram,
        Spacer(1, 5),
        Paragraph("5. Recorded simulation data", styles["Heading1"]),
        Paragraph(
            "run_results.csv contains one row per trial and team size. agent_metrics.csv contains one row per "
            "agent per trial. Visited percentage is the number of unique open cells visited divided by the "
            "number of open cells. Cleaned percentage is the number of dirt cells cleaned divided by the "
            "initial dirt count. It is 100% when the map has no dirt.",
            styles["BodyText"],
        ),
        Paragraph(
            "Each team-size folder under visualization contains Nodes.csv and Routes.csv for the first trial. "
            "It also contains S.csv (valid neighboring cells), D.csv (distance using 0.3 meters per grid unit), "
            "and P.csv (equal probability for each valid neighbor).",
            styles["BodyText"],
        ),
    ])
    headers = [
        ["Agents", "Trials", "Complete", "Mean time (ticks)", "SD time", "Visited (%)", "Cleaned (%)", "Moves"],
    ]
    for row in summary:
        headers.append([
            str(row["agents"]), str(row["trials"]), str(row["complete_trials"]),
            f'{row["mean_time_ticks"]:.1f}', f'{row["sd_time_ticks"]:.1f}',
            f'{row["mean_visited_percent"]:.1f}', f'{row["mean_cleaned_percent"]:.1f}',
            f'{row["mean_movements"]:.1f}',
        ])
    results_table = Table(headers, repeatRows=1, hAlign="LEFT")
    results_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B56")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF2F8")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([Spacer(1, 8), results_table, Spacer(1, 12)])

    chart = Drawing(450, 180)
    bars = VerticalBarChart()
    bars.x = 50
    bars.y = 35
    bars.height = 120
    bars.width = 360
    bars.data = [[float(row["mean_time_ticks"]) for row in summary]]
    bars.categoryAxis.categoryNames = [str(row["agents"]) + " agent(s)" for row in summary]
    bars.categoryAxis.labels.boxAnchor = "n"
    bars.valueAxis.valueMin = 0
    bars.valueAxis.valueMax = max(1, max(float(row["mean_time_ticks"]) for row in summary) * 1.15)
    bars.valueAxis.valueStep = max(1, int(bars.valueAxis.valueMax / 5))
    bars.bars[0].fillColor = colors.HexColor("#586675")
    chart.add(bars)
    chart.add(String(130, 165, "Mean completion time by team size", fontSize=10))
    story.append(chart)

    video_link = (
        f'Google Drive folder with the simulation videos: <link href="{escape(video_url, quote=True)}" '
        f'color="blue">Open the video folder</link>. The assignment asks for a YouTube URL; '
        "replace this with the YouTube link if that format is required."
        if video_url
        else "YouTube simulation video: [ADD THE YOUTUBE URL AFTER RECORDING AND UPLOADING]."
    )
    story.extend([
        Paragraph("6. Effect of adding agents", styles["Heading1"]),
        Paragraph(
            _agent_effect_analysis(summary),
            styles["BodyText"],
        ),
        Paragraph("7. Products and reproducibility", styles["Heading1"]),
        Paragraph(
            'Code repository: <link href="https://github.com/JohannSOVCP/multiagentsindividual/tree/main/roberto/A2" '
            'color="blue">https://github.com/JohannSOVCP/multiagentsindividual/tree/main/roberto/A2</link>. '
            "The repository link will be available to the instructor after the project is uploaded.",
            styles["BodyText"],
        ),
        Paragraph(video_link, styles["BodyText"]),
        Paragraph(
            "Reproduce with: python cleaning_sim.py --output-dir results --trials 20. "
            "This creates the run and agent CSVs plus visualization/agents_<count> route data. "
            "Run python web_app.py and open http://127.0.0.1:5000 to view the recorded agent paths.",
            styles["BodyText"],
        ),
        Paragraph("8. Conclusions", styles["Heading1"]),
        Paragraph(
            "The simulation operationalizes a constrained multi-agent cleaning problem with random dirt and "
            "locked cells and limited batteries. In these trials, teams with more agents cleaned the maps in "
            "fewer ticks on average. Their total movement can also change because agents share the work and "
            "the same charging points. These results only describe the settings used here. Add the video link "
            "and check the method against the course standard before submitting.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        Paragraph(
            "Methodology note: The linked course standard redirects to an authenticated campus SSO page in this "
            "workspace and could not be inspected. This report follows the requirements in the assignment prompt; "
            "check it against the downloadable standard before final submission.",
            styles["SmallNote"],
        ),
    ])

    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        page_width, page_height = letter
        canvas.setFillColor(navy)
        canvas.rect(0, page_height - 0.14 * inch, page_width, 0.14 * inch, stroke=0, fill=1)
        canvas.setStrokeColor(colors.HexColor("#D5E0E8"))
        canvas.line(0.65 * inch, 0.48 * inch, page_width - 0.65 * inch, 0.48 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#627384"))
        canvas.drawString(0.65 * inch, 0.31 * inch, f"TC2008B · A2 · {student_name} · {student_id}")
        canvas.drawRightString(page_width - 0.65 * inch, 0.31 * inch, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)


def _room_map_drawing(nodes_path: Path, Drawing, Rect, String, colors):
    if not nodes_path.is_file():
        return None

    nodes = []
    with nodes_path.open("r", newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            x, y, *_ = ast.literal_eval(row["Points"])
            nodes.append((int(x), int(y), bool(int(row["Dirt"])), bool(int(row["Locked"]))))
    if not nodes:
        return None

    columns = max(node[0] for node in nodes) + 1
    rows = max(node[1] for node in nodes) + 1
    cell = min(12, 150 / columns, 150 / rows)
    grid_x, grid_y = 16, 20
    drawing = Drawing(475, 185)
    drawing.add(String(16, 168, "Randomized environment · trial 1", fontName="Helvetica-Bold", fontSize=9, fillColor=colors.HexColor("#263746")))
    for x, y, dirty, locked in nodes:
        fill = colors.HexColor("#8795A5") if locked else (
            colors.HexColor("#F3C969") if dirty else colors.HexColor("#EEF3F7")
        )
        drawing.add(Rect(
            grid_x + x * cell,
            grid_y + (rows - 1 - y) * cell,
            cell - 1,
            cell - 1,
            fillColor=fill,
            strokeColor=colors.white,
            strokeWidth=0.6,
        ))

    legend_x = grid_x + columns * cell + 24
    legend_items = [
        (colors.HexColor("#F3C969"), "Dirty cell"),
        (colors.HexColor("#8795A5"), "Locked cell"),
        (colors.HexColor("#EEF3F7"), "Open cell"),
    ]
    for index, (fill, label) in enumerate(legend_items):
        y = 124 - index * 24
        drawing.add(Rect(legend_x, y, 13, 13, fillColor=fill, strokeColor=colors.HexColor("#AAB7C4"), strokeWidth=0.5))
        drawing.add(String(legend_x + 21, y + 3, label, fontName="Helvetica", fontSize=8, fillColor=colors.HexColor("#263746")))
    drawing.add(String(legend_x, 38, f"{rows} × {columns} cells", fontName="Helvetica-Bold", fontSize=8, fillColor=colors.HexColor("#263746")))
    return drawing


def _agent_effect_analysis(summary: list[dict[str, float | int]]) -> str:
    baseline = next((row for row in summary if row["agents"] == 1), None)
    if baseline is None:
        return (
            "The experiment compares elapsed time, completion rate, visited and cleaned percentages, "
            "and total movements across team sizes. Each additional agent receives a movement opportunity "
            "per tick, but agents also compete for space and share dirt targets, so more agents do not "
            "guarantee a proportional speedup. See the table for the measured results."
        )

    baseline_time = float(baseline["mean_time_ticks"])
    details = []
    for row in summary:
        if row["agents"] == 1:
            continue
        time_change = (
            100 * (baseline_time - float(row["mean_time_ticks"])) / baseline_time
            if baseline_time
            else 0
        )
        movement_change = (
            100
            * (float(row["mean_movements"]) - float(baseline["mean_movements"]))
            / float(baseline["mean_movements"])
            if float(baseline["mean_movements"])
            else 0
        )
        direction = "lower" if time_change >= 0 else "higher"
        details.append(
            f'{row["agents"]} agents averaged {float(row["mean_time_ticks"]):.1f} ticks '
            f"({abs(time_change):.1f}% {direction} than one agent), "
            f'{float(row["complete_trials"]):.0f}/{int(row["trials"])} completed, and '
            f'{movement_change:+.1f}% total movements'
        )

    comparisons = "; ".join(details)
    return (
        f"Compared with one agent ({baseline_time:.1f} mean ticks; "
        f'{float(baseline["complete_trials"]):.0f}/{int(baseline["trials"])} completed), '
        f"{comparisons}. More agents can reduce elapsed ticks because each receives one movement "
        "opportunity per tick. Speedup is not guaranteed to be proportional: agents compete for space "
        "and share a finite set of dirt targets. Changes in total movements show the additional travel "
        "and coordination cost. These results describe only the tested maps, battery, policy, and seeds."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--rows", type=int, default=12)
    parser.add_argument("--columns", type=int, default=12)
    parser.add_argument("--dirty-percent", type=float, default=20)
    parser.add_argument("--locked-percent", type=float, default=10)
    parser.add_argument("--max-time", type=int, default=2000)
    parser.add_argument("--battery-capacity", type=int, default=80)
    parser.add_argument("--strategy", choices=STRATEGIES, default="local_search")
    parser.add_argument("--agent-counts", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--video-url", help="URL of the shared folder containing simulation videos")
    parser.add_argument("--student-name", default="Add your name before submission")
    parser.add_argument("--student-id", default="Add your student ID before submission")
    args = parser.parse_args()
    config = SimulationConfig(
        args.rows, args.columns, 1, args.dirty_percent, args.locked_percent,
        args.max_time, args.battery_capacity, args.strategy,
    )
    config.validate()
    results, summary = run_experiment(
        args.output_dir, args.trials, args.rows, args.columns, args.dirty_percent,
        args.locked_percent, args.max_time, args.battery_capacity, args.strategy,
        tuple(args.agent_counts),
    )
    generate_pdf_report(
        args.output_dir / "A2_report.pdf",
        summary,
        config,
        args.trials,
        args.video_url,
        args.student_name,
        args.student_id,
    )
    print(f"Generated {args.output_dir / 'A2_report.pdf'}")
    for row in summary:
        print(
            f'{row["agents"]} agents: time={row["mean_time_ticks"]:.1f} ticks, '
            f'cleaned={row["mean_cleaned_percent"]:.1f}%, '
            f'visited={row["mean_visited_percent"]:.1f}% '
            f'({row["complete_trials"]}/{row["trials"]} complete)'
        )


if __name__ == "__main__":
    main()
