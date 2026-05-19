import torch
import torch.nn as nn
import math

"""模型文件（Graph-Transformer + Pointer）：
- PolicyNet: 输出候选邻居动作的 log-prob（用于采样策略）。
- QNet: 输出每个候选动作的 Q(s,a)（用于 SAC 的 critic）。
两者共享“图编码 -> 当前节点解码”的主干思想，区别在最后输出头。
"""


# 单头 pointer 注意力：给当前状态对一组候选邻居打分（log-softmax）。
class SingleHeadAttention(nn.Module):
    """单头注意力打分器（Pointer Head）。

    输入“当前节点状态”与“候选邻居特征”，输出每个候选动作的对数概率。
    """
    def __init__(self, embedding_dim):
        super(SingleHeadAttention, self).__init__()
        self.input_dim = embedding_dim
        self.embedding_dim = embedding_dim
        self.value_dim = embedding_dim
        self.key_dim = self.value_dim
        self.tanh_clipping = 10
        self.norm_factor = 1 / math.sqrt(self.key_dim)

        self.w_query = nn.Parameter(torch.Tensor(self.input_dim, self.key_dim))
        self.w_key = nn.Parameter(torch.Tensor(self.input_dim, self.key_dim))

        self.init_parameters()

    def init_parameters(self):
        for param in self.parameters():
            stdv = 1. / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    def forward(self, q, k, mask=None):
        # q: [B, 1, D] 当前状态特征
        # k: [B, K, D] 候选动作（邻居）特征
        # 返回: [B, 1, K] 的对数概率

        n_batch, n_key, n_dim = k.size()
        n_query = q.size(1)

        k_flat = k.reshape(-1, n_dim)
        q_flat = q.reshape(-1, n_dim)

        shape_k = (n_batch, n_key, -1)
        shape_q = (n_batch, n_query, -1)

        Q = torch.matmul(q_flat, self.w_query).view(shape_q)
        K = torch.matmul(k_flat, self.w_key).view(shape_k)

        U = self.norm_factor * torch.matmul(Q, K.transpose(1, 2))
        U = self.tanh_clipping * torch.tanh(U)

        if mask is not None:
            U = U.masked_fill(mask == 1, -1e8)
        attention = torch.log_softmax(U, dim=-1)  # n_batch*n_query*n_key

        return attention


