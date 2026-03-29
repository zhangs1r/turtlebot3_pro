#!/usr/bin/env python3

"""把 Burger Pro 的 SDF 模型生成到 Gazebo 世界中。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 初始位姿参数
    x_pose = LaunchConfiguration('x_pose')
    y_pose = LaunchConfiguration('y_pose')
    z_pose = LaunchConfiguration('z_pose')
    yaw = LaunchConfiguration('yaw')

    # 这里使用 SDF（包含 Gazebo 插件），而不是纯 URDF。
    model_sdf = os.path.join(
        get_package_share_directory('turtlebot3_pro_gazebo'),
        'models',
        'turtlebot3_burger_pro',
        'model.sdf',
    )

    return LaunchDescription([
        DeclareLaunchArgument('x_pose', default_value='0.0'),
        DeclareLaunchArgument('y_pose', default_value='0.0'),
        DeclareLaunchArgument('z_pose', default_value='0.01'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        Node(
            package='gazebo_ros',
            executable='spawn_entity.py',
            output='screen',
            arguments=[
                '-entity', 'turtlebot3_pro',
                '-file', model_sdf,
                '-x', x_pose,
                '-y', y_pose,
                '-z', z_pose,
                '-Y', yaw,
                '-timeout', '120',
            ],
        ),
    ])
