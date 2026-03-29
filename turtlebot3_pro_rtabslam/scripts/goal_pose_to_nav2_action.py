#!/usr/bin/env python3

"""
PoseStamped 目标点 -> Nav2 NavigateToPose action 的桥接节点。

典型用途是配合 RViz 的默认“2D Goal Pose / Set Goal”工具：
- RViz 默认会发布 /goal_pose（geometry_msgs/PoseStamped）
- Nav2 的标准接口是 NavigateToPose action（nav2_msgs/action/NavigateToPose）

当系统没有安装 nav2_rviz_plugins（或不想依赖对应插件）时，本节点可以作为最小桥接层：
订阅 PoseStamped，并把它转为 action goal 发送给 Nav2。

行为约定：
- 收到新目标时：直接发送新 goal，不做对旧 goal 的显式 cancel。
- 反馈处理：默认丢弃，避免高频日志刷屏（需要时可扩展为节流打印）。
"""

from __future__ import annotations

from typing import Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose


class GoalPoseToNav2Action(Node):
    """
    将 RViz 的 /goal_pose (PoseStamped) 转换为 Nav2 的 NavigateToPose Action 请求。

    适用场景：
    - 系统未安装 nav2_rviz_plugins，无法在 RViz 里使用 Nav2 Goal Tool（Action Client）。
    - 使用 RViz 默认的 SetGoal 工具发布 /goal_pose，然后由本节点转发给 Nav2。
    """

    def __init__(self) -> None:
        """
        初始化订阅与 ActionClient，并在收到目标点时触发 NavigateToPose 请求。
        """
        super().__init__('goal_pose_to_nav2_action')

        # 参数化的好处：
        # - goal_topic：兼容不同 RViz 工具/项目对目标话题的命名差异。
        # - action_name：允许切换到其他 action（例如自定义导航 action），默认保持与 nav2_bringup 一致。
        # - wait_for_server_sec：避免启动初期 action server 尚未就绪导致发送失败。
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('action_name', 'navigate_to_pose')
        self.declare_parameter('wait_for_server_sec', 2.0)

        goal_topic = self.get_parameter('goal_topic').get_parameter_value().string_value
        action_name = self.get_parameter('action_name').get_parameter_value().string_value

        self._wait_for_server_sec = float(
            self.get_parameter('wait_for_server_sec').get_parameter_value().double_value
        )

        self._action_client = ActionClient(self, NavigateToPose, action_name)
        self._current_goal_handle = None

        # RViz 发布目标的频率较低，使用默认队列深度即可。
        self._sub = self.create_subscription(PoseStamped, goal_topic, self._on_goal_pose, 10)
        self.get_logger().info(f'Listening goal topic: {goal_topic}')
        self.get_logger().info(f'Nav2 action name: {action_name}')

    def _on_goal_pose(self, msg: PoseStamped) -> None:
        """
        接收 RViz 发布的 PoseStamped，并向 Nav2 发送 NavigateToPose 目标。
        """
        # Nav2 可能在生命周期管理器拉起前短暂不可用，因此每次收到目标都先做一次短等待。
        if not self._action_client.wait_for_server(timeout_sec=self._wait_for_server_sec):
            self.get_logger().error('Nav2 action server not available (navigate_to_pose).')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = msg

        self.get_logger().info(
            f'Sending goal: frame={msg.header.frame_id}, '
            f'x={msg.pose.position.x:.3f}, y={msg.pose.position.y:.3f}'
        )

        send_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self._on_feedback)
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        """
        处理 Action server 对 goal 的接收结果。
        """
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Goal rejected by Nav2.')
            return

        # 保存 handle 的主要目的是为了未来扩展：取消/替换目标、查询状态等。
        self._current_goal_handle = goal_handle
        self.get_logger().info('Goal accepted by Nav2.')

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_feedback(self, feedback_msg) -> None:
        """
        处理 Nav2 的反馈消息（默认不刷屏，仅保留最小输出）。
        """
        _ = feedback_msg

    def _on_result(self, future) -> None:
        """
        处理 Nav2 目标完成结果。
        """
        result = future.result().result
        status = future.result().status
        _ = result
        self.get_logger().info(f'Goal finished with status={status}.')


def main(args: Optional[list[str]] = None) -> None:
    """
    进程入口：启动 ROS 节点并阻塞运行。
    """
    rclpy.init(args=args)
    node = GoalPoseToNav2Action()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
