# 训练配置集中管理文件。
# 新手可以把它当成项目的“总控制面板”。

# 保存路径
FOLDER_NAME = 'ariadne1_ground_truth_critic'
model_path = f'model/{FOLDER_NAME}'
train_path = f'train/{FOLDER_NAME}'
gifs_path = f'gifs/{FOLDER_NAME}'

# 训练数据记录
# SUMMARY_WINDOW：每隔多少次训练迭代做一次平均并写日志。
SUMMARY_WINDOW = 8  # 窗口设小一些，便于更快看到统计结果
LOAD_MODEL = True  # 是否加载之前训练好的模型继续训练
SAVE_IMG_GAP = 100000  # 设得很大，默认基本不画图，避免拖慢长训练

# 地图与规划分辨率
CELL_SIZE = 0.4  # 米，栅格地图分辨率
NODE_RESOLUTION = 4.0  # 米，图节点分辨率
FRONTIER_CELL_SIZE = 2 * CELL_SIZE  # 前沿点下采样分辨率

# 地图语义值定义
FREE = 255  # 可通行栅格值
OCCUPIED = 1  # 障碍栅格值
UNKNOWN = 127  # 未知栅格值

# 传感器与效用范围（与 A2M12/Nav2/Cartographer 的 12m 工作范围保持一致）
SENSOR_RANGE = 12  # 米
UTILITY_RANGE = 0.8 * SENSOR_RANGE  # 该范围内前沿点可被认为“可观测”
MIN_UTILITY = 2  # 若可观测前沿点少于该值，则效用记为 0

# 机器人当前位置附近的局部更新窗口大小
UPDATING_MAP_SIZE = 4 * SENSOR_RANGE + 4 * NODE_RESOLUTION  # 窗口外节点默认不受当前观测影响

# 训练超参数
# MAX_EPISODE_STEP：单回合最多动作数，超过后强制结束。
MAX_EPISODE_STEP = 128
# REPLAY_SIZE：回放缓冲区上限，超出后丢弃更早样本。
REPLAY_SIZE = 4000
# MINIMUM_BUFFER_SIZE：开始梯度更新前的预热样本量阈值。
MINIMUM_BUFFER_SIZE = 1024
# BATCH_SIZE：每次参数更新从回放池采样的转移数量。
BATCH_SIZE = 128
LR = 1e-5
GAMMA = 1
NUM_META_AGENT = 6  # WSL 下较稳妥的默认并行数（若 OOM 可继续减小）

# 网络参数
NODE_INPUT_DIM = 4
EMBEDDING_DIM = 128

# 图结构参数
# K_SIZE：动作维度（邻居候选数量）补齐后的固定长度上限。
K_SIZE = 25  # 固定的邻居候选上限
# NODE_PADDING_SIZE：节点数补齐到该长度，方便批量张量运算。
NODE_PADDING_SIZE = 360  # 训练时节点序列会 pad 到这个大小

# GPU 使用设置
USE_GPU = False  # 是否让采样端用 GPU（通常不建议）
USE_GPU_GLOBAL = True  # 是否让全局学习器用 GPU
NUM_GPU = 0  # 若采样端不使用 GPU，这里保持 0
