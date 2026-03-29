# turtlebot3_pro_bringup

`turtlebot3_pro_bringup` 用于 TurtleBot3 Pro 的“本体启动层”：  
- 发布 `robot_description`（xacro 展开）  
- 启动 `robot_state_publisher`  
- 按需补充传感器静态 TF  
- 提供 `Twist -> TwistStamped` 速度指令桥接（方便真机控制）

它不负责 Gazebo 物理仿真进程；仿真由 `turtlebot3_pro_gazebo` 管理。

## 功能结构

- `launch/bringup.launch.py`  
  包入口，启动 `robot_state_publisher`，可选包含 `sensors.launch.py`，可选启动速度桥接节点。
- `launch/sensors.launch.py`  
  传感器相关补充（例如必要的静态 TF）。
- `scripts/twist_to_twist_stamped.py`  
  将 `geometry_msgs/Twist` 转为 `geometry_msgs/TwistStamped`。

## 速度控制链路（重点）

当前包支持两种输入方式并存：

- 方式 A：直接发布 `TwistStamped` 到 `/cmd_vel`（直连底盘）
- 方式 B：发布 `Twist` 到 `/cmd_vel_in`，由桥接节点转换后输出到 `/cmd_vel`

也就是：

`/cmd_vel_in (Twist) -> twist_to_twist_stamped.py -> /cmd_vel (TwistStamped)`

如果你的控制器已经输出 `TwistStamped`，可以直接发 `/cmd_vel`；  
如果只输出 `Twist`（如一些 teleop/旧控制器），就发 `/cmd_vel_in`。

## Launch 参数

`bringup.launch.py` 支持以下参数：

- `use_sim_time`（默认：`true`）  
  是否使用仿真时钟。
- `namespace`（默认：空）  
  多机器人场景下的命名空间前缀。
- `with_sensors`（默认：`true`）  
  是否包含 `sensors.launch.py`。
- `publish_lidar_tf`（默认：`false`）  
  仅在 URDF 未提供相关 TF 时，才手动补 `base_footprint -> base_scan`。
- `enable_cmd_vel_twist_bridge`（默认：`true`）  
  是否启动 `Twist -> TwistStamped` 桥接节点。

## 使用方式

### 1) 编译

```bash
cd ~/turtlebot3_ws
colcon build --packages-select turtlebot3_pro_bringup
source install/setup.bash
```

### 2) 启动 bringup

```bash
ros2 launch turtlebot3_pro_bringup bringup.launch.py
```

### 3) 速度指令示例

- 发 `Twist` 到桥接输入：

```bash
ros2 topic pub /cmd_vel_in geometry_msgs/msg/Twist "{linear: {x: 0.1}, angular: {z: 0.0}}" -r 10
```

- 直接发 `TwistStamped` 到底盘入口：

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/TwistStamped "{header: {frame_id: 'base_link'}, twist: {linear: {x: 0.1}, angular: {z: 0.0}}}" -r 10
```

### 4) 仅使用直连 `TwistStamped`（关闭桥接）

```bash
ros2 launch turtlebot3_pro_bringup bringup.launch.py enable_cmd_vel_twist_bridge:=false
```

## 排错建议

- 如果 TF 报重复（尤其 `base_scan` 相关），优先检查 `publish_lidar_tf` 是否误开。
- 如果 `/cmd_vel_in` 有数据但机器人不动，检查：
  - `twist_to_twist_stamped` 节点是否在运行
  - `/cmd_vel` 是否有 `TwistStamped` 输出
- 多机器人场景建议显式设置 `namespace`，避免话题和 TF 混用。
