# A2 - Multi-agent room cleaning

This project simulates one-agent and multi-agent cleaning in a rectangular grid room. It includes reproducible experiment data, per-agent metrics, professor-compatible route and grid CSVs, a local browser visualizer, tests, and a PDF report.

## Run the experiment

Use Python 3.10 or later. From this folder, install the dependency, run the tests, and generate the report and data:

```powershell
python -m pip install -r requirements.txt
python -m unittest -v
python cleaning_sim.py --output-dir results --trials 20 --agent-counts 1 2 4
python make_videos.py
python web_app.py
```

Use `--student-name` and `--student-id` to personalize the report. Pass the shared video folder with `--video-url`; for example:

```powershell
python cleaning_sim.py --output-dir results --trials 20 --agent-counts 1 2 4 --student-name "Your Name" --student-id "Your ID" --video-url "https://drive.google.com/your-folder"
```

The run compares one, two, and four agents over 20 paired trials. A seed creates one random map that is reused across each team size. Agent starts are distinct random accessible cells, and all starts are shared charging locations. A run stops when all dirt is cleaned, the time limit is reached, or the agents cannot make progress.

The default room is 12 x 12, with 20% dirt, 10% locked cells, 2,000 ticks maximum, and a battery capacity of 80 moves. Movement uses the eight neighboring cells, including diagonals, matching the instructor's adjacency matrix. The default trajectory policy is `local_search`; `zigzag` and `random` policies are also available. The agent reserves at least 5% of its battery to reach a charger.

Configure the experiment with `--rows`, `--columns`, `--dirty-percent`, `--locked-percent`, `--max-time`, `--battery-capacity`, `--strategy`, `--trials`, and `--agent-counts`. For example:

```powershell
python cleaning_sim.py --rows 8 --columns 10 --dirty-percent 25 --locked-percent 10 --max-time 1500 --battery-capacity 60 --strategy zigzag --trials 10 --agent-counts 1 3
```

## Outputs

The output directory contains:

- `A2_report.pdf`: report with the methods, environment, agent architecture, recorded results, measured team-size comparisons, and conclusions.
- `run_results.csv`: one record per trial and team size.
- `agent_metrics.csv`: one record per agent per trial, including movements, unique cells visited, cells cleaned, recharges, and remaining battery.
- `visualization/agents_<count>/Nodes.csv` and `Routes.csv`: map nodes and each agent's actual visited-node sequence, compatible with the instructor's route viewer data shape. `Nodes.csv` also marks locked cells.
- `visualization/agents_<count>/S.csv`, `D.csv`, and `P.csv`: the adjacency, 0.3-meter Euclidean distance, and row-normalized transition-probability matrices.
- `videos/cleaning_1_agent.mp4` and `cleaning_4_agents.mp4`: videos that replay the first trial's recorded routes.

Time is measured in ticks, with one action opportunity per agent per tick. Visited percentage is the union of cells visited divided by accessible cells. Cleaned percentage is cleaned dirt divided by initial dirt; it is 100% for a map with no dirt.

## View the simulation

After generating the results, run `python web_app.py` and open `http://127.0.0.1:5000`. Choose a team size, then use Play, Pause, or Reset to animate its recorded routes. To create MP4 files for the one-agent and four-agent scenarios, run `python make_videos.py`.

## Before submission

- The Colab and Drive examples were reviewed and the route export/viewer follow their `Nodes.csv` and `Routes.csv` format and eight-neighbor grid model. The separate course methodology standard still requires institutional access; compare it with this implementation before submitting.
- The report currently links the shared Drive folder. The assignment requests a YouTube URL, so replace the Drive link if the instructor requires that exact format.
- Push this folder to the repository before using its code URL in the report.
