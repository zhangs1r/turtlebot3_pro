# turtlebot3_pro_nav2map

`turtlebot3_pro_nav2map` 在 `turtlebot3_pro_gazebo/launch/slam.launch.py` 基础上叠加 Nav2。
支持在 RViz 中使用 `2D Goal Pose` 触发导航。

## 功能结构
- `launch/nav2_map.launch.py`
  - 启动 `turtlebot3_pro_gazebo/slam.launch.py`（仿真 + Cartographer）
  - 启动 `nav2_bringup/navigation_launch.py`
  - 启动 Nav2 RViz
  - 启动 `goal_pose_bridge`
- `turtlebot3_pro_nav2map/goal_pose_bridge.py`
  - 订阅 `/goal_pose`（RViz 2D Goal Pose）
  - 转发到 Nav2 action `/navigate_to_pose`

## 使用方法

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash

# 强烈建议仿真前清理外部发现服务相关变量
unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT ROS_IP ROS_MASTER_URI
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch turtlebot3_pro_nav2map nav2_map.launch.py
```

然后在 RViz：
1. 点击 `2D Goal Pose`
2. 指定目标点与朝向
3. 观察终端日志 `Goal accepted by Nav2`

## 常见问题
- 能看到车但 `ros2 topic list` 只有 `/parameter_events`、`/rosout`：
  说明当前终端环境与启动终端不一致，优先检查 `ROS_DISCOVERY_SERVER` 等变量。
- 地图漂移/空旷区迷失：参考 `turtlebot3_pro_gazebo/README.md` 的 SLAM 调参建议。
