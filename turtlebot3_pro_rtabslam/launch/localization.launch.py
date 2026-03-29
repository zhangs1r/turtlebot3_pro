# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    """
    生成定位启动描述 (map_server + amcl + lifecycle_manager)。
    
    该文件负责加载静态地图并运行 AMCL 定位。
    设计上与 navigation.launch.py 配合，共同构成完整的导航栈。
    """
    rtab_slam_dir = get_package_share_directory('turtlebot3_pro_rtabslam')

    namespace = LaunchConfiguration('namespace')
    map_yaml_file = LaunchConfiguration('map')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    params_file = LaunchConfiguration('params_file')
    use_respawn = LaunchConfiguration('use_respawn')
    log_level = LaunchConfiguration('log_level')

    lifecycle_nodes = ['map_server', 'amcl']

    # 话题重映射：
    # 将默认的 map 话题重映射到 /rtabmap/map，注意同时映射 map_updates 话题
    remappings = [('/tf', 'tf'),
                  ('/tf_static', 'tf_static'),
                  ('map', '/rtabmap/map'),
                  ('map_updates', '/rtabmap/map_updates')]

    # 对参数文件进行 RewrittenYaml 处理，注入 use_sim_time 等全局参数。
    # 特别地，这里将 map_yaml_file 注入到 map_server 的 yaml_filename 参数。
    param_substitutions = {
        'use_sim_time': use_sim_time,
        'yaml_filename': map_yaml_file}

    configured_params = RewrittenYaml(
        source_file=params_file,
        root_key=namespace,
        param_rewrites=param_substitutions,
        convert_types=True)

    stdout_linebuf_envvar = SetEnvironmentVariable(
        'RCUTILS_LOGGING_BUFFERED_STREAM', '1')

    declare_namespace_cmd = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='顶层命名空间')

    declare_map_yaml_cmd = DeclareLaunchArgument(
        'map',
        default_value=os.path.join(rtab_slam_dir, 'maps', 'map.yaml'),
        description='静态地图 YAML 文件的完整路径')

    declare_use_sim_time_cmd = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='如果为 true，则使用仿真 (Gazebo) 时钟')

    declare_params_file_cmd = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(rtab_slam_dir, 'config', 'nav2_params.yaml'),
        description='所有启动节点使用的 ROS2 参数文件的完整路径')

    declare_autostart_cmd = DeclareLaunchArgument(
        'autostart', default_value='true',
        description='是否自动启动 nav2 栈')

    declare_use_respawn_cmd = DeclareLaunchArgument(
        'use_respawn', default_value='False',
        description='如果节点崩溃，是否重启')

    declare_log_level_cmd = DeclareLaunchArgument(
        'log_level', default_value='info',
        description='日志级别')

    # 启动 map_server 节点
    start_map_server_cmd = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        respawn=use_respawn,
        respawn_delay=2.0,
        parameters=[configured_params,
                    {'yaml_filename': map_yaml_file}],
        arguments=['--ros-args', '--log-level', log_level],
        remappings=remappings)

    # 启动 amcl 节点
    start_amcl_cmd = Node(
        package='nav2_amcl',
        executable='amcl',
        name='amcl',
        output='screen',
        respawn=use_respawn,
        respawn_delay=2.0,
        parameters=[configured_params],
        arguments=['--ros-args', '--log-level', log_level],
        remappings=remappings)

    # 启动生命周期管理器，负责激活 map_server 和 amcl
    start_lifecycle_manager_cmd = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_localization',
        output='screen',
        arguments=['--ros-args', '--log-level', log_level],
        parameters=[{'use_sim_time': use_sim_time},
                    {'autostart': autostart},
                    {'node_names': lifecycle_nodes}])

    # 创建启动描述并添加动作
    ld = LaunchDescription()

    ld.add_action(stdout_linebuf_envvar)

    ld.add_action(declare_namespace_cmd)
    ld.add_action(declare_map_yaml_cmd)
    ld.add_action(declare_use_sim_time_cmd)
    ld.add_action(declare_params_file_cmd)
    ld.add_action(declare_autostart_cmd)
    ld.add_action(declare_use_respawn_cmd)
    ld.add_action(declare_log_level_cmd)

    ld.add_action(start_map_server_cmd)
    ld.add_action(start_amcl_cmd)
    ld.add_action(start_lifecycle_manager_cmd)

    return ld
