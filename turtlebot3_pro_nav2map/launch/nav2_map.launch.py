#!/usr/bin/env python3

"""TurtleBot3 Burger Pro: Gazebo + Cartographer + Nav2 (2D Goal Pose)."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    world_file = LaunchConfiguration('world_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_nav2_rviz = LaunchConfiguration('use_nav2_rviz')
    params_file = LaunchConfiguration('params_file')
    autostart = LaunchConfiguration('autostart')

    # 1) 基于你现有的 slam.launch.py：仿真 + cartographer
    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('turtlebot3_pro_gazebo'),
                'launch',
                'slam.launch.py',
            )
        ),
        launch_arguments={
            'world_file': world_file,
            'use_sim_time': use_sim_time,
            # 用 Nav2 RViz，避免同时起两个 RViz
            'use_rviz': 'false',
            'x_pose': '0.0',
            'y_pose': '0.0',
            'z_pose': '0.01',
            'yaw': '0.0',
        }.items(),
    )

    # 2) 启动 Nav2 导航核心（不启动 AMCL/map_server，由 cartographer 提供 map+tf）
    nav2_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('nav2_bringup'),
                'launch',
                'navigation_launch.py',
            )
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'autostart': autostart,
            'params_file': params_file,
            'use_composition': 'False',
            'use_respawn': 'True',
            'log_level': 'info',
        }.items(),
    )

    # 3) 启动 Nav2 RViz（可选）
    nav2_rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('nav2_bringup'),
                'launch',
                'rviz_launch.py',
            )
        ),
        condition=IfCondition(use_nav2_rviz),
        launch_arguments={
            'use_namespace': 'false',
            'rviz_config': os.path.join(
                get_package_share_directory('nav2_bringup'),
                'rviz',
                'nav2_default_view.rviz',
            ),
        }.items(),
    )

    # 4) 2D Goal Pose 桥接：RViz /goal_pose -> Nav2 action
    goal_bridge = Node(
        package='turtlebot3_pro_nav2map',
        executable='goal_pose_bridge',
        output='screen',
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('world_file', default_value='warehouse_grid.world'),
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument('use_nav2_rviz', default_value='true'),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(
                get_package_share_directory('nav2_bringup'),
                'params',
                'nav2_params.yaml',
            ),
            description='Nav2 parameters file',
        ),
        slam_launch,
        nav2_navigation,
        goal_bridge,
        # 简化：默认始终起 Nav2 RViz。如果你不想起，可手动关掉该段。
        nav2_rviz,
    ])
