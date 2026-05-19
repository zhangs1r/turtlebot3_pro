# Training In This Package

This folder is a migrated copy of the paper training project and dataset.

For Chinese beginner-oriented code reading order, see:

- `README_READING_ORDER_ZH.md`

## Content

- Training code: `driver.py`, `runner.py`, `worker.py`, `env.py`, etc.
- Dataset: `maps/` (5663 images)

## Train

```bash
cd ~/turtlebot3_ws/src/turtlebot3_pro/turtlebot3_pro_drl_exploration/training

python3 -m pip install -U pip
python3 -m pip install torch scikit-image matplotlib ray tensorboard

python3 driver.py
```

If you want a fully pinned environment (recommended for Colab reproducibility):

```bash
pip install -r requirements_colab_full.txt
```

## Output

Training outputs are created in this folder:

- `model/<FOLDER_NAME>/checkpoint.pth`
- `train/<FOLDER_NAME>/...`
- `gifs/<FOLDER_NAME>/...`
- `train/<FOLDER_NAME>/progress.csv` (console-friendly progress table)

`FOLDER_NAME` is defined in `parameter.py`.

## Use Trained Model In Simulation

After training, launch exploration with:

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash

ros2 launch turtlebot3_pro_drl_exploration drl_cartographer_explore.launch.py \
  checkpoint_path:=/home/zjq/turtlebot3_ws/src/turtlebot3_pro/turtlebot3_pro_drl_exploration/training/model/<FOLDER_NAME>/checkpoint.pth
```

## Visualize Training Progress

1. TensorBoard:

```bash
tensorboard --logdir train/<FOLDER_NAME> --port 6006
```

If command is not found:

```bash
python3 -m tensorboard.main --logdir train/<FOLDER_NAME> --port 6006
```

2. Quick terminal view:

```bash
tail -f train/<FOLDER_NAME>/progress.csv
```

3. Better curve visualization (new):

```bash
python3 plot_progress.py \
  --csv train/<FOLDER_NAME>/progress.csv \
  --live --smooth 20 --refresh 2
```

Headless/SSH mode (no GUI), keep updating png:

```bash
python3 plot_progress.py \
  --csv train/<FOLDER_NAME>/progress.csv \
  --live --no-show \
  --save train/<FOLDER_NAME>/progress_live.png
```
