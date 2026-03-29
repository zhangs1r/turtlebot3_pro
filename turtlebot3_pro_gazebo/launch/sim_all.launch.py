#!/usr/bin/env python3

"""turtlebot3_pro_gazebo 总入口：启动 Gazebo + 发布 TF + 生成 Burger Pro。

设计目标：
1) 纯仿真一条命令拉起。
2) 显式加载 gazebo_ros 插件，确保 /spawn_entity 可用。
3) 在 WSL/离线环境下，模型与插件路径尽可能自洽，减少“能开gazebo但无模型/无服务”的概率。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description():
    # 本包 share 目录，用来拼接 worlds/models/launch 相对路径。
    pkg_share = get_package_share_directory('turtlebot3_pro_gazebo')
    pkg_gazebo_ros = get_package_share_directory('gazebo_ros')

    # -----------------------------
    # 启动参数（支持命令行覆盖）
    # -----------------------------
    use_sim_time = LaunchConfiguration('use_sim_time')
    world_file = LaunchConfiguration('world_file')
    x_pose = LaunchConfiguration('x_pose')
    y_pose = LaunchConfiguration('y_pose')
    z_pose = LaunchConfiguration('z_pose')
    yaw = LaunchConfiguration('yaw')

    # 世界文件路径：<pkg_share>/worlds/<world_file>
    world_path = PathJoinSubstitution([pkg_share, 'worlds', world_file])

    # -----------------------------
    # Gazebo 资源路径拼接
    # -----------------------------
    # 说明：
    # - 只设置模型路径（不覆盖 GAZEBO_PLUGIN_PATH），避免破坏 gazebo_ros 默认插件发现逻辑。
    # - 第1段：你自己的 pro 模型目录（必须）
    # - 第2段：官方 turtlebot3_gazebo 模型目录（含 turtlebot3_common 等依赖）
    # - 第3段：Gazebo 默认模型目录（ground_plane/sun 等）
    # - 最后拼接用户已有环境变量，避免覆盖用户外部配置
    existing_model_path = os.environ.get('GAZEBO_MODEL_PATH', '')

    model_paths = [
        os.path.join(pkg_share, 'models'),
        '/opt/ros/humble/share/turtlebot3_gazebo/models',
        '/usr/share/gazebo-11/models',
    ]
    if existing_model_path:
        model_paths.append(existing_model_path)
    gazebo_model_path = os.pathsep.join(model_paths)

    # -----------------------------
    # Gazebo 进程
    # -----------------------------
    # 改回官方 gazebo_ros 启动链，避免手写路径导致 factory 服务缺失。
    gzserver_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_gazebo_ros, 'launch', 'gzserver.launch.py')
        ),
        launch_arguments={
            'world': world_path,
            'verbose': 'true',
            'init': 'true',
            'factory': 'true',
            'force_system': 'true',
        }.items(),
    )

    # Gazebo 图形客户端
    gzclient_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_gazebo_ros, 'launch', 'gzclient.launch.py')
        )
    )

    # TF 与 robot_description 发布（只管“机器人结构”，不负责物理仿真）
    robot_state_publisher_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'robot_state_publisher.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items(),
    )

    # 调用 /spawn_entity 把 SDF 模型放入 Gazebo 世界
    spawn_robot_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'spawn_turtlebot3_pro.launch.py')
        ),
        launch_arguments={
            'x_pose': x_pose,
            'y_pose': y_pose,
            'z_pose': z_pose,
            'yaw': yaw,
        }.items(),
    )

    return LaunchDescription([
        # 环境变量必须先设置，后启动 Gazebo/Spawn。
        SetEnvironmentVariable('GAZEBO_MODEL_PATH', gazebo_model_path),
        # 兼容官方包中读取 TURTLEBOT3_MODEL 的场景（这里固定 burger）。
        SetEnvironmentVariable('TURTLEBOT3_MODEL', 'burger'),

        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('world_file', default_value='warehouse_grid.world'),
        DeclareLaunchArgument('x_pose', default_value='0.0'),
        DeclareLaunchArgument('y_pose', default_value='0.0'),
        DeclareLaunchArgument('z_pose', default_value='0.01'),
        DeclareLaunchArgument('yaw', default_value='0.0'),

        gzserver_cmd,
        gzclient_cmd,
        robot_state_publisher_cmd,
        # 给 /spawn_entity 服务一个启动窗口，减少并发竞态导致的超时失败。
        TimerAction(period=4.0, actions=[spawn_robot_cmd]),
    ])
