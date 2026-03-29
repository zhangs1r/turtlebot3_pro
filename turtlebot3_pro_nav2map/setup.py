from setuptools import setup

package_name = 'turtlebot3_pro_nav2map'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/nav2_map.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='turtlebot3 user',
    maintainer_email='user@todo.todo',
    description='Nav2 + Cartographer mapping launch stack for TurtleBot3 Burger Pro simulation.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'goal_pose_bridge = turtlebot3_pro_nav2map.goal_pose_bridge:main',
        ],
    },
)