# 标准多头注意力，用于图节点之间的信息传播。
class MultiHeadAttention(nn.Module):
    """标准多头注意力模块。

    这里既可做 self-attention（q=k=v），也可做 cross-attention（q 与 k/v 不同）。
    """
    def __init__(self, embedding_dim, n_heads=8):
        super(MultiHeadAttention, self).__init__()
        self.n_heads = n_heads
        self.input_dim = embedding_dim
        self.embedding_dim = embedding_dim
        self.value_dim = self.embedding_dim // self.n_heads
        self.key_dim = self.value_dim
        self.norm_factor = 1 / math.sqrt(self.key_dim)

        self.w_query = nn.Parameter(torch.Tensor(self.n_heads, self.input_dim, self.key_dim))
        self.w_key = nn.Parameter(torch.Tensor(self.n_heads, self.input_dim, self.key_dim))
        self.w_value = nn.Parameter(torch.Tensor(self.n_heads, self.input_dim, self.value_dim))
        self.w_out = nn.Parameter(torch.Tensor(self.n_heads, self.value_dim, self.embedding_dim))

        self.init_parameters()

    def init_parameters(self):
        for param in self.parameters():
            stdv = 1. / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    def forward(self, q, k=None, v=None, key_padding_mask=None, attn_mask=None):
        if k is None:
            k = q
        if v is None:
            v = q

        n_batch, n_key, n_dim = k.size()
        n_query = q.size(1)
        n_value = v.size(1)

        k_flat = k.contiguous().view(-1, n_dim)
        v_flat = v.contiguous().view(-1, n_dim)
        q_flat = q.contiguous().view(-1, n_dim)
        shape_v = (self.n_heads, n_batch, n_value, -1)
        shape_k = (self.n_heads, n_batch, n_key, -1)
        shape_q = (self.n_heads, n_batch, n_query, -1)

        # Q/K/V 形状：
        # [n_heads, batch_size, 序列长度, 每头维度]
        Q = torch.matmul(q_flat, self.w_query).view(shape_q)
        K = torch.matmul(k_flat, self.w_key).view(shape_k)
        V = torch.matmul(v_flat, self.w_value).view(shape_v)

        # 注意力打分矩阵 U：
        # 形状：[n_heads, batch_size, n_query, n_key]
        U = self.norm_factor * torch.matmul(Q, K.transpose(2, 3))

        if attn_mask is not None:
            attn_mask = attn_mask.view(1, n_batch, n_query, n_key).expand_as(U)

        if key_padding_mask is not None:
            key_padding_mask = key_padding_mask.repeat(1, n_query, 1)
            # key padding mask 在 head 维复制一次，便于与 U 对齐。
            key_padding_mask = key_padding_mask.view(1, n_batch, n_query, n_key).expand_as(U)

        if attn_mask is not None and key_padding_mask is not None:
            mask = (attn_mask + key_padding_mask)
        elif attn_mask is not None:
            mask = attn_mask
        elif key_padding_mask is not None:
            mask = key_padding_mask
        else:
            mask = None

        if mask is not None:
            U = U.masked_fill(mask > 0, -1e8)

        attention = torch.softmax(U, dim=-1)

        heads = torch.matmul(attention, V)

        # 旧写法参考：out = heads.permute(1, 2, 0, 3).reshape(n_batch, n_query, n_dim)
        out = torch.mm(
            heads.permute(1, 2, 0, 3).reshape(-1, self.n_heads * self.value_dim),
            # 先把多头结果拼到一起：[batch_size*n_query, n_heads*value_dim]
            self.w_out.view(-1, self.embedding_dim)
            # 投影矩阵展平后做一次矩阵乘法
        ).view(-1, n_query, self.embedding_dim)

        return out, attention


class Normalization(nn.Module):
    """对最后一维做 LayerNorm，并保持输入形状不变。"""
    def __init__(self, embedding_dim):
        super(Normalization, self).__init__()
        self.normalizer = nn.LayerNorm(embedding_dim)

    def forward(self, input):
        return self.normalizer(input.view(-1, input.size(-1))).view(*input.size())


class EncoderLayer(nn.Module):
    """Transformer 编码层：Pre-LN -> 自注意力 -> 残差 -> 前馈 -> 残差。"""
    def __init__(self, embedding_dim, n_head):
        super(EncoderLayer, self).__init__()
        self.multiHeadAttention = MultiHeadAttention(embedding_dim, n_head)
        self.normalization1 = Normalization(embedding_dim)
        self.feedForward = nn.Sequential(nn.Linear(embedding_dim, 512), nn.ReLU(inplace=True),
                                         nn.Linear(512, embedding_dim))
        self.normalization2 = Normalization(embedding_dim)

    def forward(self, src, key_padding_mask=None, attn_mask=None):
        # Pre-LN + 残差结构。
        h0 = src
        h = self.normalization1(src)
        h, _ = self.multiHeadAttention(q=h, key_padding_mask=key_padding_mask, attn_mask=attn_mask)
        h = h + h0
        h1 = h
        h = self.normalization2(h)
        h = self.feedForward(h)
        h2 = h + h1
        return h2


