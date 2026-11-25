import unittest
import csv
import math
import tempfile
from pathlib import Path

from cleaning_sim import (
    CleaningSimulation,
    GridEnvironment,
    SimulationConfig,
    _grid_neighbors,
    run_experiment,
    summarize_results,
)


class CleaningSimulationTests(unittest.TestCase):
    def test_random_environment_keeps_dirt_out_of_locked_cells(self):
        environment = GridEnvironment.random(10, 10, 25, 15, seed=4)
        self.assertEqual(len(environment.locked), 15)
        self.assertEqual(len(environment.dirty), 25)
        self.assertTrue(environment.locked.isdisjoint(environment.dirty))

    def test_all_trajectory_policies_clean_a_small_room(self):
        for strategy in ("zigzag", "random", "local_search"):
            config = SimulationConfig(
                rows=4, columns=4, num_agents=1, dirty_percent=25, locked_percent=0,
                max_time=100, battery_capacity=30, strategy=strategy,
            )
            result = CleaningSimulation(config, seed=10).run()
            self.assertEqual(result.status, "complete", strategy)
            self.assertEqual(result.cleaned_percent, 100, strategy)
            self.assertLessEqual(result.visited_percent, 100, strategy)

    def test_agents_start_distinctly_and_can_charge_at_all_starts(self):
        config = SimulationConfig(rows=5, columns=5, num_agents=4, battery_capacity=30)
        simulation = CleaningSimulation(config, seed=3)
        starts = {agent.start for agent in simulation.agents}
        self.assertEqual(len(starts), 4)
        self.assertEqual(simulation.charging_stations, starts)

    def test_locked_cells_are_not_visited_and_battery_never_exceeds_capacity(self):
        environment = GridEnvironment.random(6, 6, 30, 10, seed=22)
        config = SimulationConfig(
            rows=6, columns=6, num_agents=2, max_time=300, battery_capacity=35
        )
        simulation = CleaningSimulation(config, seed=22, environment=environment)
        result = simulation.run()
        for agent, metrics in zip(simulation.agents, result.agents):
            self.assertTrue(agent.visited.isdisjoint(environment.locked))
            self.assertGreaterEqual(int(metrics["battery_remaining"]), 0)
            self.assertLessEqual(int(metrics["battery_remaining"]), config.battery_capacity)

    def test_summary_is_grouped_by_agent_count(self):
        config = SimulationConfig(rows=4, columns=4, num_agents=1, battery_capacity=30)
        result = CleaningSimulation(config, seed=5).run()
        summary = summarize_results([result])
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["agents"], 1)
        self.assertEqual(summary[0]["trials"], 1)

    def test_running_a_simulation_does_not_mutate_a_reusable_map(self):
        environment = GridEnvironment.random(4, 4, 25, 0, seed=8)
        original_dirt = set(environment.dirty)
        config = SimulationConfig(rows=4, columns=4, battery_capacity=30)
        CleaningSimulation(config, seed=8, environment=environment).run()
        self.assertEqual(environment.dirty, original_dirt)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            CleaningSimulation(SimulationConfig(num_agents=0), seed=1)

    def test_room_without_dirt_finishes_without_elapsed_ticks(self):
        environment = GridEnvironment(rows=2, columns=2, locked=set(), dirty=set())
        config = SimulationConfig(rows=2, columns=2, battery_capacity=5)

        result = CleaningSimulation(config, seed=1, environment=environment).run()

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.time_ticks, 0)
        self.assertEqual(result.cleaned_percent, 100)

    def test_grid_neighbors_match_eight_direction_cell_model(self):
        neighbors = set(_grid_neighbors(3, 3, set(), (1, 1)))
        self.assertEqual(len(neighbors), 8)
        self.assertEqual(len(set(_grid_neighbors(3, 3, set(), (0, 0)))), 3)
        self.assertNotIn((1, 1), neighbors)

    def test_run_exports_professor_compatible_routes_and_matrices(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            results, _ = run_experiment(
                output_dir=output_dir,
                trials=1,
                rows=4,
                columns=4,
                dirty_percent=25,
                locked_percent=12.5,
                max_time=100,
                battery_capacity=30,
                agent_counts=(1, 2),
                base_seed=5,
            )

            for result in results:
                directory = output_dir / "visualization" / f"agents_{result.agent_count}"
                with (directory / "Nodes.csv").open(newline="", encoding="utf-8") as file:
                    nodes = list(csv.DictReader(file))
                with (directory / "Routes.csv").open(newline="", encoding="utf-8") as file:
                    route_rows = list(csv.DictReader(file))
                self.assertEqual(len(nodes), 16)
                self.assertEqual(set(nodes[0]), {"Node", "Points", "Dirt", "Locked"})
                for agent_id, trajectory in enumerate(result.trajectories, start=1):
                    exported = [
                        int(row["Node"])
                        for row in route_rows
                        if int(row["Agent"]) == agent_id
                    ]
                    self.assertEqual(
                        exported,
                        [row * 4 + column for row, column in trajectory],
                    )

                with (directory / "S.csv").open(newline="", encoding="utf-8") as file:
                    adjacency = list(csv.reader(file))[1:]
                with (directory / "P.csv").open(newline="", encoding="utf-8") as file:
                    probabilities = list(csv.reader(file))[1:]
                self.assertEqual(len(adjacency), 16)
                self.assertEqual(len(probabilities), 16)
                for row_index, row in enumerate(probabilities):
                    total = sum(float(value) for value in row[1:])
                    self.assertTrue(math.isclose(total, 0) or math.isclose(total, 1))
                    self.assertEqual(
                        sum(int(value) for value in adjacency[row_index][1:]) > 0,
                        math.isclose(total, 1),
                    )


if __name__ == "__main__":
    unittest.main()
