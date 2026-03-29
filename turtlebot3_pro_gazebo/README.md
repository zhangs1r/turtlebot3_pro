# turtlebot3_pro_gazebo

`turtlebot3_pro_gazebo` 负责 Burger Pro 的纯仿真：Gazebo 世界、SDF 模型、传感器与运动插件、SLAM 启动。

## 目录说明
- `launch/sim_all.launch.py`：Gazebo + robot_state_publisher + spawn。
- `launch/slam.launch.py`：在 `sim_all` 基础上叠加 Cartographer。
- `models/turtlebot3_burger_pro/model.sdf`：仿真核心（diff_drive/ray/imu/camera 插件）。
- `worlds/*.world`：强化学习探索场景。

## 启动方式

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash
ros2 launch turtlebot3_pro_gazebo sim_all.launch.py
```

SLAM：

```bash
ros2 launch turtlebot3_pro_gazebo slam.launch.py
```

## 排障经验（本项目关键）

### 1) `/spawn_entity` 不可用的根因
历史故障中，最关键根因不是 `model.sdf` 语法，而是 ROS2 发现机制环境变量冲突（见下方 `.bashrc` 条目）。

### 2) `.bashrc` 高风险变量（仿真时建议禁用）
以下变量会导致本机节点和查询终端不在同一 ROS 图：
- `ROS_DISCOVERY_SERVER=...`
- `ROS_SUPER_CLIENT=TRUE`

仿真推荐先清理：

```bash
unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT ROS_IP ROS_MASTER_URI
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

### 3) “误导性”日志（通常非致命）
- `Missing model.config for ... turtlebot3_autorace_2020`
- `Unable to connect to model database ...`
- `fuel.ignitionrobotics.org SSL_connect ...`

这些通常不影响本地仿真主流程。

### 4) 成功判据
- 日志出现：`SpawnEntity: Successfully spawned entity [turtlebot3_pro]`
- 插件日志出现：
  - `Subscribed to [/cmd_vel]`
  - `Advertise odometry on [/odom]`

### 5) 空旷区“迷失”建议
- 在 `model.sdf` 提高雷达频率与量程（如 10~15Hz，max_range 增大）。
- 调低 Cartographer 回环匹配分数阈值。
- 开启 IMU 约束（`use_imu_data=true`）。
- world 中增加可观测锚点（柱子/障碍块）。
