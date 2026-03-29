# turtlebot3_pro

这是一个聚合仓库，包含你当前 TurtleBot3 Pro 相关的 6 个 ROS 2 包：

- `turtlebot3_pro_bringup`：本体描述/TF 启动，含 `Twist -> TwistStamped` 桥接。
- `turtlebot3_pro_deploybot`：部署相关启动与脚本。
- `turtlebot3_pro_description`：URDF/xacro 机器人模型描述。
- `turtlebot3_pro_gazebo`：Gazebo 仿真模型与仿真 launch。
- `turtlebot3_pro_nav2map`：Nav2 地图/导航相关桥接与启动。
- `turtlebot3_pro_rtabslam`：RTAB-Map SLAM + Nav2 集成启动。

## 目录结构

```text
turtlebot3_pro/
├── turtlebot3_pro_bringup
├── turtlebot3_pro_deploybot
├── turtlebot3_pro_description
├── turtlebot3_pro_gazebo
├── turtlebot3_pro_nav2map
└── turtlebot3_pro_rtabslam
```

## 编译（工作空间根目录执行）

```bash
cd ~/turtlebot3_ws
colcon build --packages-select \
  turtlebot3_pro_bringup \
  turtlebot3_pro_deploybot \
  turtlebot3_pro_description \
  turtlebot3_pro_gazebo \
  turtlebot3_pro_nav2map \
  turtlebot3_pro_rtabslam
source install/setup.bash
```

## 常用启动

- 仿真 + RTAB-Map + Nav2（Nav2 直出 `/cmd_vel`）：

```bash
ros2 launch turtlebot3_pro_rtabslam sim_rtabmap_nav2_cmdvel.launch.py
```

- 仅本体 bringup（含 `/cmd_vel_in` Twist 输入桥接到 `/cmd_vel` TwistStamped）：

```bash
ros2 launch turtlebot3_pro_bringup bringup.launch.py
```

## 说明

- 本仓库是“多包聚合仓库”，`ros2 launch` 时请使用包名（例如 `turtlebot3_pro_rtabslam`），不要用目录名。
- 若你修改了包结构或 launch，建议重新执行一次 `colcon build` 并 `source install/setup.bash`。
