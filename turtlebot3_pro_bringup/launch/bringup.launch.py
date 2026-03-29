#!/usr/bin/env python3

"""turtlebot3_pro_bringup：偏“机器人本体描述层”的启动。

这个文件通常用于：
- 发布 robot_description（xacro展开后）
- 启动 robot_state_publisher
- 可选附加一些传感器相关静态TF
- 可选启动 Twist -> TwistStamped 桥接（/cmd_vel_in -> /cmd_vel）

在本项目里，Gazebo 插件由 turtlebot3_pro_gazebo 负责，
这个 bringup 更像“TF/描述骨架”层。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    # 使用 xacro 源文件，支持 namespace 参数化。
    urdf_path = os.path.join(
        get_package_share_directory('turtlebot3_pro_description'),
        'urdf',
        'turtlebot3_burger_pro.urdf.xacro',
    )

    use_sim_time = LaunchConfiguration('use_sim_time')
    namespace = LaunchConfiguration('namespace')
    with_sensors = LaunchConfiguration('with_sensors')
    publish_lidar_tf = LaunchConfiguration('publish_lidar_tf')
    enable_cmd_vel_twist_bridge = LaunchConfiguration('enable_cmd_vel_twist_bridge')

    # 运行时调用 xacro 生成 robot_description。
    # namespace 非空时在链接名前加前缀，便于多机器人场景扩展。
    robot_description = Command([
        'xacro ',
        urdf_path,
        ' namespace:=',
        PythonExpression(['"', namespace, '" + "/" if "', namespace, '" != "" else ""']),
    ])

    # 可选传感器补充 launch（例如补静态TF）
    sensors_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('turtlebot3_pro_bringup'), 'launch', 'sensors.launch.py')
        ),
        condition=IfCondition(with_sensors),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'publish_lidar_tf': publish_lidar_tf,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use simulation clock',
        ),
        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Namespace for robot topics',
        ),
        DeclareLaunchArgument(
            'with_sensors',
            default_value='true',
            description='Include sensors.launch.py for sensor TF setup',
        ),
        DeclareLaunchArgument(
            'publish_lidar_tf',
            default_value='false',
            description='Publish base_footprint->base_scan static TF only when URDF does not provide it',
        ),
        DeclareLaunchArgument(
            'enable_cmd_vel_twist_bridge',
            default_value='true',
            description='Enable Twist(/cmd_vel_in) to TwistStamped(/cmd_vel) bridge',
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            output='screen',
            parameters=[
                {'robot_description': robot_description},
                {'use_sim_time': use_sim_time},
            ],
        ),
        # 兼容两种速度输入：
        # 1) 直接给 /cmd_vel（TwistStamped）；
        # 2) 给 /cmd_vel_in（Twist），由该节点转换后发布到 /cmd_vel。
        Node(
            package='turtlebot3_pro_bringup',
            executable='twist_to_twist_stamped.py',
            name='twist_to_twist_stamped',
            output='screen',
            condition=IfCondition(enable_cmd_vel_twist_bridge),
            parameters=[{'use_sim_time': use_sim_time}],
        ),
        sensors_launch,
    ])
