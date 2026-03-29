#!/usr/bin/env python3

"""
仿真专用一体化启动（Nav2 直接输出 /cmd_vel）：
- 使用 turtlebot3_pro_gazebo/launch/sim_all.launch.py 拉起 Gazebo 仿真
- 使用 rtabmap.launch.py 进行 RTAB-Map SLAM
- 使用 navigation.launch.py 启动 Nav2，并将速度输出直接映射到 /cmd_vel

适用场景：
- Gazebo 中使用 diff_drive 插件直接订阅 /cmd_vel
- 不需要 /cmd_vel_twist -> /cmd_vel 的中间桥接链路
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    world_file = LaunchConfiguration('world_file')
    x_pose = LaunchConfiguration('x_pose')
    y_pose = LaunchConfiguration('y_pose')
    z_pose = LaunchConfiguration('z_pose')
    yaw = LaunchConfiguration('yaw')

    localization = LaunchConfiguration('localization')
    database_path = LaunchConfiguration('database_path')
    qos = LaunchConfiguration('qos')

    autostart = LaunchConfiguration('autostart')
    params_file = LaunchConfiguration('params_file')

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_gazebo'),
                'launch',
                'sim_all.launch.py',
            ])
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

    rtabmap_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'rtabmap.launch.py',
            ])
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'localization': localization,
            'database_path': database_path,
            'qos': qos,
        }.items(),
    )

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'navigation.launch.py',
            ])
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'autostart': autostart,
            'params_file': params_file,
            'cmd_vel_out_topic': '/cmd_vel',
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('world_file', default_value='warehouse_grid.world'),
        DeclareLaunchArgument('x_pose', default_value='0.0'),
        DeclareLaunchArgument('y_pose', default_value='0.0'),
        DeclareLaunchArgument('z_pose', default_value='0.01'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('localization', default_value='false'),
        DeclareLaunchArgument('database_path', default_value='~/.ros/rtabmap.db'),
        DeclareLaunchArgument('qos', default_value='2'),
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'config',
                'nav2_params.yaml',
            ]),
        ),
        sim_launch,
        rtabmap_launch,
        nav2_launch,
    ])
