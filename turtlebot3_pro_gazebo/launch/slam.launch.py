#!/usr/bin/env python3

"""SLAM 总入口：在仿真之上叠加 Cartographer 建图。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    pkg_share = get_package_share_directory('turtlebot3_pro_gazebo')

    # 这些参数会同时传给仿真层和建图层。
    use_sim_time = LaunchConfiguration('use_sim_time')
    world_file = LaunchConfiguration('world_file')
    x_pose = LaunchConfiguration('x_pose')
    y_pose = LaunchConfiguration('y_pose')
    z_pose = LaunchConfiguration('z_pose')
    yaw = LaunchConfiguration('yaw')
    use_rviz = LaunchConfiguration('use_rviz')

    # 先起仿真环境（Gazebo + robot + 传感器）
    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'sim_all.launch.py')
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'world_file': world_file,
            'x_pose': x_pose,
            'y_pose': y_pose,
            'z_pose': z_pose,
            'yaw': yaw,
        }.items(),
    )

    # 再叠加 Cartographer
    # 依赖话题：/scan、/tf、/odom、/clock（sim time）
    cartographer_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('turtlebot3_cartographer'),
                'launch',
                'cartographer.launch.py',
            )
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'use_rviz': use_rviz,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('use_rviz', default_value='true'),
        DeclareLaunchArgument(
            'world_file',
            default_value='warehouse_grid.world',
            description='World file under turtlebot3_pro_gazebo/worlds',
        ),
        DeclareLaunchArgument('x_pose', default_value='0.0'),
        DeclareLaunchArgument('y_pose', default_value='0.0'),
        DeclareLaunchArgument('z_pose', default_value='0.01'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        sim_launch,
        cartographer_launch,
    ])
