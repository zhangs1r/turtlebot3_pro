# turtlebot3_pro_drl_exploration

在 `turtlebot3_pro` 工作区中把论文
`Deep Reinforcement Learning-Based Large-Scale Robot Exploration`
迁移为可在 `sim_all.launch.py` 环境运行的 ROS 2 探索栈：

- `sim_all` 起 Gazebo 仿真
- `cartographer` 提供在线栅格地图
- `nav2` 执行局部/全局导航
- `drl_explorer` 作为高层决策器，输出下一段探索目标点

## 1) 迁移后的决策逻辑

论文原始策略是“图节点一步决策下一步”：
- 每次从当前节点邻居中选一个下一节点
- 执行后再基于新观测重新决策

本包保留这个思路，同时支持你提出的 MPC 风格改法：
- `use_lookahead=true` 时，先对候选动作做多步滚动评估
- 实际只下发第一步目标给 Nav2
- 下一周期重算（receding horizon）

## 2) 目录说明

- `launch/drl_cartographer_explore.launch.py`
  - 一键启动 Gazebo + Cartographer + Nav2 + DRL
- `turtlebot3_pro_drl_exploration/drl_explorer_node.py`
  - 订阅 `/map`
  - 读取 `map -> base_link` TF
  - 运行图策略并调用 `/navigate_to_pose`
- `config/drl_explorer.yaml`
  - DRL 节点参数（含 lookahead）
- `config/nav2_params_cartographer_drl.yaml`
  - 针对 TurtleBot3 Pro + Cartographer 的 Nav2 参数
- `turtlebot3_pro_drl_exploration/paper_core/*`
  - 论文推理核心模块（模型、图管理、agent）
- `training/*`
  - 已迁移的论文训练工程（含 `maps` 训练数据集）

## 3) 训练后如何迁移到仿真

1. 在论文工程中训练出 checkpoint（`checkpoint.pth`）
2. 启动本包时通过 launch 参数传入 `checkpoint_path`
3. DRL 节点读取 checkpoint 的 `policy_model` 权重并在线推理
4. 每次推理输出“下一段目标点”，由 Nav2 负责避障与轨迹跟踪

如果暂时没有 checkpoint：
- 节点会自动退化到 `utility` 策略（按前沿效用选邻居）
- 用于先验证“感知-决策-导航”整条链路

## 4) 运行

```bash
cd ~/turtlebot3_ws
colcon build --packages-select turtlebot3_pro_drl_exploration
source install/setup.bash

ros2 launch turtlebot3_pro_drl_exploration drl_cartographer_explore.launch.py \
  world_file:=warehouse_grid.world \
  checkpoint_path:=/ABS/PATH/TO/checkpoint.pth
```

如果先不用 DRL 权重，改为 utility 试运行：

```bash
ros2 launch turtlebot3_pro_drl_exploration drl_cartographer_explore.launch.py \
  checkpoint_path:="" \
  drl_params_file:=/home/zjq/turtlebot3_ws/src/turtlebot3_pro/turtlebot3_pro_drl_exploration/config/drl_explorer.yaml
```

然后把 `drl_explorer.yaml` 中 `planner_mode` 改为 `utility`。

## 4.1 在新包内训练（已迁移）

```bash
cd ~/turtlebot3_ws/src/turtlebot3_pro/turtlebot3_pro_drl_exploration/training

python3 -m pip install -U pip
python3 -m pip install torch scikit-image matplotlib ray tensorboard

python3 driver.py
```

训练输出默认在：

```text
training/model/<FOLDER_NAME>/checkpoint.pth
```

其中 `FOLDER_NAME` 见 `training/parameter.py`。

## 5) 你最关心的参数建议（TB3 Pro）

已默认做了这些适配：
- 雷达有效范围：按改装车 RPLIDAR A2M12 的 `12.0m` 配置
- 占据栅格阈值：`free_threshold=20`, `occupied_threshold=65`
- 局部图节点间距：`NODE_RESOLUTION=1.0m`
- Nav2 代价地图探测距离：`raytrace_max_range=12.0`, `obstacle_max_range=8.0`
- 机器人半径：`robot_radius=0.12`

建议优先调三组参数：
- 平滑与效率：`lookahead_horizon / heading_weight / distance_weight`
- 探索激进度：`utility_weight / revisit_penalty`
- 地图到图节点尺度：`paper_core/parameter.py` 里的 `CELL_SIZE` 与 Cartographer 分辨率一致
