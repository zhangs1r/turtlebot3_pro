from setuptools import setup

package_name = 'turtlebot3_pro_drl_exploration'

setup(
    name=package_name,
    version='0.1.0',
    packages=[
        package_name,
        package_name + '.paper_core',
    ],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/drl_cartographer_explore.launch.py']),
        ('share/' + package_name + '/config', [
            'config/drl_explorer.yaml',
            'config/nav2_params_cartographer_drl.yaml',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='turtlebot3 user',
    maintainer_email='user@todo.todo',
    description='Deep RL graph-exploration planner integration for TurtleBot3 Pro simulation.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'drl_explorer = turtlebot3_pro_drl_exploration.drl_explorer_node:main',
        ],
    },
)
