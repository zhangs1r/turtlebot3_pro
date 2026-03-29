#!/usr/bin/env python3

"""TurtleBot3 Burger Pro: Gazebo SLAM + deploy_real_robot policy navigation."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    world_file = LaunchConfiguration("world_file")
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_slam_rviz = LaunchConfiguration("use_slam_rviz")
    x_pose = LaunchConfiguration("x_pose")
    y_pose = LaunchConfiguration("y_pose")
    z_pose = LaunchConfiguration("z_pose")
    yaw = LaunchConfiguration("yaw")
    use_deploy = LaunchConfiguration("use_deploy")
    deploy_delay_sec = LaunchConfiguration("deploy_delay_sec")

    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("turtlebot3_pro_gazebo"),
                "launch",
                "slam.launch.py",
            )
        ),
        launch_arguments={
            "world_file": world_file,
            "use_sim_time": use_sim_time,
            "use_rviz": use_slam_rviz,
            "x_pose": x_pose,
            "y_pose": y_pose,
            "z_pose": z_pose,
            "yaw": yaw,
        }.items(),
    )

    deploy_node = Node(
        package="my_irl_robot",
        executable="deploy_real_robot",
        name="deploy_real_robot",
        output="screen",
    )

    delayed_deploy = TimerAction(
        period=deploy_delay_sec,
        actions=[deploy_node],
        condition=IfCondition(use_deploy),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument(
                "world_file",
                default_value="/root/turtlebot3_ws/src/my_irl_robot/my_irl_robot/worlds/260114/260114.world",
            ),
            DeclareLaunchArgument("use_slam_rviz", default_value="true"),
            DeclareLaunchArgument("x_pose", default_value="0.6"),
            DeclareLaunchArgument("y_pose", default_value="0.6"),
            DeclareLaunchArgument("z_pose", default_value="0.01"),
            DeclareLaunchArgument("yaw", default_value="0.0"),
            DeclareLaunchArgument("use_deploy", default_value="true"),
            DeclareLaunchArgument("deploy_delay_sec", default_value="5.0"),
            slam_launch,
            delayed_deploy,
        ]
    )
