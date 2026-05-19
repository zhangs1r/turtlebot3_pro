import numpy as np


def collision_check(x0, y0, x1, y1, ground_truth, robot_belief):
    # 沿一条射线投射观测，把 ground_truth 中可见栅格写入 robot_belief。
    # 射线碰到障碍（或到达终点）后停止。
    # NumPy 2.x 对索引类型更严格，这里保持 Bresenham 状态为 int。
    x0 = int(np.rint(x0))
    y0 = int(np.rint(y0))
    x1 = int(np.rint(x1))
    y1 = int(np.rint(y1))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    x, y = x0, y0
    error = dx - dy
    x_inc = 1 if x1 > x0 else -1
    y_inc = 1 if y1 > y0 else -1
    dx *= 2
    dy *= 2

    collision_flag = 0
    max_collision = 10

    while 0 <= x < ground_truth.shape[1] and 0 <= y < ground_truth.shape[0]:
        k = ground_truth[y, x]
        if k == 1 and collision_flag < max_collision:
            collision_flag += 1
            if collision_flag >= max_collision:
                break

        if k != 1 and collision_flag > 0:
            break

        if x == x1 and y == y1:
            break

        # NumPy 2.0+ 移除了 ndarray.itemset，改用直接赋值。
        robot_belief[y, x] = k

        if error > 0:
            x += x_inc
            error -= dy
        else:
            y += y_inc
            error += dx

    return robot_belief


def sensor_work(robot_position, sensor_range, robot_belief, ground_truth):
    # 以固定角步长做 360 度雷达式扫描。
    sensor_angle_inc = 0.5 / 180 * np.pi
    sensor_angle = 0
    x0 = robot_position[0]
    y0 = robot_position[1]
    while sensor_angle < 2 * np.pi:
        x1 = x0 + np.cos(sensor_angle) * sensor_range
        y1 = y0 + np.sin(sensor_angle) * sensor_range
        robot_belief = collision_check(x0, y0, x1, y1, ground_truth, robot_belief)
        sensor_angle += sensor_angle_inc
    return robot_belief
