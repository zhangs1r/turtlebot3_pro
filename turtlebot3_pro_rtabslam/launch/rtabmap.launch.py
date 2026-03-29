"""
RTAB-Map 建图/定位启动文件（强制 namespace=rtabmap）。

该文件的职责是把 RTAB-Map 运行所需的“关键约定”固定下来：
- 输入：RGB + Depth + Scan + Odom（分别来自 RealSense、RPLIDAR 与底盘里程计）。
- 坐标系：map / odom / base_footprint。
- 输出：/rtabmap/map（供 Nav2 的全局代价地图使用）以及 /rtabmap/* 调试话题。

模式：
- localization=false：建图（增量内存开启，会持续往数据库写入新节点）。
- localization=true：定位（增量内存关闭，加载历史节点进行匹配重定位）。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    """
    生成 RTAB-MAP SLAM 启动描述文件。
    
    该版本强制使用 'rtabmap' 命名空间以匹配 RVIZ 默认配置话题 (/rtabmap/cloud_map)。
    同时优化了同步参数和坐标系配置。
    """
    
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')
    localization = LaunchConfiguration('localization', default='false')
    database_path = LaunchConfiguration('database_path', default='~/.ros/rtabmap.db')
    qos = LaunchConfiguration('qos', default='2')

    # 共同参数：
    # - subscribe_depth/subscribe_scan：订阅深度图与激光，组成 RGB-D + 2D LiDAR 的融合输入。
    # - frame_id/odom_frame_id/map_frame_id：显式指定三大坐标系，避免依赖默认值导致 TF 断链。
    # - approx_sync/queue_size：近似时间同步与队列大小，对 USB 相机 + 激光 + 里程计异步抖动很重要。
    # - qos_*：传感器数据 QoS（2 通常对应 SensorData，适合高频非关键数据）。
    common_parameters = {
        'use_sim_time': use_sim_time,
        'subscribe_depth': True,
        'subscribe_scan': True,
        'frame_id': 'base_footprint',
        'odom_frame_id': 'odom',
        'map_frame_id': 'map',
        'database_path': database_path,
        'approx_sync': True,
        'queue_size': 500,
        'approx_sync_max_interval': 0.5,
        'Reg/Strategy': '2',
        'Reg/Force3DoF': 'true',
        'Grid/Sensor': '0',
        'Grid/FromDepth': 'false',
        'Grid/RangeMax': '10.0',
        'Rtabmap/PublishMapData': 'true',
        'Rtabmap/DetectionRate': '2.0',
        'RGBD/LinearUpdate': '0.01',
        'RGBD/AngularUpdate': '0.01',
        'qos_image': qos,
        'qos_depth': qos,
        'qos_camera_info': qos,
        'qos_scan': qos,
        'qos_odom': qos,
    }

    # 建图模式：
    # - Mem/IncrementalMemory=true：允许新增节点/回环信息，持续扩展地图。
    # - Mem/InitWMWithAllNodes=false：启动时不把所有历史节点都加载到工作记忆，节省资源。
    mapping_parameters = {
        **common_parameters,
        'Mem/IncrementalMemory': 'true',
        'Mem/InitWMWithAllNodes': 'false',
    }

    # 定位模式：
    # - Mem/IncrementalMemory=false：不再新增节点，只对照已有地图做匹配。
    # - Mem/InitWMWithAllNodes=true：把历史节点加载到工作记忆，加快重定位成功率。
    localization_parameters = {
        **common_parameters,
        'Mem/IncrementalMemory': 'false',
        'Mem/InitWMWithAllNodes': 'true',
    }

    # 话题重映射 (显式使用绝对路径)
    # RTAB-Map 节点的输入接口名是相对话题（rgb/image、depth/image 等），这里把它们连到
    # 本工程中 RealSense/RPLIDAR/里程计的实际话题上，避免依赖任何外部 remap 习惯。
    remappings = [
        ('rgb/image', '/camera/color/image_raw'),
        ('rgb/camera_info', '/camera/color/camera_info'),
        ('depth/image', '/camera/aligned_depth_to_color/image_raw'),
        ('scan', '/scan'),
        ('odom', '/odom'),
    ]
    
    rtabmap_mapping_node = Node(
        package='rtabmap_slam',
        executable='rtabmap',
        name='rtabmap',
        namespace='rtabmap',
        output='screen',
        condition=UnlessCondition(localization),
        parameters=[mapping_parameters],
        remappings=remappings,
        # 每次启动都清空数据库便于快速调参验证；如果你希望持久化地图，请移除该参数。
        arguments=['--delete_db_on_start']
    )

    rtabmap_localization_node = Node(
        package='rtabmap_slam',
        executable='rtabmap',
        name='rtabmap',
        namespace='rtabmap',
        output='screen',
        condition=IfCondition(localization),
        parameters=[localization_parameters],
        remappings=remappings
    )

    map_assembler_node = Node(
        package='rtabmap_util',
        executable='map_assembler',
        name='map_assembler',
        namespace='rtabmap',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('localization', default_value='false'),
        DeclareLaunchArgument('database_path', default_value='~/.ros/rtabmap.db'),
        DeclareLaunchArgument('qos', default_value='2'),
        rtabmap_mapping_node,
        rtabmap_localization_node,
        map_assembler_node
    ])
