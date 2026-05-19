import torch
import torch.optim as optim
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
import ray
import os
import numpy as np
import random
import csv
import time

from model import PolicyNet, QNet
from runner import RLRunner
from parameter import *

"""driver.py 是分布式训练主入口（学习器）：
1. 持有全局 policy / twin-Q / target-Q 网络与优化器。
2. 通过 Ray 启动多个 runner 并行采样（rollout）。
3. 聚合回放数据并执行 SAC 更新。
4. 记录 TensorBoard、CSV 训练曲线并定期保存 checkpoint。
"""

if not os.path.exists(train_path):
    os.makedirs(train_path)
writer = SummaryWriter(train_path)
if not os.path.exists(model_path):
    os.makedirs(model_path)
if not os.path.exists(gifs_path):
    os.makedirs(gifs_path)
progress_csv_path = os.path.join(train_path, "progress.csv")


def _init_progress_csv(path):
    # 轻量 CSV，便于训练中 `tail -f` 实时观察趋势。
    if os.path.exists(path):
        return
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "episode",
                "updates",
                "replay_size",
                "elapsed_sec",
                "reward",
                "value",
                "policy_loss",
                "q_value_loss",
                "entropy",
                "policy_grad_norm",
                "q_value_grad_norm",
                "log_alpha",
                "alpha_loss",
                "travel_dist",
                "success_rate",
                "explored_rate",
                "gpu_mem_alloc_gb",
                "gpu_mem_reserved_gb",
            ]
        )


def _gpu_mem_gb():
    # 返回当前进程的 GPU 已分配/已保留显存（GB）。
    if not torch.cuda.is_available():
        return 0.0, 0.0
    allocated = torch.cuda.memory_allocated() / (1024 ** 3)
    reserved = torch.cuda.memory_reserved() / (1024 ** 3)
    return allocated, reserved


def _append_progress_csv(path, row):
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow(row)


