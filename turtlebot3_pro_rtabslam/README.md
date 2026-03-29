# TurtleBot3 RTAB-MAP SLAM 🚀

[![ROS 2](https://img.shields.io/badge/ROS-Humble-blue)](https://docs.ros.org/en/humble/index.html)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## 📌 项目简介

本项目（`turtlebot3_pro_rtabslam`）是专为 TurtleBot3 Burger 打造的 RTAB-Map (ROS 2 Humble) SLAM 方案，集成了：

- **RPLIDAR A2M12**：提供高精度的 2D 激光扫描，用于构建占据栅格地图与位姿图优化 🛰️
- **Intel RealSense D435i**：提供 RGB-D 数据，生成彩色 3D 点云地图并实现视觉回环检测 📷

**设计思路**：采用“2D 导航 + 3D 建模”双路策略，确保机器人能够在 2D 栅格地图上稳定导航的同时，通过 3D 点云提供丰富的环境可视化效果。🧭

## 文件与架构说明

本包的目标是把一个“可跑通、可调参、可排错”的真机 SLAM+导航栈拆成几个清晰模块：

- `launch/turtlebot3_pro_rtabslam.launch.py`：顶层入口，只负责编排与开关（是否启动传感器、RViz、rtabmap_viz、建图/定位模式）。
- `launch/bringup.launch.py`：底盘与机器人模型（OpenCR + robot_state_publisher），并提供速度指令桥接节点。
- `launch/sensors.launch.py`：硬件传感器驱动与外参 TF（RPLIDAR/RealSense + 静态 TF）。
- `launch/rtabmap.launch.py`：RTAB-Map 节点（建图/定位参数、话题 remap、QoS 与坐标系约定）。
- `launch/navigation.launch.py`：Nav2 bringup 变体（核心改动是把速度输出导向 `/cmd_vel_twist`）。
- `launch/sim_rtabmap_nav2_cmdvel.launch.py`：仿真专用入口（Gazebo + RTAB-Map + Nav2，Nav2 直接输出 `/cmd_vel`）。
- `config/nav2_params.yaml`：Nav2 参数，关键点是全局静态层订阅 `/rtabmap/map`。
- `config/turtlebot3_pro_rtabslam.rviz`：RViz 视图，固定 frame 为 `map`，并预置 `/scan`、`/rtabmap/map`、相机图像等显示。
- `scripts/twist_to_twist_stamped.py`：Twist -> TwistStamped 桥接（底盘只接受带 stamp 的速度指令时使用）。
- `scripts/goal_pose_to_nav2_action.py`：把 RViz 的 `/goal_pose` 转成 Nav2 的 NavigateToPose action。

## 约定（建议在排错时优先检查）

- 坐标系链路：`map -> odom -> base_footprint` 必须连通（RTAB-Map 负责发布 `map -> odom`）。
- 激光：`/scan`（frame 通常为 `base_scan`，且需要 TF：`base_footprint -> base_scan`）。
- 相机：`/camera/color/image_raw`、`/camera/aligned_depth_to_color/image_raw`（RTAB-Map 在 launch 中做 remap）。
- 地图：`/rtabmap/map`（Nav2 订阅它作为静态地图层，不是 `/map`）。
- 控制链路：Nav2 输出 `/cmd_vel_twist`（Twist）→ 桥接节点输出 `/cmd_vel`（底盘入口）。

## 🚀 硬件配置

- **机器人底盘**: TurtleBot3 Burger (OpenCR)
- **激光雷达**: RPLIDAR A2M12 (串口: `/dev/ttyUSB0`, 波特率: 256000)
- **深度相机**: Intel RealSense D435i (USB 3.0)

## 🛠️ 安装与编译

1. **安装依赖**
   ```bash
   sudo apt install ros-humble-rtabmap-ros ros-humble-realsense2-camera ros-humble-rplidar-ros \
                    ros-humble-nav2-map-server ros-humble-nav2-amcl ros-humble-nav2-lifecycle-manager
   ```
2. **编译工作空间**
   ```bash
   cd ~/turtlebot3_ws
   colcon build --packages-select turtlebot3_pro_rtabslam
   source install/setup.bash
   ```

## 🏁 启动步骤

### 0. Gazebo 仿真一体化启动（推荐）

如果你在仿真中联调 RTAB-Map + Nav2，建议使用下面这个入口：

#### **仿真专用（Nav2 直接输出 `/cmd_vel`，推荐）**

```bash
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_pro_rtabslam sim_rtabmap_nav2_cmdvel.launch.py
```

该模式直接对接 `turtlebot3_pro_gazebo` 的 diff_drive 插件（订阅 `/cmd_vel`），避免 `/cmd_vel_twist` 中间链路带来的话题不一致问题。

可选参数示例：

```bash
ros2 launch turtlebot3_pro_rtabslam sim_rtabmap_nav2_cmdvel.launch.py world_file:=warehouse_grid.world localization:=false
```

### 1. 启动 SLAM 建图或定位导航（终端 1）

此命令会同时启动：

- 机器人底盘驱动 (OpenCR)
- RPLIDAR A2M12 驱动
- RealSense D435i 驱动
- RTAB-MAP 建图/定位算法
- Nav2 导航栈 (Planner, Controller, Recoveries)
- RViz2 可视化界面 (已配置 Nav2 插件)
- 速度指令转换器 (Twist -> TwistStamped)

#### **场景 A：建图模式 (Mapping)**

每次启动都会清空旧地图，重新开始建图。Nav2 会基于实时构建的地图进行路径规划。

```bash
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_pro_rtabslam turtlebot3_pro_rtabslam.launch.py localization:=false
```

- **操作**：使用键盘遥控机器人移动，直到地图构建完整。
- **保存数据库**：直接 Ctrl+C 终止程序，RTAB-Map 会自动保存地图数据库到 `~/.ros/rtabmap.db`。
- **保存 2D 静态地图**：如果您想导出 2D 栅格地图供 AMCL 定位使用，请在建图运行期间执行：
  ```bash
  ros2 run nav2_map_server map_saver_cli -f ~/turtlebot3_ws/src/turtlebot3_pro_rtabslam/maps/map --ros-args -p map_subscribe_transient_local:=true -r /map:=/rtabmap/map
  ```

#### **场景 B：定位导航模式 (Localization)**

加载静态地图并使用 **AMCL** 进行定位导航。此模式下不会修改已有地图，适合在已知环境中进行精确移动。

```bash
export TURTLEBOT3_MODEL=burger
# 默认使用项目 maps/ 目录下的地图
ros2 launch turtlebot3_pro_rtabslam turtlebot3_pro_rtabslam.launch.py localization:=true
# 或者手动指定地图路径
ros2 launch turtlebot3_pro_rtabslam turtlebot3_pro_rtabslam.launch.py localization:=true map:=/your/path/to/map.yaml
```

- **操作**：
  1. 启动后，在 RViz 中观察机器人位置。如果位置不准，点击 RViz 顶部的 **"2D Pose Estimate"** 在地图上标出机器人的初始位姿。
  2. 待定位稳定后，使用 RViz 的 **“2D Nav Goal / Set Goal”** 工具设置目标点。
  3. 本项目会将 RViz 发布的 `/goal_pose` 自动转发为 Nav2 的 `NavigateToPose` Action，请求机器人规划并导航到目标点。

### 2. 启动键盘控制（终端 2）

由于我们已经集成了速度指令转换器，您可以直接使用标准的键盘控制节点，但需要进行话题重映射，将其输出指向转换器的输入端口 `/cmd_vel_twist`：

```bash
export TURTLEBOT3_MODEL=burger
ros2 run turtlebot3_teleop teleop_keyboard --ros-args -r /cmd_vel:=/cmd_vel_twist
```

现在，您可以使用键盘控制机器人移动，并在 RViz 中实时查看建图效果！

## 🧩 主要话题（快速自检）

- 2D 激光：`/scan`
- 里程计：`/odom`
- 2D 占据栅格：`/rtabmap/map`（注意：不是 `/map`）
- 3D 彩色点云地图：`/rtabmap/cloud_map`

## 常见冲突：TF 重复发布

如果 RViz 的 TF 显示中出现跳变或 “Multiple parents” 等症状，优先检查是否重复发布了同一条静态 TF：

- `launch/sensors.launch.py` 会发布 `base_footprint -> base_scan`（为了在“未运行完整 URDF/bringup”时兜底）。
- 但 `turtlebot3_state_publisher` 在正常情况下也可能发布同名 TF。

当你确认 URDF 已经提供该 TF 时，建议禁用 sensors.launch.py 中的 `base_to_scan_tf` 节点，避免冲突。

## 💡 遇到的困难与解决方案 (经验总结)

### 1. 机器人无法移动

- **现象**: 键盘控制节点运行正常，但机器人纹丝不动。
- **原因**: TurtleBot3 Burger 的底盘固件开启了 `enable_stamped_cmd_vel`，只接受带有时间戳的 `geometry_msgs/TwistStamped` 消息，而键盘节点发送的是普通的 `Twist` 消息。
- **解决**: 编写了一个转换节点 `scripts/twist_to_twist_stamped.py`，将 `Twist` 转换为 `TwistStamped` 并转发给底盘。

### 2. RViz 报错 "Frame \[map] does not exist"

- **现象**: 激光雷达数据正常，但无法建立地图，TF 树断裂。
- **原因**: RTAB-MAP 没有接收到有效的传感器数据，导致无法初始化和发布 `map` -> `odom` 的 TF 变换。具体原因是 RealSense 话题名称默认为 `/camera/camera/...`，而 RTAB-MAP 默认订阅 `/camera/...`。
- **解决**: 在 `rtabmap.launch.py` 中修正了所有相机话题的订阅路径，使其与 RealSense 驱动的输出一致。

### 3. RealSense 图像不显示或卡顿

- **现象**: `/camera/camera/color/image_raw` 话题频率为 0 或极低。
- **原因**: 树莓派/上位机 USB 带宽不足，无法承载默认的 1280x720 @ 30fps 数据流。
- **解决**: 在 `sensors.launch.py` 中将 RGB 和深度流的分辨率降低至 **640x480**，帧率降低至 **15fps**。

### 4. `/map` 没有发布者（Publisher count: 0）

- **现象**: `ros2 topic info /map` 显示 Publisher 为 0。
- **原因**: 本项目将 RTAB-Map 节点放在 `rtabmap` 命名空间中，地图默认发布到 `/rtabmap/map`。
- **解决**: 将 RViz 的 Map 订阅改为 `/rtabmap/map` 与 `/rtabmap/map_updates`，或直接订阅 `/rtabmap/map` 查看。

### 5. 建图效果漂移

- **解决**: 在 `rtabmap.launch.py` 中增加了以下参数优化：
  - `Reg/Strategy=2`：使用视觉+激光融合策略（更稳）
  - `Reg/Force3DoF=true`：强制平面运动约束
  - `Grid/RangeMax=10.0`：限制建图距离，减少远处噪声

### 6. 3D 点云地图 `/rtabmap/cloud_map` 没有输出

- **现象**: RViz/rtabmap\_viz 看不到完整 3D 点云，或 `ros2 topic info /rtabmap/cloud_map` Publisher 为 0。
- **原因**: 3D 全局点云需要由 `rtabmap_util/map_assembler` 订阅 `mapData` 进行组装发布。
- **解决**:
  1. 确认已启动 `map_assembler`（本项目已默认启动）
  2. 检查 `ros2 topic info /rtabmap/mapData` 与 `/rtabmap/cloud_map`
  3. 若日志目录只读导致节点异常退出，可临时设置：`export ROS_LOG_DIR=/tmp/roslog`

### 7. Nav2 导航故障排查指南

- **问题 A: Nav2 报错 "Can't update static costmap layer, no map received"**
  - **原因**: 静态层代价地图（Static Layer）与 RTAB-Map 发布的地图 QoS（Quality of Service）不匹配，或者未正确指向动态地图话题。
  - **解决**: 在 `config/nav2_params.yaml` 中，将 `static_layer` 的 `map_subscribe_transient_local` 设为 `True`，并明确指定 `map_topic: /rtabmap/map` 且开启 `subscribe_to_updates: True`。

- **问题 B: Nav2 频繁警告 "Sensor origin is out of map bounds" 且拒绝规划**
  - **原因 1**: 机器人实际坐标超出了当前 RTAB-Map 构建的地图边界（特别是刚启动时坐标为负数）。由于 `global_costmap` 默认是固定窗口且不追踪未知区域，一旦出界就会导致规划失败。
  - **解决**: 在 `config/nav2_params.yaml` 的 `global_costmap` 中：
    1. 增加地图预设范围（如 `width: 15`, `height: 15`），并将原点偏移至负数（如 `origin_x: -7.5`, `origin_y: -7.5`），使其能包裹住整个初始建图区域。
    2. 开启 `track_unknown_space: True`，允许在未知区域内进行探索式规划。
  - **原因 2**: Launch 文件未加载自定义的 Nav2 参数文件。
  - **解决**: 检查 `launch/navigation.launch.py`，确保 `params_file` 参数指向本包内的 `config/nav2_params.yaml`，而不是默认的 `nav2_bringup` 参数。

- **问题 C: RViz2 中的 "2D Pose Estimate" 工具点击没反应**
  - **原因**: RViz 默认将初始位姿发送至 `/initialpose` 话题，但在本工程中，RTAB-Map 订阅的是 `/rtabmap/initialpose`。
  - **解决**: 在 RViz2 左侧的 "Tool Properties" 面板中，将 "2D Pose Estimate" 的 "Topic" 属性修改为 `/rtabmap/initialpose`。

- **问题 D: 点了 Goal 但机器人不动**
  - **原因 1**: 目标点在未知区域（灰色）或障碍物内（黑色）。请确保点在白色自由区域。
  - **原因 2**: TF 树未连通（`map` -> `odom` 缺失）。
    - *自检*: `ros2 run tf2_ros tf2_echo map odom`。如果断开，请遥控机器人转一圈以触发定位。
  - **原因 3**: 速度指令未转发。
    - *自检*: `ros2 topic hz /cmd_vel_twist`。如果没数据，说明 Nav2 规划失败（看日志）；如果有数据但底盘不动，检查转换节点 `twist_to_twist_stamped`。
