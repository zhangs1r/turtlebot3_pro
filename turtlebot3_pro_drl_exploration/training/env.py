import os
from skimage import io
from skimage.measure import block_reduce
from copy import deepcopy

from sensor import sensor_work
from utils import *

"""Env 是训练时的仿真环境封装：
- 管理 ground_truth（真值图）与 robot_belief（机器人已知图）
- 接收航点动作并更新位置/观测
- 计算奖励、探索率、累计路程
"""


class Env:
    # 环境对象维护三类核心状态：
    # - ground truth 地图（仅仿真可见）
    # - 机器人 belief 地图（当前已观测区域）
    # - 奖励、探索率、累计路程
    def __init__(self, episode_index, plot=False):
        self.episode_index = episode_index
        self.plot = plot
        self.ground_truth, self.robot_cell = self.import_ground_truth(episode_index)
        self.ground_truth_size = np.shape(self.ground_truth)  # cell
        self.cell_size = CELL_SIZE  # meter

        self.robot_location = np.array([0.0, 0.0])  # meter

        self.robot_belief = np.ones(self.ground_truth_size) * 127
        self.belief_origin_x = -np.round(self.robot_cell[0] * self.cell_size, 1)   # meter
        self.belief_origin_y = -np.round(self.robot_cell[1] * self.cell_size, 1)  # meter

        self.global_frontiers = set()

        self.sensor_range = SENSOR_RANGE  # meter
        self.travel_dist = 0  # meter
        self.explored_rate = 0

        self.robot_belief = sensor_work(self.robot_cell, self.sensor_range / self.cell_size, self.robot_belief,
                                        self.ground_truth)
        self.old_belief = deepcopy(self.robot_belief)

        self.belief_info = MapInfo(self.robot_belief, self.belief_origin_x, self.belief_origin_y, self.cell_size)

        self.ground_truth_info = MapInfo(self.ground_truth, self.belief_origin_x, self.belief_origin_y, self.cell_size)

        if self.plot:
            self.frame_files = []
            self.trajectory_x = [self.robot_location[0]]
            self.trajectory_y = [self.robot_location[1]]

    def import_ground_truth(self, episode_index):
        # 按 episode 轮换地图，提升训练地图多样性。
        map_dir = f'maps'
        map_list = os.listdir(map_dir)
        map_index = episode_index % np.size(map_list)
        ground_truth = (io.imread(map_dir + '/' + map_list[map_index], 1) * 255).astype(int)

        ground_truth = block_reduce(ground_truth, 2, np.min)

        robot_cell = np.nonzero(ground_truth == 208)
        robot_cell = np.array([np.array(robot_cell)[1, 10], np.array(robot_cell)[0, 10]])

        # 把原图像素映射为本项目占据栅格语义值：
        # 常量映射：FREE=255，OCCUPIED=1。
        ground_truth = (ground_truth > 150) | ((ground_truth <= 80) & (ground_truth >= 50))
        ground_truth = ground_truth * 254 + 1

        return ground_truth, robot_cell

    def update_robot_location(self, robot_location):
        # 世界坐标(m) -> 栅格坐标(cell)，并更新轨迹。
        self.robot_location = robot_location
        self.robot_cell = np.array([round((robot_location[0] - self.belief_origin_x) / self.cell_size),
                                    round((robot_location[1] - self.belief_origin_y) / self.cell_size)])
        if self.plot:
            self.trajectory_x.append(self.robot_location[0])
            self.trajectory_y.append(self.robot_location[1])

    def update_robot_belief(self):
        # 使用传感器模型在当前位置“揭示”可观测区域。
        self.robot_belief = sensor_work(self.robot_cell, round(self.sensor_range / self.cell_size), self.robot_belief,
                                        self.ground_truth)

    def calculate_reward(self, dist):
        # 奖励由两部分组成：
        # 1）移动惩罚（走得越短越好）
        # 2）前沿减少奖励（发现并消除未知边界）
        reward = 0
        reward -= dist / UPDATING_MAP_SIZE * 5
        
        global_frontiers = get_frontier_in_map(self.belief_info)
        if len(global_frontiers) == 0:
            delta_num = len(self.global_frontiers)
        else:
            observed_frontiers = self.global_frontiers - global_frontiers
            delta_num = len(observed_frontiers)

        reward += delta_num / (SENSOR_RANGE * 3.14 // FRONTIER_CELL_SIZE)

        self.global_frontiers = global_frontiers
        self.old_belief = deepcopy(self.robot_belief)

        return reward

    def evaluate_exploration_rate(self):
        # 探索率 = belief 中已知 free / ground truth 中真实 free。
        self.explored_rate = np.sum(self.robot_belief == 255) / np.sum(self.ground_truth == 255)

    def step(self, next_waypoint):
        # 一步 RL 交互：移动 -> 传感更新 -> 指标更新 -> 计算奖励。
        dist = np.linalg.norm(self.robot_location - next_waypoint)
        self.update_robot_location(next_waypoint)
        self.update_robot_belief()

        self.travel_dist += dist
        self.evaluate_exploration_rate()

        reward = self.calculate_reward(dist)

        return reward

    def plot_env(self, step):
        import matplotlib.pyplot as plt

        plt.subplot(1, 3, 1)
        plt.imshow(self.robot_belief, cmap='gray')
        plt.axis('off')
        plt.plot((self.robot_location[0] - self.belief_origin_x) / self.cell_size,
                 (self.robot_location[1] - self.belief_origin_y) / self.cell_size, 'mo', markersize=4, zorder=5)
        plt.plot((np.array(self.trajectory_x) - self.belief_origin_x) / self.cell_size,
                 (np.array(self.trajectory_y) - self.belief_origin_y) / self.cell_size, 'b', linewidth=2, zorder=1)
        plt.suptitle('Explored ratio: {:.4g}  Travel distance: {:.4g}'.format(self.explored_rate, self.travel_dist))
        plt.tight_layout()
        # 调试可打开：plt.show()
        plt.savefig('{}/{}_{}_samples.png'.format(gifs_path, self.episode_index, step), dpi=150)
        frame = '{}/{}_{}_samples.png'.format(gifs_path, self.episode_index, step)
        plt.close()
        self.frame_files.append(frame)