def main():
    print("Welcome to RL autonomous exploration!")
    ray.init()
    _init_progress_csv(progress_csv_path)
    start_time = time.time()

    # driver 与 worker 的设备可分开配置：
    # - device: 学习器（参数更新）
    # - local_device: rollout 采样端（Runner/Worker）
    cuda_available = torch.cuda.is_available()
    if USE_GPU_GLOBAL and cuda_available:
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')

    if USE_GPU and cuda_available:
        local_device = torch.device('cuda')
    else:
        local_device = torch.device('cpu')

    print(
        f"[Device] torch.cuda.is_available={cuda_available}, "
        f"torch.cuda.device_count={torch.cuda.device_count()}"
    )
    if device.type == 'cuda':
        print(f"[Device] Global learner uses GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("[Device] Global learner uses CPU")
    if local_device.type == 'cuda':
        print("[Device] Rollout workers use GPU")
    else:
        print("[Device] Rollout workers use CPU")
    print(
        f"[Warmup] replay >= {MINIMUM_BUFFER_SIZE} required before gradient updates. "
        "Before that, you mostly see CPU data collection."
    )
    print(f"[TensorBoard] tensorboard --logdir {train_path} --port 6006")
    print(f"[ProgressCSV] {progress_csv_path}")

    # 初始化网络：
    # - policy: 输出每个候选动作的 log-prob
    # - q_net1/q_net2: twin critic，缓解 Q 过估计
    # - target_q: 计算 TD 目标时使用的慢更新网络
    global_policy_net = PolicyNet(NODE_INPUT_DIM, EMBEDDING_DIM).to(device)
    global_q_net1 = QNet(NODE_INPUT_DIM + 1, EMBEDDING_DIM).to(device)
    global_q_net2 = QNet(NODE_INPUT_DIM + 1, EMBEDDING_DIM).to(device)
    log_alpha = torch.FloatTensor([-2]).to(device)
    log_alpha.requires_grad = True

    global_target_q_net1 = QNet(NODE_INPUT_DIM + 1, EMBEDDING_DIM).to(device)
    global_target_q_net2 = QNet(NODE_INPUT_DIM + 1, EMBEDDING_DIM).to(device)

    # 初始化优化器（策略/Q/温度参数 alpha 分开优化）。
    global_policy_optimizer = optim.Adam(global_policy_net.parameters(), lr=LR)
    global_q_net1_optimizer = optim.Adam(global_q_net1.parameters(), lr=LR)
    global_q_net2_optimizer = optim.Adam(global_q_net2.parameters(), lr=LR)
    log_alpha_optimizer = optim.Adam([log_alpha], lr=1e-4)

    # SAC 目标熵：控制探索强度（alpha 会自动调节接近该目标）。
    entropy_target = 0.05 * (-np.log(1 / K_SIZE))

    curr_episode = 0
    target_q_update_counter = 1

    # 可选：加载历史 checkpoint 继续训练。
    if LOAD_MODEL:
        print('Loading Model...')
        checkpoint = torch.load(model_path + '/checkpoint.pth', map_location=device)
        global_policy_net.load_state_dict(checkpoint['policy_model'])
        global_q_net1.load_state_dict(checkpoint['q_net1_model'])
        global_q_net2.load_state_dict(checkpoint['q_net2_model'])
        log_alpha = checkpoint['log_alpha']
        log_alpha = checkpoint['log_alpha']
        log_alpha_optimizer = optim.Adam([log_alpha], lr=1e-4)

        global_policy_optimizer.load_state_dict(checkpoint['policy_optimizer'])
        global_q_net1_optimizer.load_state_dict(checkpoint['q_net1_optimizer'])
        global_q_net2_optimizer.load_state_dict(checkpoint['q_net2_optimizer'])
        log_alpha_optimizer.load_state_dict(checkpoint['log_alpha_optimizer'])
        curr_episode = checkpoint['episode']

        print("curr_episode set to ", curr_episode)
        print(log_alpha, log_alpha.requires_grad)
        print(global_policy_optimizer.state_dict()['param_groups'][0]['lr'])

    global_target_q_net1.load_state_dict(global_q_net1.state_dict())
    global_target_q_net2.load_state_dict(global_q_net2.state_dict())
    global_target_q_net1.eval()
    global_target_q_net2.eval()

    # 启动并行采样 actor。
    meta_agents = [RLRunner.remote(i) for i in range(NUM_META_AGENT)]

    # 下发策略权重（worker 只需要 policy，不需要 Q 网络参数）。
    weights_set = []
    if device != local_device:
        policy_weights = global_policy_net.to(local_device).state_dict()
        global_policy_net.to(device)
    else:
        policy_weights = global_policy_net.state_dict()
    weights_set.append(policy_weights)

    # DataParallel：即便单卡也可正常工作，多卡时自动切分 batch。
    dp_policy = nn.DataParallel(global_policy_net)
    dp_q_net1 = nn.DataParallel(global_q_net1)
    dp_q_net2 = nn.DataParallel(global_q_net2)
    dp_target_q_net1 = nn.DataParallel(global_target_q_net1)
    dp_target_q_net2 = nn.DataParallel(global_target_q_net2)

    # 为每个 runner 先投递一个 episode 任务。
    job_list = []
    for i, meta_agent in enumerate(meta_agents):
        curr_episode += 1
        job_list.append(meta_agent.job.remote(weights_set, curr_episode))

    # 初始化性能统计容器。
    metric_name = ['travel_dist', 'success_rate', 'explored_rate']
    training_data = []
    perf_metrics = {}
    for n in metric_name:
        perf_metrics[n] = []

    # 初始化回放池（replay buffer）。
    # 槽位布局（固定 27 个列表，与 worker.py 保持一致）：
    # 0-14: policy 的 s/a/r/s'
    # 15-26: critic 的 s/s'（ground-truth 图观测）
    experience_buffer = []
    for i in range(27):
        experience_buffer.append([])
    printed_training_start = False
    n_updates = 0

    # 主循环：异步收集 rollout + 同步进行梯度更新。
    try:
        while True:
            # 等任意一个 worker 完成（异步并行）。
            done_id, job_list = ray.wait(job_list)
            # 取回采样结果。
            done_jobs = ray.get(done_id)

            # 合并经验与性能指标。
            for job in done_jobs:
                job_results, metrics, info = job
                for i in range(len(experience_buffer)):
                    experience_buffer[i] += job_results[i]
                for n in metric_name:
                    perf_metrics[n].append(metrics[n])
            buffer_size = len(experience_buffer[0])
            for i in range(len(experience_buffer)):
                assert len(experience_buffer[i]) == buffer_size

            # 立即给刚完成的 actor 派发下一回合任务，保持流水线满载。
            curr_episode += 1
            job_list.append(meta_agents[info['id']].job.remote(weights_set, curr_episode))

            # 达到 warmup 阈值后才开始参数更新。
            if curr_episode % 1 == 0 and len(experience_buffer[0]) >= MINIMUM_BUFFER_SIZE:
                if not printed_training_start:
                    print(
                        f"[TrainStart] episode={curr_episode}, replay={len(experience_buffer[0])}, "
                        f"device={device}"
                    )
                    printed_training_start = True

                # 控制 replay 上限，避免显存/内存持续增长。
                if len(experience_buffer[0]) >= REPLAY_SIZE:
                    for i in range(len(experience_buffer)):
                        experience_buffer[i] = experience_buffer[i][-REPLAY_SIZE:]

                indices = range(len(experience_buffer[0]))

                # 每次采样完成后做多步梯度更新（提升样本利用率）。
                for j in range(8):
                    # 随机采样 batch（打散相关性）。
                    sample_indices = random.sample(indices, BATCH_SIZE)
                    rollouts = []
                    for i in range(len(experience_buffer)):
                        rollouts.append([experience_buffer[i][index] for index in sample_indices])

                    # 组装批量张量。
                    # 张量形状约定统一为 [B, ...]，其中 B = BATCH_SIZE。
                    node_inputs = torch.stack(rollouts[0]).to(device)
                    node_padding_mask = torch.stack(rollouts[1]).to(device)
                    edge_mask = torch.stack(rollouts[2]).to(device)
                    current_index = torch.stack(rollouts[3]).to(device)
                    current_edge = torch.stack(rollouts[4]).to(device)
                    edge_padding_mask = torch.stack(rollouts[5]).to(device)
                    action = torch.stack(rollouts[6]).to(device)
                    reward = torch.stack(rollouts[7]).to(device)
                    done = torch.stack(rollouts[8]).to(device)
                    next_node_inputs = torch.stack(rollouts[9]).to(device)
                    next_node_padding_mask = torch.stack(rollouts[10]).to(device)
                    next_edge_mask = torch.stack(rollouts[11]).to(device)
                    next_current_index = torch.stack(rollouts[12]).to(device)
                    next_current_edge = torch.stack(rollouts[13]).to(device)
                    next_edge_padding_mask = torch.stack(rollouts[14]).to(device)

                    critic_node_inputs = torch.stack(rollouts[15]).to(device)
                    critic_node_padding_mask = torch.stack(rollouts[16]).to(device)
                    critic_edge_mask = torch.stack(rollouts[17]).to(device)
                    critic_current_index = torch.stack(rollouts[18]).to(device)
                    critic_current_edge = torch.stack(rollouts[19]).to(device)
                    critic_edge_padding_mask = torch.stack(rollouts[20]).to(device)
                    critic_next_node_inputs = torch.stack(rollouts[21]).to(device)
                    critic_next_node_padding_mask = torch.stack(rollouts[22]).to(device)
                    critic_next_edge_mask = torch.stack(rollouts[23]).to(device)
                    critic_next_current_index = torch.stack(rollouts[24]).to(device)
                    critic_next_current_edge = torch.stack(rollouts[25]).to(device)
                    critic_next_edge_padding_mask = torch.stack(rollouts[26]).to(device)

                    observation = [node_inputs, node_padding_mask, edge_mask, current_index,
                                   current_edge, edge_padding_mask]
                    next_observation = [next_node_inputs, next_node_padding_mask, next_edge_mask,
                                        next_current_index, next_current_edge, next_edge_padding_mask]

                    critic_observation = [critic_node_inputs, critic_node_padding_mask, critic_edge_mask,
                                          critic_current_index,
                                          critic_current_edge, critic_edge_padding_mask]
                    critic_next_observation = [critic_next_node_inputs, critic_next_node_padding_mask,
                                               critic_next_edge_mask,
                                               critic_next_current_index, critic_next_current_edge,
                                               critic_next_edge_padding_mask]

                    # SAC-Policy 更新：
                    # 使用 min(Q1,Q2) 估计策略目标，降低过估计。
                    with torch.no_grad():
                        q_values1 = dp_q_net1(*critic_observation)
                        q_values2 = dp_q_net2(*critic_observation)
                        q_values = torch.min(q_values1, q_values2)

                    logp = dp_policy(*observation)
                    policy_loss = torch.sum(
                        (logp.exp().unsqueeze(2) * (log_alpha.exp().detach() * logp.unsqueeze(2) - q_values.detach())),
                        dim=1).mean()

                    global_policy_optimizer.zero_grad()
                    policy_loss.backward()
                    policy_grad_norm = torch.nn.utils.clip_grad_norm_(global_policy_net.parameters(), max_norm=100,
                                                                      norm_type=2)
                    global_policy_optimizer.step()

                    # 计算 Q 的 bootstrap 目标：
                    # 公式：target_q = r + gamma * (1-done) * V(s')
                    with torch.no_grad():
                        next_logp = dp_policy(*next_observation)
                        next_q_values1 = dp_target_q_net1(*critic_next_observation)
                        next_q_values2 = dp_target_q_net2(*critic_next_observation)
                        next_q_values = torch.min(next_q_values1, next_q_values2)
                        value_prime = torch.sum(
                            next_logp.unsqueeze(2).exp() * (next_q_values - log_alpha.exp() * next_logp.unsqueeze(2)),
                            dim=1).unsqueeze(1)
                        target_q = reward + GAMMA * (1 - done) * value_prime

                    mse_loss = nn.MSELoss()

                    q_values1 = dp_q_net1(*critic_observation)
                    q1 = torch.gather(q_values1, 1, action)
                    q1_loss = mse_loss(q1, target_q.detach()).mean()

                    global_q_net1_optimizer.zero_grad()
                    q1_loss.backward()
                    q_grad_norm = torch.nn.utils.clip_grad_norm_(global_q_net1.parameters(), max_norm=20000,
                                                                 norm_type=2)
                    global_q_net1_optimizer.step()

                    q_values2 = dp_q_net2(*critic_observation)
                    q2 = torch.gather(q_values2, 1, action)
                    q2_loss = mse_loss(q2, target_q.detach()).mean()

                    global_q_net2_optimizer.zero_grad()
                    q2_loss.backward()
                    q_grad_norm = torch.nn.utils.clip_grad_norm_(global_q_net2.parameters(), max_norm=20000,
                                                                 norm_type=2)
                    global_q_net2_optimizer.step()

                    # 温度系数 alpha 自适应更新：
                    # 熵偏小 -> 增大 alpha（鼓励探索）；熵偏大 -> 减小 alpha。
                    entropy = (logp * logp.exp()).sum(dim=-1)
                    alpha_loss = -(log_alpha * (entropy.detach() + entropy_target)).mean()

                    log_alpha_optimizer.zero_grad()
                    alpha_loss.backward()
                    log_alpha_optimizer.step()
                    n_updates += 1

                    target_q_update_counter += 1
                    # 调试用：打印 target-Q 同步计数器

                # 收集一组可写入日志的标量。
                perf_data = []
                for n in metric_name:
                    perf_data.append(np.nanmean(perf_metrics[n]))
                data = [reward.mean().item(), value_prime.mean().item(), policy_loss.item(), q1_loss.item(),
                        entropy.mean().item(), policy_grad_norm.item(), q_grad_norm.item(), log_alpha.item(),
                        alpha_loss.item(), *perf_data]
                training_data.append(data)
                # 每轮更新都写一条 CSV，便于外部工具实时监控。
                elapsed = time.time() - start_time
                gpu_alloc_gb, gpu_reserved_gb = _gpu_mem_gb()
                replay_size = len(experience_buffer[0])
                _append_progress_csv(
                    progress_csv_path,
                    [
                        curr_episode,
                        n_updates,
                        replay_size,
                        round(elapsed, 3),
                        data[0],   # reward
                        data[1],   # value
                        data[2],   # policy_loss
                        data[3],   # q_value_loss
                        data[4],   # entropy
                        data[5],   # policy_grad_norm
                        data[6],   # q_value_grad_norm
                        data[7],   # log_alpha
                        data[8],   # alpha_loss
                        data[9],   # travel_dist
                        data[10],  # success_rate
                        data[11],  # explored_rate
                        round(gpu_alloc_gb, 6),
                        round(gpu_reserved_gb, 6),
                    ],
                )

            # 到达 SUMMARY_WINDOW 后，对窗口内数据取均值写 TensorBoard。
            if len(training_data) >= SUMMARY_WINDOW:
                summary = write_to_tensor_board(writer, training_data, curr_episode)
                elapsed = time.time() - start_time
                gpu_alloc_gb, gpu_reserved_gb = _gpu_mem_gb()
                replay_size = len(experience_buffer[0])
                print(
                    "[Summary] "
                    f"ep={curr_episode} upd={n_updates} replay={replay_size} "
                    f"reward={summary['reward']:.3f} succ={summary['success_rate']:.3f} "
                    f"explore={summary['explored_rate']:.3f} dist={summary['travel_dist']:.2f} "
                    f"policy={summary['policy_loss']:.4f} q={summary['q_value_loss']:.4f} "
                    f"entropy={summary['entropy']:.4f} alpha={summary['log_alpha']:.4f} "
                    f"gpu_mem={gpu_alloc_gb:.2f}/{gpu_reserved_gb:.2f}GB "
                    f"elapsed={elapsed/60.0:.1f}m"
                )
                training_data = []
                perf_metrics = {}
                for n in metric_name:
                    perf_metrics[n] = []

            # 下发最新策略参数给后续 rollout。
            weights_set = []
            if device != local_device:
                policy_weights = global_policy_net.to(local_device).state_dict()
                global_policy_net.to(device)
            else:
                policy_weights = global_policy_net.state_dict()
            weights_set.append(policy_weights)

            # 周期性同步 target-Q（稳定 TD 目标）。
            if target_q_update_counter > 64:
                print("update target q net")
                target_q_update_counter = 1
                global_target_q_net1.load_state_dict(global_q_net1.state_dict())
                global_target_q_net2.load_state_dict(global_q_net2.state_dict())
                global_target_q_net1.eval()
                global_target_q_net2.eval()

            # 定期保存 checkpoint，支持断点续训。
            if curr_episode % 32 == 0:
                print(f"[Checkpoint] saving at episode {curr_episode}")
                checkpoint = {"policy_model": global_policy_net.state_dict(),
                              "q_net1_model": global_q_net1.state_dict(),
                              "q_net2_model": global_q_net2.state_dict(),
                              "log_alpha": log_alpha,
                              "policy_optimizer": global_policy_optimizer.state_dict(),
                              "q_net1_optimizer": global_q_net1_optimizer.state_dict(),
                              "q_net2_optimizer": global_q_net2_optimizer.state_dict(),
                              "log_alpha_optimizer": log_alpha_optimizer.state_dict(),
                              "episode": curr_episode,
                              }
                path_checkpoint = "./" + model_path + "/checkpoint.pth"
                torch.save(checkpoint, path_checkpoint)
                print(f"[Checkpoint] saved -> {path_checkpoint}")

    except KeyboardInterrupt:
        print("CTRL_C pressed. Killing remote workers")
        for a in meta_agents:
            ray.kill(a)


def write_to_tensor_board(writer, tensorboard_data, curr_episode):
    # 输入是窗口内多条记录，先按列求均值，再写入各指标曲线。

    tensorboard_data = np.array(tensorboard_data)
    tensorboard_data = list(np.nanmean(tensorboard_data, axis=0))
    reward, value, policy_loss, q_value_loss, entropy, policy_grad_norm, q_value_grad_norm, log_alpha, alpha_loss, travel_dist, success_rate, explored_rate = tensorboard_data

    writer.add_scalar(tag='Losses/Value', scalar_value=value, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Policy Loss', scalar_value=policy_loss, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Alpha Loss', scalar_value=alpha_loss, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Q Value Loss', scalar_value=q_value_loss, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Entropy', scalar_value=entropy, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Policy Grad Norm', scalar_value=policy_grad_norm, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Q Value Grad Norm', scalar_value=q_value_grad_norm, global_step=curr_episode)
    writer.add_scalar(tag='Losses/Log Alpha', scalar_value=log_alpha, global_step=curr_episode)
    writer.add_scalar(tag='Perf/Reward', scalar_value=reward, global_step=curr_episode)
    writer.add_scalar(tag='Perf/Travel Distance', scalar_value=travel_dist, global_step=curr_episode)
    writer.add_scalar(tag='Perf/Explored Rate', scalar_value=explored_rate, global_step=curr_episode)
    writer.add_scalar(tag='Perf/Success Rate', scalar_value=success_rate, global_step=curr_episode)

    return {
        "reward": reward,
        "value": value,
        "policy_loss": policy_loss,
        "q_value_loss": q_value_loss,
        "entropy": entropy,
        "policy_grad_norm": policy_grad_norm,
        "q_value_grad_norm": q_value_grad_norm,
        "log_alpha": log_alpha,
        "alpha_loss": alpha_loss,
        "travel_dist": travel_dist,
        "success_rate": success_rate,
        "explored_rate": explored_rate,
    }


if __name__ == "__main__":
    main()
