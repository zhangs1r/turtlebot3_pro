"""
真机传感器启动：RPLIDAR A2M12 + RealSense D435i + 必要静态 TF。

该文件的目标是把“硬件强耦合参数”集中在一起，便于迁移与排错：
- RPLIDAR：串口端口/波特率/scan_mode 与 frame_id。
- RealSense：分辨率/帧率/深度对齐/IMU 设置与 TF 发布。
- 静态 TF：把传感器坐标系挂到机器人基座（base_footprint）上，保证 RTAB-Map 可用。

注意事项（常见坑）：
- TF 重复发布：turtlebot3_state_publisher 可能已经发布 base_footprint->base_scan；
  如果这里再发布同一对 parent/child，会导致 TF 冲突与随机跳变。
- 相机 TF：realsense2_camera 在 publish_tf=true 时会发布相机内部 TF，但不会知道相机与机器人底座的外参，
  因此仍需提供 base_footprint->camera_link（或 base_link->camera_link）这条外参。
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    """
    生成传感器启动描述文件。
    
    该函数负责启动 RPLIDAR A2M12 激光雷达和 RealSense D435i 深度摄像头，
    并发布必要的静态 TF 坐标变换。
    
    Returns:
        LaunchDescription: 包含所有传感器节点和 TF 发布器的启动描述。
    """
    # 与 bringup.launch.py 同时运行时，robot_state_publisher 通常已提供 base_footprint->base_scan。
    # 默认关闭本文件中的激光静态 TF，避免重复发布冲突。
    publish_lidar_tf = LaunchConfiguration('publish_lidar_tf', default='false')

    # RPLIDAR A2M12：
    # - frame_id 建议使用 base_scan（与 TurtleBot3 生态兼容）。
    # - serial_port/serial_baudrate 依赖实际接线与 udev 规则（建议按设备序列号做固定链接）。
    rplidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('rplidar_ros'),
                'launch',
                'rplidar_a2m12_launch.py'
            ])
        ]),
        launch_arguments={
            'channel_type': 'serial',
            'serial_port': '/dev/ttyUSB0',
            'serial_baudrate': '256000',
            'frame_id': 'base_scan',
            'inverted': 'false',
            'angle_compensate': 'true',
            'scan_mode': 'Sensitivity'
        }.items()
    )

    # 启动 RealSense D435i
    # 启用 align_depth 以获取对齐到 RGB 的深度图像，用于 RGB-D SLAM
    # 如果需要，可以启用 IMU（陀螺仪/加速度计），对于基于轮式里程计的 RTAB-MAP 是可选的，但建议开启
    # unite_imu_method 2 表示线性插值
    # 注意：为了稳定性，我们将分辨率降低到 640x480，帧率设为 15fps
    #
    # 话题约定（realsense2_camera 默认）：
    # - 彩色：/camera/color/image_raw, /camera/color/camera_info
    # - 对齐深度：/camera/aligned_depth_to_color/image_raw
    # RTAB-Map 在 rtabmap.launch.py 中会把这些话题 remap 到自己的输入接口名。
    realsense_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('realsense2_camera'),
                'launch',
                'rs_launch.py'
            ])
        ]),
        launch_arguments={
            'align_depth.enable': 'true',# 确保深度图对齐到彩色图
            'enable_sync': 'true',# 强制硬件层级的时间戳同步
            'pointcloud.enable': 'false',# 关闭驱动自带的点云，节省 CPU 给 RTAB-Map 用
            'enable_color': 'true',
            'enable_depth': 'true',
            'initial_reset': 'true', # 启动时复位设备，防止 USB 占用问题
            
            # 颜色流设置
            'rgb_camera.color_profile': '640,480,15', # 宽,高,帧率
            'rgb_camera.enable_auto_exposure': 'true',
            
            # 深度流设置
            'depth_module.depth_profile': '640,480,15',
            'depth_module.enable_auto_exposure': 'true',
            
            # IMU 设置 (如果导致崩溃可设为 false)
            'enable_gyro': 'true',
            'enable_accel': 'true',
            'unite_imu_method': '2',
            
            # publish_tf=true 会发布相机内部的 TF（例如 camera_link 到各 optical frame）。
            # 但它不会自动知道“相机相对底盘”的外参，因此仍需要下面的 static_transform_publisher。
            'publish_tf': 'true',
            'camera_name': 'camera', # 默认值
            'camera_namespace': '' # 显式设置为空，防止双重命名空间
        }.items()
    )

    # 静态 TF：base_link -> camera_link
    # 请根据实际安装位置调整这些值
    # x y z yaw pitch roll
    #arguments=['0.1', '0', '0.2', '0', '0', '0', 'base_link', 'camera_link']
    camera_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_camera_tf',
        # 外参建议来源：
        # - 机械安装图纸/测量值，或
        # - 标定工具（例如手眼标定/AprilTag），或
        # - 先用粗略值跑通，再在 RViz 中微调验证。
        arguments=['0.012', '0', '0.165', '0', '0', '0', 'base_footprint', 'camera_link']
    )

    # 静态 TF：base_link -> base_scan (如果机器人描述文件未提供)
    # TurtleBot3 通常通过 turtlebot3_state_publisher 提供此 TF，但我们添加它是为了防止未运行完整机器人栈的情况。
    # 如果与 turtlebot3_bringup 一起运行，可能会发生冲突。
    # 目前假设未运行标准的 TB3 bringup，所以添加它。
    # 注意：A2M12 可能替换了默认的 LDS-01/02。
    # 默认 TB3 LDS 位置在 -0.032 0 0.172。
    lidar_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_scan_tf',
        condition=IfCondition(publish_lidar_tf),
        # 如果你已经通过 URDF/state_publisher 发布了 base_footprint->base_scan，请删除/禁用该节点，
        # 否则会出现 TF 重复发布导致的 transform 震荡。
        arguments=['-0.032', '0', '0.172', '0', '0', '0', 'base_footprint', 'base_scan']
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'publish_lidar_tf',
            default_value='false',
            description='是否发布 base_footprint->base_scan 静态 TF（与 robot_state_publisher 二选一）'
        ),
        rplidar_launch,
        realsense_launch,
        camera_tf,
        lidar_tf
    ])
