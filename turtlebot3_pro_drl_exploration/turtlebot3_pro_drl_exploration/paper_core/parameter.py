"""Inference-time defaults tuned for TurtleBot3 Pro in Gazebo + Cartographer."""

# Map / graph resolution
CELL_SIZE = 0.05  # meters, should match cartographer occupancy grid resolution
NODE_RESOLUTION = 1.0  # meters
FRONTIER_CELL_SIZE = 0.20  # meters

# Occupancy representation used by the original paper code
FREE = 255
OCCUPIED = 1
UNKNOWN = 127

# Sensor and utility scope (modified Burger uses RPLIDAR A2M12, max range ~= 12m)
SENSOR_RANGE = 12.0
UTILITY_RANGE = 0.8 * SENSOR_RANGE
MIN_UTILITY = 1

# Local planning update window
UPDATING_MAP_SIZE = 4 * SENSOR_RANGE + 4 * NODE_RESOLUTION

# Network dimensions (must match trained checkpoint architecture)
NODE_INPUT_DIM = 4
EMBEDDING_DIM = 128
K_SIZE = 25
NODE_PADDING_SIZE = 400
