# turtlebot3_pro_deploybot

`turtlebot3_pro_deploybot` 复用 `turtlebot3_pro_gazebo/launch/slam.launch.py` 进行建图，
并同时启动 `my_irl_robot` 包中的 `deploy_real_robot` 节点进行策略导航。

## 功能结构

- `launch/deploybot.launch.py`
  - 启动 `turtlebot3_pro_gazebo/slam.launch.py`（Gazebo + Cartographer）
  - 启动 `my_irl_robot/deploy_real_robot`

## 使用方法

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash

unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT ROS_IP ROS_MASTER_URI
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch turtlebot3_pro_deploybot deploybot.launch.py
```

启动后在 RViz 使用 `2D Goal Pose` 发布目标点（`/move_base_simple/goal`），
`deploy_real_robot` 会接收目标并发布 `/cmd_vel`。

## 常用参数

```bash
# 指定世界
ros2 launch turtlebot3_pro_deploybot deploybot.launch.py world_file:=maze_ruins.world

# 只建图，不启动 deploy 节点
ros2 launch turtlebot3_pro_deploybot deploybot.launch.py use_deploy:=false

# 调整 deploy 启动延时
ros2 launch turtlebot3_pro_deploybot deploybot.launch.py deploy_delay_sec:=8.0
```