class DecoderLayer(nn.Module):
    """Transformer 解码层：当前节点查询整图 memory（cross-attention）。"""
    def __init__(self, embedding_dim, n_head):
        super(DecoderLayer, self).__init__()
        self.multiHeadAttention = MultiHeadAttention(embedding_dim, n_head)
        self.normalization1 = Normalization(embedding_dim)
        self.feedForward = nn.Sequential(nn.Linear(embedding_dim, 512),
                                         nn.ReLU(inplace=True),
                                         nn.Linear(512, embedding_dim))
        self.normalization2 = Normalization(embedding_dim)

    def forward(self, tgt, memory, key_padding_mask=None, attn_mask=None):
        # 这里是 cross-attention：tgt(当前节点) 查询 memory(整图特征)。
        h0 = tgt
        tgt = self.normalization1(tgt)
        memory = self.normalization1(memory)
        h, w = self.multiHeadAttention(q=tgt, k=memory, v=memory, key_padding_mask=key_padding_mask,
                                       attn_mask=attn_mask)
        h = h + h0
        h1 = h
        h = self.normalization2(h)
        h = self.feedForward(h)
        h2 = h + h1
        return h2, w


class Encoder(nn.Module):
    """由多层 EncoderLayer 堆叠而成。"""
    def __init__(self, embedding_dim=128, n_head=8, n_layer=1):
        super(Encoder, self).__init__()
        self.layers = nn.ModuleList(EncoderLayer(embedding_dim, n_head) for i in range(n_layer))

    def forward(self, src, key_padding_mask=None, attn_mask=None):
        for layer in self.layers:
            src = layer(src, key_padding_mask=key_padding_mask, attn_mask=attn_mask)
        return src


class Decoder(nn.Module):
    """由多层 DecoderLayer 堆叠而成。"""
    def __init__(self, embedding_dim=128, n_head=8, n_layer=1):
        super(Decoder, self).__init__()
        self.layers = nn.ModuleList([DecoderLayer(embedding_dim, n_head) for i in range(n_layer)])

    def forward(self, tgt, memory, key_padding_mask=None, attn_mask=None):
        for layer in self.layers:
            tgt, w = layer(tgt, memory, key_padding_mask=key_padding_mask, attn_mask=attn_mask)
        return tgt, w


class PolicyNet(nn.Module):
    # Policy 网络流程：
    # 图编码（Encoder）-> 当前节点解码（Decoder）-> 邻居动作打分（Pointer）。
    def __init__(self, node_dim, embedding_dim):
        super(PolicyNet, self).__init__()

        # 图编码器：把节点原始特征映射到 embedding 并做消息传播。
        self.initial_embedding = nn.Linear(node_dim, embedding_dim)
        self.encoder = Encoder(embedding_dim=embedding_dim, n_head=8, n_layer=6)

        # 解码器：提取“当前节点在全图上下文中的状态表示”。
        self.decoder = Decoder(embedding_dim=embedding_dim, n_head=8, n_layer=1)
        self.current_embedding = nn.Linear(embedding_dim * 2, embedding_dim)

        # 指针头：对候选邻居动作输出 log-prob。
        self.pointer = SingleHeadAttention(embedding_dim)

    def encode_graph(self, node_inputs, node_padding_mask, edge_mask):
        # 输入 node_inputs: [B, N, node_dim]
        # 输出 enhanced_node_feature: [B, N, embedding_dim]
        node_feature = self.initial_embedding(node_inputs)
        enhanced_node_feature = self.encoder(src=node_feature,
                                                         key_padding_mask=node_padding_mask,
                                                         attn_mask=edge_mask)

        return enhanced_node_feature

    def decode_state(self, enhanced_node_feature, current_index, node_padding_mask):
        # 取出当前节点特征，使用整图 memory 做一次 cross-attention 解码。
        embedding_dim = enhanced_node_feature.size()[2]
        current_node_feature = torch.gather(enhanced_node_feature, 1,
                                                  current_index.repeat(1, 1, embedding_dim))
        enhanced_current_node_feature, _ = self.decoder(current_node_feature,
                                                                    enhanced_node_feature,
                                                                    node_padding_mask)

        return current_node_feature, enhanced_current_node_feature

    def output_policy(self, current_node_feature, enhanced_current_node_feature,
                      enhanced_node_feature, current_edge, edge_padding_mask):
        # 对 K 个候选邻居动作输出对数概率（log-prob）。
        embedding_dim = enhanced_node_feature.size()[2]
        current_state_feature = self.current_embedding(torch.cat((enhanced_current_node_feature,
                                                                current_node_feature), dim=-1))

        neighboring_feature = torch.gather(enhanced_node_feature, 1,
                                           current_edge.repeat(1, 1, embedding_dim))

        logp = self.pointer(current_state_feature, neighboring_feature, edge_padding_mask)
        logp = logp.squeeze(1)

        return logp

    # 可选性能优化：@torch.compile（需要 PyTorch 2.x 生态稳定时再开）
    def forward(self, node_inputs, node_padding_mask, edge_mask, current_index,
                current_edge, edge_padding_mask):
        enhanced_node_feature = self.encode_graph(node_inputs, node_padding_mask, edge_mask)
        current_node_feature, enhanced_current_node_feature = self.decode_state(
            enhanced_node_feature, current_index, node_padding_mask)
        logp = self.output_policy(current_node_feature, enhanced_current_node_feature,
                                  enhanced_node_feature, current_edge, edge_padding_mask)

        return logp


