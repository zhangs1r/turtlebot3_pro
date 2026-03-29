cmake_minimum_required(VERSION 3.8)
project(turtlebot3_pro_rtabslam)

# 本包以 launch/config/scripts 为主：
# - launch/：系统编排入口（bringup、sensors、rtabmap、nav2）
# - config/：Nav2 参数、RViz 视图
# - scripts/：rclpy 小工具节点（以 install(PROGRAMS) 安装为可执行）

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

# 资源文件安装到 share/<pkg>，以便 FindPackageShare 在 launch 中可定位到这些文件。
install(DIRECTORY
  launch
  config
  scripts
  maps
  DESTINATION share/${PROJECT_NAME}
)

# Python 节点作为“可执行程序”安装到 lib/<pkg>，便于 ros2 run / ros2 launch 直接调用。
install(PROGRAMS
  scripts/twist_to_twist_stamped.py
  scripts/goal_pose_to_nav2_action.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
