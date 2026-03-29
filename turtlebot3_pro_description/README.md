# turtlebot3_pro_description

`turtlebot3_pro_description` 负责 Burger Pro 的机器人本体描述（URDF/Xacro）。

## 目录说明
- `urdf/turtlebot3_burger_pro.urdf.xacro`：主源文件，建议优先修改这里。
- `urdf/turtlebot3_burger_pro.urdf`：由 xacro 展开生成的静态 URDF。

## 机器人改装点（当前）
- 底盘基于 TurtleBot3 Burger。
- 雷达坐标系：`base_scan`（用于激光数据 TF）。
- 相机坐标系：`camera_link`（用于 D435i 近似安装位姿）。

## 使用建议
- 改模型参数时先改 `.urdf.xacro`，再生成 `.urdf`：

```bash
source /opt/ros/humble/setup.bash
xacro src/turtlebot3_pro_description/urdf/turtlebot3_burger_pro.urdf.xacro > \
  src/turtlebot3_pro_description/urdf/turtlebot3_burger_pro.urdf
```

## 常见问题
- `tftree` 断裂：先检查 `base_footprint -> base_link -> base_scan/camera_link` 是否完整。
- 不建议直接手改 `.urdf`（会在下次生成时被覆盖）。
