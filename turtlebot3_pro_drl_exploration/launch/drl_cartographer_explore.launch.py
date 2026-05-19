#!/usr/bin/env python3

"""TurtleBot3 Pro: sim_all + Cartographer + Nav2 + DRL exploration."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    world_file = LaunchConfiguration('world_file')
    x_pose = LaunchConfiguration('x_pose')
    y_pose = LaunchConfiguration('y_pose')
    z_pose = LaunchConfiguration('z_pose')
    yaw = LaunchConfiguration('yaw')
    gui = LaunchConfiguration('gui')

    autostart = LaunchConfiguration('autostart')
    use_nav2_rviz = LaunchConfiguration('use_nav2_rviz')
    use_cartographer_rviz = LaunchConfiguration('use_cartographer_rviz')
    cartographer_config_dir = LaunchConfiguration('cartographer_config_dir')
    configuration_basename = LaunchConfiguration('configuration_basename')
    nav2_params_file = LaunchConfiguration('nav2_params_file')
    drl_params_file = LaunchConfiguration('drl_params_file')
    checkpoint_path = LaunchConfiguration('checkpoint_path')

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('turtlebot3_pro_gazebo'),
                'launch',
                'sim_all.launch.py',
            )
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'world_file': world_file,
            'x_pose': x_pose,
            'y_pose': y_pose,
            'z_pose': z_pose,
            'yaw': yaw,
            'gui': gui,
        }.items(),
    )

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
            'use_rviz': use_cartographer_rviz,
            'cartographer_config_dir': cartographer_config_dir,
            'configuration_basename': configuration_basename,
        }.items(),
    )

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
            'params_file': nav2_params_file,
            'use_composition': 'False',
            'use_respawn': 'True',
            'log_level': 'info',
        }.items(),
    )

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

    drl_node = Node(
        package='turtlebot3_pro_drl_exploration',
        executable='drl_explorer',
        output='screen',
        parameters=[
            drl_params_file,
            {
                'use_sim_time': use_sim_time,
                'checkpoint_path': checkpoint_path,
            },
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('world_file', default_value='warehouse_grid.world'),
        DeclareLaunchArgument('x_pose', default_value='0.0'),
        DeclareLaunchArgument('y_pose', default_value='0.0'),
        DeclareLaunchArgument('z_pose', default_value='0.01'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument('use_nav2_rviz', default_value='true'),
        DeclareLaunchArgument('use_cartographer_rviz', default_value='false'),
        DeclareLaunchArgument(
            'cartographer_config_dir',
            default_value=os.path.join(
                get_package_share_directory('turtlebot3_pro_gazebo'),
                'config',
            ),
        ),
        DeclareLaunchArgument(
            'configuration_basename',
            default_value='turtlebot3_a2m12_2d.lua',
        ),
        DeclareLaunchArgument(
            'nav2_params_file',
            default_value=os.path.join(
                get_package_share_directory('turtlebot3_pro_drl_exploration'),
                'config',
                'nav2_params_cartographer_drl.yaml',
            ),
        ),
        DeclareLaunchArgument(
            'drl_params_file',
            default_value=os.path.join(
                get_package_share_directory('turtlebot3_pro_drl_exploration'),
                'config',
                'drl_explorer.yaml',
            ),
        ),
        DeclareLaunchArgument(
            'checkpoint_path',
            default_value='',
            description='Path to trained policy checkpoint (.pth).',
        ),
        sim_launch,
        cartographer_launch,
        TimerAction(period=4.0, actions=[nav2_navigation]),
        TimerAction(period=6.0, actions=[drl_node]),
        nav2_rviz,
    ])
