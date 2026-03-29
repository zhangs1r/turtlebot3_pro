#!/usr/bin/env python3

"""Bridge RViz 2D Goal Pose topic (/goal_pose) to Nav2 NavigateToPose action.

用法：
- RViz 使用 "2D Goal Pose" 工具发布 /goal_pose。
- 本节点接收该 PoseStamped，并转发给 /navigate_to_pose action。
"""

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose


class GoalPoseBridge(Node):
    def __init__(self):
        super().__init__('goal_pose_bridge')

        self._client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._sub = self.create_subscription(
            PoseStamped,
            '/goal_pose',
            self._on_goal_pose,
            10,
        )

        self.get_logger().info('GoalPose bridge ready: /goal_pose -> /navigate_to_pose')

    def _on_goal_pose(self, msg: PoseStamped):
        if not self._client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn('navigate_to_pose action server not available yet')
            return

        goal = NavigateToPose.Goal()
        goal.pose = msg

        self.get_logger().info(
            f'Received 2D goal: x={msg.pose.position.x:.2f}, '
            f'y={msg.pose.position.y:.2f}. Sending to Nav2...'
        )

        send_goal_future = self._client.send_goal_async(goal)
        send_goal_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Goal rejected by Nav2')
            return

        self.get_logger().info('Goal accepted by Nav2')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_result(self, future):
        result = future.result()
        self.get_logger().info(f'Navigation finished with status={result.status}')


def main():
    rclpy.init()
    node = GoalPoseBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
