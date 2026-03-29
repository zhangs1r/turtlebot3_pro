#!/usr/bin/env python3

"""
TurtleBot3 真机基础 bringup（不包含传感器）。

该启动文件用于启动“机器人底座必需组件”，并刻意把传感器驱动拆分到 sensors.launch.py：
- turtlebot3_state_publisher：加载 URDF 并发布 TF（机器人关节与固定坐标关系）。
- turtlebot3_node（turtlebot3_ros）：OpenCR 通信与底盘驱动（里程计、控制等）。
- twist_to_twist_stamped.py：把 Twist 转为 TwistStamped 的兼容桥（便于与 Nav2 的控制链路对接）。

为什么需要 TwistStamped 桥：
- Nav2 的部分组件（例如速度平滑器）在某些配置下更偏好 TwistStamped（带时间戳）。
- 许多 teleop/工具仍旧只发布 Twist；桥接后可统一底盘入口话题保持 /cmd_vel。

约定：
- /cmd_vel_twist：系统中“上游控制”产生的 Twist（来源可能是 Nav2、teleop 或其他控制器）。
- /cmd_vel：最终送入底盘驱动的 Twist（turtlebot3_node 订阅）。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import ThisLaunchFileDir
from launch_ros.actions import Node

def generate_launch_description():
    """
    生成 TurtleBot3 Burger 的自定义启动文件。
    
    这个启动文件基于官方的 robot.launch.py，但移除了激光雷达的启动部分，
    因为激光雷达已经由 sensors.launch.py 独立管理。
    
    主要功能：
    1. 启动 turtlebot3_state_publisher (加载 URDF 模型)
    2. 启动 turtlebot3_node (OpenCR 驱动，处理里程计和电机控制)
    """

    # 获取 TURTLEBOT3_MODEL 环境变量，默认为 burger
    TURTLEBOT3_MODEL = os.environ.get('TURTLEBOT3_MODEL', 'burger')
    
    # OpenCR 的串口设备节点（不同机器可能是 /dev/ttyACM0 或其他）。
    usb_port = LaunchConfiguration('usb_port', default='/dev/ttyACM0')
    
    # 定义参数文件路径
    # 该参数文件通常来自 turtlebot3_bringup/param/<model>.yaml，包含 OpenCR、轮子参数、里程计等。
    tb3_param_dir = LaunchConfiguration(
        'tb3_param_dir',
        default=os.path.join(
            get_package_share_directory('turtlebot3_bringup'),
            'param',
            TURTLEBOT3_MODEL + '.yaml'))

    use_sim_time = LaunchConfiguration('use_sim_time', default='false')
    namespace = LaunchConfiguration('namespace', default='')

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value=use_sim_time,
            description='如果为 true，则使用仿真 (Gazebo) 时钟'),
            
        DeclareLaunchArgument(
            'namespace',
            default_value=namespace,
            description='节点命名空间'),

        DeclareLaunchArgument(
            'usb_port',
            default_value=usb_port,
            description='连接 OpenCR 的 USB 端口'),

        DeclareLaunchArgument(
            'tb3_param_dir',
            default_value=tb3_param_dir,
            description='要加载的 turtlebot3 参数文件的完整路径'),

        # 包含 turtlebot3_state_publisher.launch.py
        # 这会发布 robot_description 和 TF 变换
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory('turtlebot3_bringup'), 'launch', 'turtlebot3_state_publisher.launch.py')
            ),
            launch_arguments={'use_sim_time': use_sim_time, 'namespace': namespace}.items(),
        ),

        # 启动 turtlebot3_node (OpenCR 驱动)
        Node(
            package='turtlebot3_node',
            executable='turtlebot3_ros',
            parameters=[tb3_param_dir, {'namespace': namespace}],
            arguments=['-i', usb_port],
            # /cmd_vel 是底盘控制入口（geometry_msgs/Twist）。这里的 remapping 保持原样，显式强调接口。
            remappings=[('/cmd_vel', '/cmd_vel')],
            output='screen'),
            
        # 启动 Twist 转 TwistStamped 节点 (兼容旧版 teleop)
        Node(
            package='turtlebot3_pro_rtabslam',
            executable='twist_to_twist_stamped.py',
            name='twist_converter',
            remappings=[
                # 上游控制（例如 Nav2 或 teleop）发布 Twist 到 /cmd_vel_twist。
                ('/cmd_vel_in', '/cmd_vel_twist'),
                # 经过桥接后输出到 /cmd_vel，供 turtlebot3_node 消费。
                ('/cmd_vel_out', '/cmd_vel')
            ],
            output='screen'
        ),
    ])