class QNet(nn.Module):
    # Critic 网络与 Policy 主干类似，但输出的是每个候选动作的 Q(s,a)。
    def __init__(self, node_dim, embedding_dim):
        super(QNet, self).__init__()

        # 图编码器：结构与 policy 一致，便于共享同类表示能力。
        self.initial_embedding = nn.Linear(node_dim, embedding_dim)
        self.encoder = Encoder(embedding_dim=embedding_dim, n_head=8, n_layer=6)

        # 解码器：提取当前节点上下文表示。
        self.decoder = Decoder(embedding_dim=embedding_dim, n_head=8, n_layer=1)

        self.q_values_layer = nn.Linear(embedding_dim * 3, 1)

    def encode_graph(self, node_inputs, node_padding_mask, edge_mask):
        node_feature = self.initial_embedding(node_inputs)
        enhanced_node_feature = self.encoder(src=node_feature,
                                                         key_padding_mask=node_padding_mask,
                                                         attn_mask=edge_mask)

        return enhanced_node_feature

    def decode_state(self, enhanced_node_feature, current_index, node_padding_mask):
        embedding_dim = enhanced_node_feature.size()[2]
        current_node_feature = torch.gather(enhanced_node_feature, 1,
                                                  current_index.repeat(1, 1, embedding_dim))
        enhanced_current_node_feature, _ = self.decoder(current_node_feature,
                                                                    enhanced_node_feature,
                                                                    node_padding_mask)

        return current_node_feature, enhanced_current_node_feature

    def output_q(self, current_node_feature, enhanced_current_node_feature, enhanced_node_feature,
                 current_edge, edge_padding_mask):
        # 对每个候选动作，拼接“当前状态特征 + 邻居特征”，再回归 Q 值。
        embedding_dim = enhanced_node_feature.size()[2]
        k_size = current_edge.size()[1]
        current_state_feature = torch.cat((enhanced_current_node_feature, current_node_feature), dim=-1)

        neighboring_feature = torch.gather(enhanced_node_feature, 1,
                                           current_edge.repeat(1, 1, embedding_dim))

        action_features = torch.cat((current_state_feature.repeat(1, k_size, 1), neighboring_feature), dim=-1)
        q_values = self.q_values_layer(action_features)
        return q_values

    def forward(self, node_inputs, node_padding_mask, edge_mask, current_index,
                current_edge, edge_padding_mask):
        # 输出形状: [B, K, 1]，每个候选动作一个 Q 值。
        enhanced_node_feature = self.encode_graph(node_inputs, node_padding_mask, edge_mask)
        current_node_feature, enhanced_current_node_feature = self.decode_state(enhanced_node_feature, current_index, node_padding_mask)
        q_values = self.output_q(current_node_feature, enhanced_current_node_feature,
                                 enhanced_node_feature, current_edge, edge_padding_mask)

        return q_values
