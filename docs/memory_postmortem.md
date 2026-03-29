# TurtleBot3 Pro 仿真内存异常复盘（WSL2 + ROS2 + Gazebo）

## 1) 现象

- 运行：
  - `ros2 launch turtlebot3_pro_rtabslam sim_rtabmap_nav2_cmdvel.launch.py`
- Windows 任务管理器中 **非分页缓冲池（Non-paged pool）持续增长**，可达数 GB。
- 即使 `kill` ROS/Gazebo 进程后，非分页池也不立即回落。
- 同时出现导航异常：
  - RTAB-Map：`Did not receive data since 5 seconds`
  - Nav2：`Can't update static costmap layer, no map received`
  - `/cmd_vel` 无输出。

## 2) 根因分析

### A. 功能链路问题（导航）

- 仿真入口早期未包含 `/goal_pose -> navigate_to_pose` 桥接，RViz 点目标未进入 Nav2 action。
- RTAB-Map remap 与仿真话题不一致（期望 `/camera/color/...`，实际是 `/camera/image_raw`、`/camera/depth/image_raw`）。
- `nav2_params.yaml` 的 static layer QoS 设置不匹配 RTAB-Map，导致地图接收异常。

### B. 系统层问题（非分页池）

- 更接近 Windows 内核/驱动侧内存增长，而非普通用户态进程泄漏：
  - 进程退出后 nonpaged pool 仍高。
- 触发因素：
  - WSL2 + DDS 高频通信
  - Gazebo 彩色+深度相机高频发布
  - 点云话题进一步放大数据面压力

## 3) 修复项

1. 在仿真入口补齐 goal 桥接节点（`/goal_pose -> navigate_to_pose`）。
2. 修正 RTAB-Map 输入 remap 到仿真实际话题：
   - `/camera/image_raw`
   - `/camera/camera_info`
   - `/camera/depth/image_raw`
3. RTAB-Map 同步队列降载：
   - `topic_queue_size: 10`（保持）
   - `sync_queue_size: 50`（由 500 下调）
4. Nav2 static layer QoS 调整：
   - `map_subscribe_transient_local: False`
5. Gazebo 相机降载（关键）：
   - 相机频率 `30 -> 10`
   - 关闭点云发布（移除 `pointCloudTopicName`）

## 4) 结果

- 仿真建图、导航恢复正常。
- 非分页池异常增长显著缓解，系统可稳定运行。

## 5) 后续建议

- 启动前建议环境变量：

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_LOCALHOST_ONLY=1
export FASTDDS_BUILTIN_TRANSPORTS=SHM
```

- 仿真调试先从低负载配置起步（低频、无点云），稳定后逐步加功能。
- 观察到 nonpaged pool 上涨且进程退出不回落时，优先从内核驱动/网络栈方向排查。
