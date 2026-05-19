# 训练代码阅读顺序（Python 新手版）

这份顺序按“先看全局，再看细节”的思路安排。  
建议你一边读一边画流程图，先理解数据怎么流动，再抠网络细节。

## 第 0 步：先知道项目在做什么

1. `parameter.py`  
看所有超参数、路径、地图语义值（`FREE/OCCUPIED/UNKNOWN`）。

2. `README_TRAINING.md`  
知道怎么训练、日志输出在哪里、如何看曲线。

## 第 1 步：先跑通训练主流程（不深究网络）

1. `driver.py`  
主训练循环：收集样本 -> 采样 batch -> 算 loss -> 更新参数 -> 写日志。

2. `runner.py`  
Ray actor 包装层：每个 runner 拉取最新策略，然后调用 worker 跑一回合。

3. `worker.py`  
单回合采样逻辑最关键：保存 `s/a/r/s'` 到固定 27 槽位回放结构。

## 第 2 步：看环境与状态是怎么来的

1. `env.py`  
环境如何更新机器人位置、传感观测、奖励和探索率。

2. `sensor.py`  
雷达式射线扫描（Bresenham）如何把真值地图写入 belief 地图。

3. `utils.py`  
坐标变换、frontier 提取、连通区域筛选、碰撞检测等基础工具。

## 第 3 步：看图结构怎么维护

1. `node_manager.py`  
belief 图上的节点增删改查、utility 更新、邻接关系维护、A*/Dijkstra。

2. `ground_truth_node_manager.py`  
训练技巧：critic 用 ground-truth 图（特权信息），policy 仍只用 belief 图。

## 第 4 步：最后读神经网络（最难）

1. `model.py`  
`PolicyNet` 与 `QNet`：图编码（Transformer）+ 当前节点解码 + 邻居动作头。

重点先看这三个函数：
- `PolicyNet.forward`
- `QNet.forward`
- `SingleHeadAttention.forward`

## 第 5 步：训练过程可视化

1. `plot_progress.py`  
读取 `progress.csv`，画 reward / success_rate / loss / 显存曲线。

## 可后读（先跳过也没事）

1. `quads.py`  
这是 QuadTree 数据结构实现，服务于节点快速查找。  
新手第一轮可先不读，等你理解 `node_manager.py` 后再回来看。

