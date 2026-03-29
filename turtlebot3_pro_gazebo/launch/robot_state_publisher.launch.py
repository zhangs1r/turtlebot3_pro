#!/usr/bin/env python3

"""发布机器人静态/动态关节 TF（来自 URDF）。

注意：
- 这个 launch 只负责 TF 结构与 robot_description 参数。
- 真正的物理运动、里程计、雷达、相机由 Gazebo SDF 插件提供。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')

    # 这里读取“已展开的 urdf”而非 xacro，减少运行时依赖，提升稳定性。
    urdf_path = os.path.join(
        get_package_share_directory('turtlebot3_pro_description'),
        'urdf',
        'turtlebot3_burger_pro.urdf',
    )

    with open(urdf_path, 'r', encoding='utf-8') as infp:
        robot_desc = infp.read()

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use simulation clock',
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'robot_description': robot_desc,
            }],
        ),
    ])
