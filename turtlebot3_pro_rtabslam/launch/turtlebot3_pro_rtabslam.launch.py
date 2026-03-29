"""
TurtleBot3 + RTAB-Map + Nav2 的顶层启动入口。

该启动文件的职责是“编排”，它不会直接承载复杂参数，而是把系统拆成几个稳定的子模块：
- 底盘与机器人模型（bringup.launch.py）：OpenCR 驱动 + robot_state_publisher。
- 传感器（sensors.launch.py，可选）：RPLIDAR 与 RealSense 以及必要的静态 TF。
- 建图/定位（rtabmap.launch.py）：RTAB-Map 节点（namespace 固定为 rtabmap）。
- 导航（navigation.launch.py）：Nav2 全家桶（规划、控制、行为树等）。
- 可视化（RViz/rtabmap_viz，可选）：用于调试 TF、地图与传感器数据。

约定（本包内多个文件共享的假设）：
- 坐标系：map / odom / base_footprint（RTAB-Map 与 rtabmap_viz 统一用 base_footprint）。
- 传感器话题：激光使用 /scan；相机使用 /camera/...（来自 realsense2_camera 默认命名）。
- 控制链路：Nav2 最终输出到 /cmd_vel_twist（Twist），再由本包桥接到底盘使用的 /cmd_vel。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    """
    生成 TurtleBot3 RTAB-MAP SLAM 总启动描述文件。
    
    该函数作为顶层启动文件，负责按需启动底盘/模型、传感器、RTAB-Map 与 Nav2。
    设计目标是把“硬件耦合”集中在 sensors.launch.py，把“算法参数”集中在 rtabmap.launch.py
    与 config/nav2_params.yaml，从而让顶层入口只做开关与编排。

    关键开关：
    - use_sensors：是否启动传感器驱动（真机需要；如果传感器已由其他方式启动可关闭）。
    - use_rviz：是否启动 RViz（同时决定是否启动 goal_pose_to_nav2_action 桥接节点）。
    - use_rtabmap_viz：是否启动 rtabmap_viz（RTAB-Map 的 3D 可视化与调参界面）。
    - localization：false=建图；true=定位（使用已有数据库进行重定位）。
    
    Returns:
        LaunchDescription: 包含所有子启动文件的总启动描述。
    """
    
    # 说明：
    # 这里同时用 LaunchConfiguration(..., default=...) 与 DeclareLaunchArgument(default_value=...)，
    # 是为了在“未显式声明参数时”也能正常运行（LaunchConfiguration 的 default 会兜底）。
    use_sensors = LaunchConfiguration('use_sensors', default='true')
    use_rviz = LaunchConfiguration('use_rviz', default='true')
    use_rtabmap_viz = LaunchConfiguration('use_rtabmap_viz', default='false')
    localization = LaunchConfiguration('localization', default='false')
    map_yaml_file = LaunchConfiguration('map', default=PathJoinSubstitution([
        FindPackageShare('turtlebot3_pro_rtabslam'),
        'maps',
        'map.yaml'
    ]))
    
    declare_use_sensors = DeclareLaunchArgument(
        'use_sensors',
        default_value='true',
        description='是否启动传感器（激光雷达和摄像头）'
    )
    
    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='是否启动 RViz'
    )

    declare_use_rtabmap_viz = DeclareLaunchArgument(
        'use_rtabmap_viz',
        default_value='false',
        description='是否启动 rtabmap_viz (3D 点云可视化界面)'
    )
    
    declare_localization = DeclareLaunchArgument(
        'localization',
        default_value='false',
        description='是否为定位模式 (true=定位, false=建图)'
    )

    declare_map = DeclareLaunchArgument(
        'map',
        default_value=map_yaml_file,
        description='静态地图 YAML 文件的完整路径'
    )
    
    # 底盘与模型：
    # - turtlebot3_state_publisher：发布 robot_description 以及 TF（通常包含 base_footprint 等）。
    # - turtlebot3_node：OpenCR 驱动，发布里程计/关节状态并订阅 /cmd_vel 控制底盘。
    bringup_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'bringup.launch.py'
            ])
        ])
    )
    
    # 传感器（可选）：
    # 真机通常需要启动；但在某些集成场景（例如传感器由其他 launch 管理）可以关闭以避免重复启动。
    sensors_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'sensors.launch.py'
            ])
        ]),
        condition=IfCondition(use_sensors)
    )
    
    # SLAM / 定位：
    # 当 localization=false 时，启动 RTAB-Map 建图。
    # 当 localization=true 时，启动基于 Map Server + AMCL 的定位。
    rtabmap_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'rtabmap.launch.py'
            ])
        ]),
        condition=UnlessCondition(localization),
        launch_arguments={'localization': localization}.items()
    )
    
    localization_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'localization.launch.py'
            ])
        ]),
        condition=IfCondition(localization),
        launch_arguments={
             'use_sim_time': 'false',
             'autostart': 'true',
             'map': map_yaml_file,
         }.items()
    )
    
    # 导航：
    # Nav2 在建图与定位两种模式下都可以工作，只要 global_costmap 的地图源稳定。
    # 本包默认将 Nav2 的静态地图源指向 /rtabmap/map（见 config/nav2_params.yaml）。
    navigation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('turtlebot3_pro_rtabslam'),
                'launch',
                'navigation.launch.py'
            ])
        ]),
        launch_arguments={'use_sim_time': 'false'}.items()
    )

    goal_pose_to_nav2_node = Node(
        package='turtlebot3_pro_rtabslam',
        executable='goal_pose_to_nav2_action.py',
        name='goal_pose_to_nav2_action',
        output='screen',
        condition=IfCondition(use_rviz),
    )
    
    # RViz：
    # RViz 的“2D Nav Goal/GoalPose”通常发布 /goal_pose（PoseStamped）。
    # goal_pose_to_nav2_action.py 把这个话题桥接为 Nav2 的 NavigateToPose action 调用，
    # 因此这里把两者都绑定到 use_rviz 开关：不启 RViz 时通常也不需要该桥接节点。
    rviz_config_dir = PathJoinSubstitution([
        FindPackageShare('turtlebot3_pro_rtabslam'),
        'config',
        'turtlebot3_pro_rtabslam.rviz'
    ])

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config_dir],
        condition=IfCondition(use_rviz),
        output='screen'
    )

    rtabmap_viz_node = Node(
        package='rtabmap_viz',
        executable='rtabmap_viz',
        name='rtabmap_viz',
        namespace='rtabmap',
        output='screen',
        condition=IfCondition(use_rtabmap_viz),
        parameters=[{
            'subscribe_depth': True,
            'subscribe_scan': True,
            'frame_id': 'base_footprint',
            'odom_frame_id': 'odom',
            'map_frame_id': 'map',
        }],
        remappings=[
            ('rgb/image', '/camera/color/image_raw'),
            ('rgb/camera_info', '/camera/color/camera_info'),
            ('depth/image', '/camera/aligned_depth_to_color/image_raw'),
            ('scan', '/scan'),
            ('odom', '/odom'),
        ],
    )

    return LaunchDescription([
        declare_use_sensors,
        declare_use_rviz,
        declare_use_rtabmap_viz,
        declare_localization,
        declare_map,
        bringup_launch,
        sensors_launch,
        rtabmap_launch,
        localization_launch,
        navigation_launch,
        goal_pose_to_nav2_node,
        rtabmap_viz_node,
        rviz_node
    ])
