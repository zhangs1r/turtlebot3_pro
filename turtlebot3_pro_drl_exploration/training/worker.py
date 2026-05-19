import torch

from env import Env
from agent import Agent
from utils import *
from model import PolicyNet
from ground_truth_node_manager import GroundTruthNodeManager

"""Worker 负责“单回合采样”：
1. 在环境中按当前 policy 执行动作直到 done/步数上限。
2. 同时保存 policy 观测与 critic 观测（ground-truth 图）。
3. 产出固定 27 槽位的数据结构供 driver 训练。
"""

if not os.path.exists(gifs_path):
    os.makedirs(gifs_path)


class Worker:
    # Worker 负责执行“一个完整回合”并缓存转移样本。
    # 它由 Runner（Ray Actor）调用，不直接由 driver 调用。
    def __init__(self, meta_agent_id, policy_net, global_step, device='cpu', save_image=False):
        self.meta_agent_id = meta_agent_id
        self.global_step = global_step
        self.save_image = save_image
        self.device = device

        self.env = Env(global_step, plot=self.save_image)
        self.robot = Agent(policy_net, self.device, self.save_image)

        self.ground_truth_node_manager = GroundTruthNodeManager(self.robot.node_manager, self.env.ground_truth_info,
                                                                device=self.device, plot=self.save_image)

        self.episode_buffer = []
        self.perf_metrics = dict()
        for i in range(27):
            self.episode_buffer.append([])
        # 回放槽位说明（固定 27 个列表）：
        # 0-5   : 当前状态 s_t（policy 输入）
        # 6-8   : 动作 / 奖励 / 结束标志
        # 9-14  : 下一状态 s_{t+1}（policy 输入）
        # 15-20 : 当前状态 s_t（critic 输入，来自 ground-truth 图）
        # 21-26 : 下一状态 s_{t+1}（critic 输入，来自 ground-truth 图）

    def run_episode(self):
        # 单回合时序：初始化图 -> 反复 (存s, 选a, 环境步进, 存r/done, 存s')。
        done = False
        # 从初始 belief 地图先构建第一版规划图。
        self.robot.update_planning_state(self.env.belief_info, self.env.robot_location)
        observation = self.robot.get_observation()
        ground_truth_observation = self.ground_truth_node_manager.get_ground_truth_observation(self.env.robot_location)

        if self.save_image:
            self.robot.plot_env()
            self.ground_truth_node_manager.plot_ground_truth_env(self.env.robot_location)
            self.env.plot_env(0)

        for i in range(MAX_EPISODE_STEP):
            # 先保存动作前状态 s_t。
            self.save_observation(observation, ground_truth_observation)

            next_location, action_index = self.robot.select_next_waypoint(observation)
            self.save_action(action_index)

            node = self.robot.node_manager.nodes_dict.find((self.robot.location[0], self.robot.location[1]))
            check = np.array(list(node.data.neighbor_set)).reshape(-1, 2)
            assert next_location[0] + next_location[1] * 1j in check[:, 0] + check[:, 1] * 1j, print(next_location, self.robot.location, node.data.neighbor_set)
            assert next_location[0] != self.robot.location[0] or next_location[1] != self.robot.location[1]

            reward = self.env.step(next_location)

            self.robot.update_planning_state(self.env.belief_info, self.env.robot_location)
            if self.robot.utility.sum() == 0:
                # 没有正效用节点时，基本可视为当前地图已探索完成。
                done = True
                reward += 20
            self.save_reward_done(reward, done)

            # 环境步进后保存下一状态 s_{t+1}。
            observation = self.robot.get_observation()
            ground_truth_observation = self.ground_truth_node_manager.get_ground_truth_observation(
                self.env.robot_location)
            self.save_next_observations(observation, ground_truth_observation)

            if self.save_image:
                self.robot.plot_env()
                self.ground_truth_node_manager.plot_ground_truth_env(self.env.robot_location)
                self.env.plot_env(i+1)

            if done:
                break

        # 保存本回合性能指标（供 driver 聚合统计）。
        self.perf_metrics['travel_dist'] = self.env.travel_dist
        self.perf_metrics['explored_rate'] = self.env.explored_rate
        self.perf_metrics['success_rate'] = done

        # 可选：导出轨迹 GIF 便于可视化回放。
        if self.save_image:
            make_gif(gifs_path, self.global_step, self.env.frame_files, self.env.explored_rate)

    def save_observation(self, observation, ground_truth_observation):
        # 保存当前时刻 s_t（policy 与 critic 两套图输入）。
        node_inputs, node_padding_mask, edge_mask, current_index, current_edge, edge_padding_mask = observation
        self.episode_buffer[0] += node_inputs
        self.episode_buffer[1] += node_padding_mask.bool()
        self.episode_buffer[2] += edge_mask.bool()
        self.episode_buffer[3] += current_index
        self.episode_buffer[4] += current_edge
        self.episode_buffer[5] += edge_padding_mask.bool()

        critic_node_inputs, critic_node_padding_mask, critic_edge_mask, critic_current_index, critic_current_edge, critic_edge_padding_mask = ground_truth_observation
        self.episode_buffer[15] += critic_node_inputs
        self.episode_buffer[16] += critic_node_padding_mask.bool()
        self.episode_buffer[17] += critic_edge_mask.bool()
        self.episode_buffer[18] += critic_current_index
        self.episode_buffer[19] += critic_current_edge
        self.episode_buffer[20] += critic_edge_padding_mask.bool()

        # 对齐校验：policy 与 critic 的动作索引必须对应同一条边。
        assert torch.all(current_edge == critic_current_edge), print(current_edge, critic_current_edge, current_index, critic_current_index)
        assert torch.all(node_inputs[0, current_index.item(), :2] == critic_node_inputs[0, critic_current_index.item(), :2]), print(node_inputs[0, current_index.item()], critic_node_inputs[0, critic_current_index.item()])
        assert torch.all(torch.gather(node_inputs, 1, current_edge.repeat(1, 1, 2)) == torch.gather(critic_node_inputs, 1, critic_current_edge.repeat(1, 1, 2)))

    def save_action(self, action_index):
        # action_index 形状统一成 [1,1,1]，后续 batch 可直接 stack。
        self.episode_buffer[6] += action_index.reshape(1, 1, 1)

    def save_reward_done(self, reward, done):
        # done 存成 0/1，便于 target_q 中计算 (1-done)。
        self.episode_buffer[7] += torch.FloatTensor([reward]).reshape(1, 1, 1).to(self.device)
        self.episode_buffer[8] += torch.tensor([int(done)]).reshape(1, 1, 1).to(self.device)

    def save_next_observations(self, observation, ground_truth_observation):
        # 保存下一时刻 s_{t+1}（policy 与 critic 两套图输入）。
        node_inputs, node_padding_mask, edge_mask, current_index, current_edge, edge_padding_mask = observation
        self.episode_buffer[9] += node_inputs
        self.episode_buffer[10] += node_padding_mask.bool()
        self.episode_buffer[11] += edge_mask.bool()
        self.episode_buffer[12] += current_index
        self.episode_buffer[13] += current_edge
        self.episode_buffer[14] += edge_padding_mask.bool()

        critic_node_inputs, critic_node_padding_mask, critic_edge_mask, critic_current_index, critic_current_edge, critic_edge_padding_mask = ground_truth_observation
        self.episode_buffer[21] += critic_node_inputs
        self.episode_buffer[22] += critic_node_padding_mask.bool()
        self.episode_buffer[23] += critic_edge_mask.bool()
        self.episode_buffer[24] += critic_current_index
        self.episode_buffer[25] += critic_current_edge
        self.episode_buffer[26] += critic_edge_padding_mask.bool()

if __name__ == "__main__":
    torch.manual_seed(4777)
    np.random.seed(4777)
    model = PolicyNet(NODE_INPUT_DIM, EMBEDDING_DIM)
    # 调试续训时可取消注释：
    # 示例：checkpoint = torch.load(model_path + '/checkpoint.pth', map_location='cpu')
    # 示例：model.load_state_dict(checkpoint['policy_model'])
    worker = Worker(0, model, 77, save_image=False)
    worker.run_episode()
