#!/usr/bin/env python3

"""可选传感器辅助启动。

当前只包含一个“可选的雷达静态TF发布器”：
- 当 URDF / SDF 已经提供 base_footprint -> base_scan 时，应保持关闭。
- 仅在 TF 缺失时手动开启 publish_lidar_tf:=true。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    publish_lidar_tf = LaunchConfiguration('publish_lidar_tf')

    # 用静态 TF 补 base_footprint -> base_scan，避免 scan 数据有但 TF 树断开。
    lidar_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_scan_tf',
        condition=IfCondition(publish_lidar_tf),
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            '-0.032',
            '0.0',
            '0.172',
            '0.0',
            '0.0',
            '0.0',
            'base_footprint',
            'base_scan',
        ],
        output='screen',
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument(
            'publish_lidar_tf',
            default_value='false',
            description='Publish base_footprint->base_scan only when your simulation model does not include this TF',
        ),
        lidar_tf,
    ])
