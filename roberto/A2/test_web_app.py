import csv
import tempfile
import unittest
from pathlib import Path

import web_app


class VisualizationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_directory = web_app.VISUALIZATION_DIR
        web_app.VISUALIZATION_DIR = Path(self.temp_dir.name)
        team_dir = web_app.VISUALIZATION_DIR / "agents_1"
        team_dir.mkdir()
        with (team_dir / "Nodes.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["Node", "Points", "Dirt", "Locked"])
            writer.writeheader()
            writer.writerows([
                {"Node": 0, "Points": "(0, 0, 0)", "Dirt": 1, "Locked": 0},
                {"Node": 1, "Points": "(1, 0, 0)", "Dirt": 0, "Locked": 0},
            ])
        with (team_dir / "Routes.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["Node", "Agent"])
            writer.writeheader()
            writer.writerows([{"Node": 0, "Agent": 1}, {"Node": 1, "Agent": 1}])
        web_app.app.config.update(TESTING=True)
        self.client = web_app.app.test_client()

    def tearDown(self):
        web_app.VISUALIZATION_DIR = self.original_directory
        self.temp_dir.cleanup()

    def test_config_and_route_data_use_exported_csv_files(self):
        config_response = self.client.get("/api/config")
        data_response = self.client.get("/api/data?agents=1")

        self.assertEqual(config_response.status_code, 200)
        self.assertEqual(config_response.json, {"agent_counts": [1]})
        self.assertEqual(data_response.status_code, 200)
        self.assertEqual(data_response.json["routes"], {"1": [0, 1]})
        self.assertEqual(data_response.json["nodes"][0]["dirt"], 1)

    def test_invalid_team_size_returns_json_error(self):
        response = self.client.get("/api/data?agents=invalid")

        self.assertEqual(response.status_code, 400)
        self.assertIn("positive integer", response.json["message"])


if __name__ == "__main__":
    unittest.main()
