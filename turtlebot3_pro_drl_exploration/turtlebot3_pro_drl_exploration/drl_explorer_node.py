#!/usr/bin/env python3

import copy
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import rclpy
import torch
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from tf2_ros import Buffer, TransformException, TransformListener

from .paper_core.agent import Agent
from .paper_core.model import PolicyNet
from .paper_core.parameter import (
    CELL_SIZE,
    EMBEDDING_DIM,
    FREE,
    NODE_INPUT_DIM,
    OCCUPIED,
    UNKNOWN,
)
from .paper_core.utils import MapInfo


@dataclass
class ActionCandidate:
    action_index: int
    node_index: int
    coords: np.ndarray
    logp: float
    utility: float


class DrlExplorerNode(Node):
    def __init__(self) -> None:
        super().__init__('drl_explorer')

        # ROS interfaces
        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._goal_pub = self.create_publisher(PoseStamped, 'drl_next_goal', 10)

        # Parameters
        self.declare_parameter('map_topic', '/map')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('robot_frame', 'base_link')
        self.declare_parameter('planning_period_sec', 2.0)
        self.declare_parameter('goal_timeout_sec', 45.0)
        self.declare_parameter('goal_tolerance_xy', 0.35)
        self.declare_parameter('min_goal_distance', 0.25)
        self.declare_parameter('free_threshold', 20)
        self.declare_parameter('occupied_threshold', 65)
        self.declare_parameter('deterministic_policy', True)
        self.declare_parameter('planner_mode', 'drl')  # drl | utility
        self.declare_parameter('use_lookahead', True)
        self.declare_parameter('lookahead_horizon', 3)
        self.declare_parameter('lookahead_top_k', 6)
        self.declare_parameter('lookahead_discount', 0.9)
        self.declare_parameter('utility_weight', 1.0)
        self.declare_parameter('distance_weight', 0.8)
        self.declare_parameter('heading_weight', 0.25)
        self.declare_parameter('revisit_penalty', 0.75)
        self.declare_parameter('policy_weight', 0.25)
        self.declare_parameter('checkpoint_path', '')
        self.declare_parameter('device', 'cpu')

        self.map_topic = self.get_parameter('map_topic').value
        self.map_frame = self.get_parameter('map_frame').value
        self.robot_frame = self.get_parameter('robot_frame').value
        self.planning_period_sec = float(self.get_parameter('planning_period_sec').value)
        self.goal_timeout_sec = float(self.get_parameter('goal_timeout_sec').value)
        self.goal_tolerance_xy = float(self.get_parameter('goal_tolerance_xy').value)
        self.min_goal_distance = float(self.get_parameter('min_goal_distance').value)
        self.free_threshold = int(self.get_parameter('free_threshold').value)
        self.occupied_threshold = int(self.get_parameter('occupied_threshold').value)
        self.deterministic_policy = bool(self.get_parameter('deterministic_policy').value)
        self.planner_mode = str(self.get_parameter('planner_mode').value)
        self.use_lookahead = bool(self.get_parameter('use_lookahead').value)
        self.lookahead_horizon = int(self.get_parameter('lookahead_horizon').value)
        self.lookahead_top_k = int(self.get_parameter('lookahead_top_k').value)
        self.lookahead_discount = float(self.get_parameter('lookahead_discount').value)
        self.utility_weight = float(self.get_parameter('utility_weight').value)
        self.distance_weight = float(self.get_parameter('distance_weight').value)
        self.heading_weight = float(self.get_parameter('heading_weight').value)
        self.revisit_penalty = float(self.get_parameter('revisit_penalty').value)
        self.policy_weight = float(self.get_parameter('policy_weight').value)
        self.checkpoint_path = str(self.get_parameter('checkpoint_path').value)

        requested_device = str(self.get_parameter('device').value)
        if requested_device == 'cuda' and torch.cuda.is_available():
            self.device = torch.device('cuda')
        else:
            self.device = torch.device('cpu')

        # Planner state
        self._latest_map_msg: Optional[OccupancyGrid] = None
        self._latest_map_info: Optional[MapInfo] = None
        self._cell_size_warned = False

        self._goal_handle = None
        self._goal_sent_time = None
        self._active_goal_xy: Optional[np.ndarray] = None
        self._goal_request_inflight = False

        self._model_loaded = False
        self._policy_net = PolicyNet(NODE_INPUT_DIM, EMBEDDING_DIM).to(self.device)
        self._policy_net.eval()
        self._load_checkpoint(self.checkpoint_path)
        self._agent = Agent(self._policy_net, device=self.device, plot=False)

        self._last_motion_vec: Optional[np.ndarray] = None

        self._map_sub = self.create_subscription(
            OccupancyGrid,
            self.map_topic,
            self._on_map,
            10,
        )
        self._timer = self.create_timer(self.planning_period_sec, self._planning_tick)

        self.get_logger().info('DRL explorer node ready.')
        self.get_logger().info(
            f'planner_mode={self.planner_mode}, use_lookahead={self.use_lookahead}, '
            f'checkpoint_loaded={self._model_loaded}'
        )

    def _load_checkpoint(self, checkpoint_path: str) -> None:
        if not checkpoint_path:
            self.get_logger().warn('No checkpoint_path configured. Fallback to utility planner.')
            return

        if not os.path.isfile(checkpoint_path):
            self.get_logger().warn(
                f'Checkpoint not found: {checkpoint_path}. Fallback to utility planner.'
            )
            return

        try:
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            if isinstance(checkpoint, dict) and 'policy_model' in checkpoint:
                state_dict = checkpoint['policy_model']
            elif isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                state_dict = checkpoint['state_dict']
            else:
                state_dict = checkpoint

            self._policy_net.load_state_dict(state_dict)
            self._model_loaded = True
            self.get_logger().info(f'Loaded checkpoint: {checkpoint_path}')
        except Exception as exc:
            self.get_logger().error(f'Failed to load checkpoint: {exc}')
            self._model_loaded = False

    def _on_map(self, msg: OccupancyGrid) -> None:
        self._latest_map_msg = msg

    def _planning_tick(self) -> None:
        if self._latest_map_msg is None:
            return

        robot_xy = self._get_robot_xy()
        if robot_xy is None:
            return

        if self._goal_handle is not None or self._goal_request_inflight:
            self._check_goal_timeout(robot_xy)
            return

        map_info = self._convert_map_to_map_info(self._latest_map_msg)
        if map_info is None:
            return

        self._latest_map_info = map_info

        try:
            self._agent.update_planning_state(map_info, robot_xy)
        except Exception as exc:
            self.get_logger().warn(f'Planning state update failed: {exc}')
            return

        if float(np.sum(self._agent.utility)) <= 0.0:
            self.get_logger().info('No frontier utility left in local graph. Exploration may be complete.')
            return

        observation = self._agent.get_observation()
        candidates = self._extract_candidates(observation)
        if not candidates:
            self.get_logger().warn('No valid action candidate from graph neighbors.')
            return

        best = self._pick_candidate(candidates, robot_xy)
        if best is None:
            return

        goal_xy = best.coords
        dist_to_goal = float(np.linalg.norm(goal_xy - robot_xy))
        if dist_to_goal < self.min_goal_distance:
            self.get_logger().info('Selected goal too close; skip this cycle.')
            return

        self._send_nav_goal(robot_xy, goal_xy)

    def _get_robot_xy(self) -> Optional[np.ndarray]:
        try:
            trans = self._tf_buffer.lookup_transform(
                self.map_frame,
                self.robot_frame,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.2),
            )
            return np.array(
                [
                    trans.transform.translation.x,
                    trans.transform.translation.y,
                ],
                dtype=float,
            )
        except TransformException:
            return None

    def _convert_map_to_map_info(self, msg: OccupancyGrid) -> Optional[MapInfo]:
        if msg.info.width == 0 or msg.info.height == 0:
            return None

        grid = np.asarray(msg.data, dtype=np.int16).reshape(msg.info.height, msg.info.width)
        belief = np.full(grid.shape, UNKNOWN, dtype=np.int16)

        free_mask = (grid >= 0) & (grid <= self.free_threshold)
        occ_mask = grid >= self.occupied_threshold

        belief[free_mask] = FREE
        belief[occ_mask] = OCCUPIED

        resolution = float(msg.info.resolution)
        if not self._cell_size_warned and abs(resolution - CELL_SIZE) > 1e-4:
            self.get_logger().warn(
                f'Map resolution({resolution:.3f}) != planner CELL_SIZE({CELL_SIZE:.3f}). '
                'Please keep paper_core/parameter.py CELL_SIZE consistent with map resolution.'
            )
            self._cell_size_warned = True

        return MapInfo(
            belief,
            float(msg.info.origin.position.x),
            float(msg.info.origin.position.y),
            resolution,
        )

    def _extract_candidates(self, observation) -> List[ActionCandidate]:
        current_edge = observation[4][0, :, 0].detach().cpu().numpy().astype(int)
        edge_mask = observation[5][0, 0, :].detach().cpu().numpy().astype(bool)

        logp = None
        if self._model_loaded and self.planner_mode != 'utility':
            with torch.no_grad():
                logp_tensor = self._policy_net(*observation)
            logp = logp_tensor[0].detach().cpu().numpy()

        candidates: List[ActionCandidate] = []
        for i, node_idx in enumerate(current_edge):
            if i >= len(edge_mask) or edge_mask[i]:
                continue
            if node_idx < 0 or node_idx >= len(self._agent.node_coords):
                continue

            coords = self._agent.node_coords[node_idx]
            node_wrapper = self._agent.node_manager.nodes_dict.find((coords[0], coords[1]))
            utility = float(node_wrapper.data.utility) if node_wrapper is not None else 0.0
            candidate_logp = float(logp[i]) if logp is not None else 0.0

            candidates.append(
                ActionCandidate(
                    action_index=i,
                    node_index=int(node_idx),
                    coords=np.asarray(coords, dtype=float),
                    logp=candidate_logp,
                    utility=utility,
                )
            )

        return candidates

    def _pick_candidate(
        self,
        candidates: List[ActionCandidate],
        robot_xy: np.ndarray,
    ) -> Optional[ActionCandidate]:
        if not candidates:
            return None

        if not self.use_lookahead or self.lookahead_horizon <= 1:
            return self._pick_single_step(candidates, robot_xy)

        if self._model_loaded and self.planner_mode != 'utility':
            ranked = sorted(candidates, key=lambda c: c.logp, reverse=True)
        else:
            ranked = sorted(candidates, key=lambda c: c.utility, reverse=True)
        ranked = ranked[: max(1, min(len(ranked), self.lookahead_top_k))]

        coord_to_index = {
            (float(x), float(y)): idx
            for idx, (x, y) in enumerate(self._agent.node_coords)
        }

        best_candidate = None
        best_score = -1e9
        for candidate in ranked:
            score = self._score_candidate_lookahead(candidate, robot_xy, coord_to_index)
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is not None:
            self.get_logger().info(
                f'Select goal ({best_candidate.coords[0]:.2f}, {best_candidate.coords[1]:.2f}) '
                f'lookahead_score={best_score:.3f}, utility={best_candidate.utility:.1f}, '
                f'logp={best_candidate.logp:.3f}'
            )
        return best_candidate

    def _pick_single_step(
        self,
        candidates: List[ActionCandidate],
        robot_xy: np.ndarray,
    ) -> ActionCandidate:
        if self._model_loaded and self.planner_mode != 'utility':
            if self.deterministic_policy:
                return max(candidates, key=lambda c: c.logp)

            probs = np.asarray([math.exp(c.logp) for c in candidates], dtype=float)
            probs = probs / max(np.sum(probs), 1e-8)
            idx = int(np.random.choice(len(candidates), p=probs))
            return candidates[idx]

        # Pure utility fallback
        best = None
        best_score = -1e9
        for candidate in candidates:
            score = self.utility_weight * candidate.utility
            score -= self.distance_weight * float(np.linalg.norm(candidate.coords - robot_xy))
            if score > best_score:
                best_score = score
                best = candidate
        return best if best is not None else candidates[0]

    def _score_candidate_lookahead(
        self,
        first: ActionCandidate,
        robot_xy: np.ndarray,
        coord_to_index: Dict[Tuple[float, float], int],
    ) -> float:
        score = 0.0
        prev_xy = np.asarray(robot_xy, dtype=float)
        prev_vec = copy.deepcopy(self._last_motion_vec)
        visited = {int(self._agent.current_index)}

        current_index = first.node_index
        policy_bonus = self.policy_weight * first.logp if self._model_loaded else 0.0

        for depth in range(max(1, self.lookahead_horizon)):
            current_xy = np.asarray(self._agent.node_coords[current_index], dtype=float)
            move_vec = current_xy - prev_xy
            dist = float(np.linalg.norm(move_vec))

            node_wrapper = self._agent.node_manager.nodes_dict.find((current_xy[0], current_xy[1]))
            utility = float(node_wrapper.data.utility) if node_wrapper is not None else 0.0

            turn_cost = self._turn_cost(prev_vec, move_vec)
            step_score = self.utility_weight * utility
            step_score -= self.distance_weight * dist
            step_score -= self.heading_weight * turn_cost
            if current_index in visited:
                step_score -= self.revisit_penalty

            score += (self.lookahead_discount ** depth) * step_score
            visited.add(current_index)

            prev_xy = current_xy
            if np.linalg.norm(move_vec) > 1e-6:
                prev_vec = move_vec

            if depth >= self.lookahead_horizon - 1:
                break

            next_index = self._choose_rollout_next(current_index, prev_xy, visited, coord_to_index)
            if next_index is None:
                break
            current_index = next_index

        return score + policy_bonus

    def _choose_rollout_next(
        self,
        current_index: int,
        current_xy: np.ndarray,
        visited: set,
        coord_to_index: Dict[Tuple[float, float], int],
    ) -> Optional[int]:
        coords = self._agent.node_coords[current_index]
        node_wrapper = self._agent.node_manager.nodes_dict.find((coords[0], coords[1]))
        if node_wrapper is None:
            return None

        node = node_wrapper.data
        best_idx = None
        best_score = -1e9

        for neighbor in node.neighbor_set:
            key = (float(neighbor[0]), float(neighbor[1]))
            idx = coord_to_index.get(key)
            if idx is None or idx == current_index:
                continue

            neighbor_xy = np.asarray(self._agent.node_coords[idx], dtype=float)
            neighbor_node = self._agent.node_manager.nodes_dict.find((neighbor_xy[0], neighbor_xy[1]))
            utility = float(neighbor_node.data.utility) if neighbor_node is not None else 0.0

            score = self.utility_weight * utility
            score -= self.distance_weight * float(np.linalg.norm(neighbor_xy - current_xy))
            if idx in visited:
                score -= self.revisit_penalty

            if score > best_score:
                best_score = score
                best_idx = idx

        return best_idx

    @staticmethod
    def _turn_cost(prev_vec: Optional[np.ndarray], move_vec: np.ndarray) -> float:
        if prev_vec is None:
            return 0.0
        prev_norm = float(np.linalg.norm(prev_vec))
        move_norm = float(np.linalg.norm(move_vec))
        if prev_norm < 1e-6 or move_norm < 1e-6:
            return 0.0
        cos_theta = float(np.dot(prev_vec, move_vec) / (prev_norm * move_norm))
        cos_theta = max(-1.0, min(1.0, cos_theta))
        return abs(math.acos(cos_theta))

    def _send_nav_goal(self, robot_xy: np.ndarray, goal_xy: np.ndarray) -> None:
        if not self._nav_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn('navigate_to_pose action server is not ready.')
            return

        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.map_frame
        msg.pose.position.x = float(goal_xy[0])
        msg.pose.position.y = float(goal_xy[1])
        msg.pose.position.z = 0.0

        yaw = math.atan2(goal_xy[1] - robot_xy[1], goal_xy[0] - robot_xy[0])
        msg.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.orientation.w = math.cos(yaw / 2.0)

        goal = NavigateToPose.Goal()
        goal.pose = msg

        self._goal_pub.publish(msg)
        self._active_goal_xy = np.asarray(goal_xy, dtype=float)
        self._goal_sent_time = self.get_clock().now()
        self._goal_request_inflight = True
        self._last_motion_vec = self._active_goal_xy - robot_xy

        self.get_logger().info(
            f'Send Nav2 goal: ({goal_xy[0]:.2f}, {goal_xy[1]:.2f}), '
            f'dist={np.linalg.norm(goal_xy - robot_xy):.2f}m'
        )

        future = self._nav_client.send_goal_async(goal)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f'Goal send failed: {exc}')
            self._clear_goal_state()
            return

        self._goal_request_inflight = False
        if not goal_handle.accepted:
            self.get_logger().warn('Goal rejected by Nav2.')
            self._clear_goal_state()
            return

        self._goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_goal_result)

    def _on_goal_result(self, future) -> None:
        try:
            result_wrap = future.result()
            status = int(result_wrap.status)
            self.get_logger().info(f'Goal finished, status={status}')
        except Exception as exc:
            self.get_logger().error(f'Goal result failed: {exc}')
        finally:
            self._clear_goal_state()

    def _check_goal_timeout(self, robot_xy: np.ndarray) -> None:
        if self._goal_sent_time is None:
            return

        elapsed = (self.get_clock().now() - self._goal_sent_time).nanoseconds / 1e9
        if self._active_goal_xy is not None and self._goal_handle is not None:
            dist = float(np.linalg.norm(self._active_goal_xy - robot_xy))
            if dist < self.goal_tolerance_xy:
                self.get_logger().info('Close to active goal, waiting Nav2 result.')

        if elapsed < self.goal_timeout_sec:
            return

        self.get_logger().warn('Goal timeout reached, canceling current goal.')
        if self._goal_handle is not None:
            cancel_future = self._goal_handle.cancel_goal_async()
            cancel_future.add_done_callback(lambda _: self._clear_goal_state())
        else:
            self._clear_goal_state()

    def _clear_goal_state(self) -> None:
        self._goal_handle = None
        self._goal_sent_time = None
        self._active_goal_xy = None
        self._goal_request_inflight = False


def main(args=None):
    rclpy.init(args=args)
    node = DrlExplorerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
