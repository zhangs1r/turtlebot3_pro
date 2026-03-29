#!/usr/bin/env python3

"""
Twist -> TwistStamped 的简单桥接节点。

在一个导航系统里，速度指令的“语义”往往包含两个层面：
- Twist：只描述线速度/角速度，不带时间戳。
- TwistStamped：在 Twist 基础上增加 header.stamp（产生时间）与 frame_id（参考坐标系）。

本节点的用途是把上游发布的 Twist（例如 Nav2、teleop）转换成带时间戳的 TwistStamped，
以便满足某些下游组件/中间件对时间信息的需求，或便于调试与回放。

默认话题：
- 订阅：/cmd_vel_in（geometry_msgs/Twist）
- 发布：/cmd_vel（geometry_msgs/TwistStamped）
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TwistStamped


class TwistToTwistStamped(Node):
    """
    接收 Twist 并发布 TwistStamped。

    约定：
    - header.stamp：使用本机节点时钟的当前时间（与 use_sim_time 配置相关）。
    - header.frame_id：默认写入 base_link，用于表达“速度相对机器人基座”。
      如果你的系统约定使用 base_footprint 作为基座坐标系，可以在此处统一改为 base_footprint。
    """

    def __init__(self):
        super().__init__('twist_to_twist_stamped')
        
        # 输入端：只含速度，不含时间戳。
        # 上游常见来源：Nav2 controller 输出、键盘遥控、外部控制器等。
        self.subscription = self.create_subscription(
            Twist,
            '/cmd_vel_in',
            self.listener_callback,
            10)
            
        # 输出端：补齐时间戳与参考坐标系，便于下游做时序一致性处理。
        self.publisher = self.create_publisher(
            TwistStamped,
            '/cmd_vel',
            10)
            
        self.get_logger().info('Twist to TwistStamped converter started.')

    def listener_callback(self, msg):
        """
        回调：把 Twist 包装成 TwistStamped 并发布。

        参数：
        - msg：上游速度指令（线速度/角速度）。
        """
        stamped_msg = TwistStamped()
        stamped_msg.header.stamp = self.get_clock().now().to_msg()
        stamped_msg.header.frame_id = 'base_link'
        stamped_msg.twist = msg
        
        self.publisher.publish(stamped_msg)


def main(args=None):
    """
    进程入口：初始化 rclpy，创建节点并进入 spin 循环。
    """
    rclpy.init(args=args)
    converter = TwistToTwistStamped()
    rclpy.spin(converter)
    converter.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
