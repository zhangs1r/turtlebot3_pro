import torch
import ray
from model import PolicyNet
from worker import Worker
from parameter import *

"""Runner（Ray Actor）职责：
1. 持有一份本地策略网络（用于采样动作）。
2. 每次任务开始前从 driver 同步最新权重。
3. 调用 Worker 跑完整 episode，返回回放数据与性能指标。
"""


class Runner(object):
    # 一个 Runner 对应一个 Ray Actor。
    # 它维护一份本地策略网络参数，从 driver 拉取最新权重后，
    # 交给 Worker 跑完整一回合并返回采样数据。
    def __init__(self, meta_agent_id):
        self.meta_agent_id = meta_agent_id
        self.device = torch.device('cuda') if USE_GPU else torch.device('cpu')
        self.network = PolicyNet(NODE_INPUT_DIM, EMBEDDING_DIM)
        self.network.to(self.device)

    def get_weights(self):
        # 便于调试：查看当前 actor 上的模型参数。
        return self.network.state_dict()

    def set_policy_net_weights(self, weights):
        # 将 driver 下发的全局策略参数覆盖到本地网络。
        self.network.load_state_dict(weights)

    def do_job(self, episode_number):
        save_img = True if episode_number % SAVE_IMG_GAP == 0 else False
        # 调试时可强制打开：save_img = True
        # Worker 会把转移数据打包到固定 27 槽位的回放结构。
        worker = Worker(self.meta_agent_id, self.network, episode_number, device=self.device, save_image=save_img)
        worker.run_episode()

        job_results = worker.episode_buffer
        perf_metrics = worker.perf_metrics
        return job_results, perf_metrics

    def job(self, weights_set, episode_number):
        # 仅在主 actor 周期性打印，避免多 actor 日志刷屏。
        if self.meta_agent_id == 0 and episode_number % SUMMARY_WINDOW == 0:
            print(f"[Runner] dispatch episode {episode_number} (metaAgent={self.meta_agent_id})")
        # 开始采样前先同步最新全局策略参数。
        self.set_policy_net_weights(weights_set[0])

        job_results, metrics = self.do_job(episode_number)

        info = {"id": self.meta_agent_id, "episode_number": episode_number}

        return job_results, metrics, info


@ray.remote(num_cpus=1, num_gpus=NUM_GPU / NUM_META_AGENT)
class RLRunner(Runner):
    def __init__(self, meta_agent_id):
        super().__init__(meta_agent_id)


if __name__ == '__main__':
    ray.init()
    runner = RLRunner.remote(0)
    job_id = runner.do_job.remote(1)
    out = ray.get(job_id)
    print(out[1])
