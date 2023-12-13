#!/usr/bin/env python3

# Software License Agreement (BSD)
#
# @author    Roni Kreinin <rkreinin@clearpathrobotics.com>
# @copyright (c) 2023, Clearpath Robotics, Inc., All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of Clearpath Robotics nor the names of its contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# Redistribution and use in source and binary forms, with or without
# modification, is not permitted without the express permission
# of Clearpath Robotics.

from clearpath_generator_common.common import LaunchFile, Package
from clearpath_generator_common.launch.writer import LaunchWriter
from clearpath_generator_common.launch.generator import LaunchGenerator
from clearpath_generator_robot.launch.sensors import SensorLaunch

from clearpath_config.common.types.platform import Platform

import os


class RobotLaunchGenerator(LaunchGenerator):
    def __init__(self, setup_path: str = '/etc/clearpath/') -> None:
        super().__init__(setup_path)

        # Filter for MCU IMU
        self.imu_0_filter_node = LaunchFile.Node(
            package='imu_filter_madgwick',
            executable='imu_filter_madgwick_node',
            name='imu_filter_node',
            namespace=self.namespace,
            parameters=[LaunchFile.Variable('imu_filter')],
            remappings=[
                ('imu/data_raw', 'sensors/imu_0/data_raw'),
                ('imu/mag', 'sensors/imu_0/magnetic_field'),
                ('imu/data', 'sensors/imu_0/data'),
                ('/tf', 'tf'),
            ],
        )

        self.imu_0_filter_config = LaunchFile.LaunchArg(
            'imu_filter',
            default_value=os.path.join(self.platform_params_path, 'imu_filter.yaml'),
        )

        # Configure MCU namespace and domain ID
        self.configure_mcu = LaunchFile.Process(
            name='configure_mcu',
            cmd=[
                ['export ROS_DOMAIN_ID=0;'],
                [LaunchFile.Variable('FindExecutable(name=\'ros2\')'),
                 ' service call platform/mcu/configure',
                 ' clearpath_platform_msgs/srv/ConfigureMcu',
                 ' \"{{domain_id: {0},'.format(self.clearpath_config.system.domain_id),
                 ' robot_namespace: \\\'{0}\\\'}}\"'.format(self.namespace)]
            ]
        )

        # Ethernet MicroROS Agent
        self.eth_uros_node = LaunchFile.Node(
            name='micro_ros_agent',
            package='micro_ros_agent',
            executable='micro_ros_agent',
            namespace=self.namespace,
            arguments=['udp4', '--port', '11411'],
        )

        # J100 MicroROS Agent
        self.j100_uros_node = LaunchFile.Node(
            name='micro_ros_agent',
            package='micro_ros_agent',
            executable='micro_ros_agent',
            namespace=self.namespace,
            arguments=['serial', '--dev', '/dev/clearpath/j100'],
        )

        # J100 Navsat driver
        self.nmea_driver_node = LaunchFile.Node(
            package='nmea_navsat_driver',
            executable='nmea_topic_driver',
            name='nmea_topic_driver',
            namespace=self.namespace,
            remappings=[
                ('nmea_sentence', 'sensors/gps_0/nmea_sentence'),
                ('fix', 'sensors/gps_0/fix'),
                ('heading', 'sensors/gps_0/heading'),
                ('time_reference', 'sensors/gps_0/time_reference'),
                ('vel', 'sensors/gps_0/vel'),
            ],
        )

        # Wireless watcher
        self.wireless_watcher_node = LaunchFile.Node(
            package='wireless_watcher',
            executable='wireless_watcher',
            name='wireless_watcher',
            namespace=self.namespace,
            parameters=[
                {
                    'hz': 1,
                    'dev': '',
                    'connected_topic': 'platform/wifi_connected',
                    'connection_topic': 'platform/wifi_status',
                }
            ],
        )

        # Diagnostics
        clearpath_diagnostics_package = Package('clearpath_diagnostics')
        self.diagnostics_launch = LaunchFile('diagnostics', package=clearpath_diagnostics_package)

        # Battery state
        self.battery_state_estimator = LaunchFile.Node(
            package='clearpath_diagnostics',
            executable='battery_state_estimator',
            name='battery_state_estimator',
            namespace=self.namespace,
            arguments=['-s', setup_path]
        )

        self.battery_state_control = LaunchFile.Node(
            package='clearpath_diagnostics',
            executable='battery_state_control',
            name='battery_state_control',
            namespace=self.namespace,
            arguments=['-s', setup_path]
        )

        # Lighting
        self.lighting_node = LaunchFile.Node(
          package='clearpath_platform',
          executable='lighting_node',
          name='lighting_node',
          namespace=self.namespace,
          parameters=[{'platform': self.platform_model}]
        )

        # Sevcon
        self.sevcon_node = LaunchFile.Node(
          package='sevcon_traction',
          executable='sevcon_traction_node',
          name='sevcon_traction_node',
          namespace=self.namespace,
        )

        # Static transform from <namespace>/odom to odom
        # See https://github.com/ros-controls/ros2_controllers/pull/533
        self.tf_namespaced_odom_publisher = LaunchFile.get_static_tf_node(
            name='namespaced_odom',
            namespace=self.namespace,
            parent_link='odom',
            child_link=f'{self.namespace}/odom',
            use_sim_time=False,
        )

        # Static transform from <namespace>/base_link to base_link
        self.tf_namespaced_base_link_publisher = LaunchFile.get_static_tf_node(
            name='namespaced_base_link',
            namespace=self.namespace,
            parent_link=f'{self.namespace}/base_link',
            child_link='base_link',
            use_sim_time=False,
        )

        # Components required for each platform
        common_platform_components = [
            self.wireless_watcher_node,
            self.diagnostics_launch,
            self.battery_state_estimator,
            self.battery_state_control
        ]

        self.platform_components = {
            Platform.J100: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.configure_mcu,
                self.j100_uros_node,
                self.nmea_driver_node
            ],
            Platform.A200: common_platform_components,
            Platform.W200: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.eth_uros_node,
                self.configure_mcu,
                self.lighting_node,
                self.sevcon_node
            ],
            Platform.DD100: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.eth_uros_node,
                self.configure_mcu,
                self.lighting_node,
            ],
            Platform.DO100: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.eth_uros_node,
                self.configure_mcu,
                self.lighting_node,
            ],
            Platform.DD150: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.eth_uros_node,
                self.configure_mcu,
                self.lighting_node,
            ],
            Platform.DO150: common_platform_components + [
                self.imu_0_filter_node,
                self.imu_0_filter_config,
                self.eth_uros_node,
                self.configure_mcu,
                self.lighting_node,
            ],
        }

    def generate_sensors(self) -> None:
        sensors_service_launch_writer = LaunchWriter(self.sensors_service_launch_file)
        sensors = self.clearpath_config.sensors.get_all_sensors()

        for sensor in sensors:
            if sensor.launch_enabled:
                sensor_launch = SensorLaunch(
                    sensor,
                    self.namespace,
                    self.sensors_launch_path,
                    self.sensors_params_path,
                )
                # Generate sensor launch file
                sensor_launch.generate()
                # Include sensor launch in top level sensors launch file
                sensors_service_launch_writer.add(sensor_launch.launch_file)

        sensors_service_launch_writer.generate_file()

    def generate_platform(self) -> None:
        platform_service_launch_writer = LaunchWriter(self.platform_service_launch_file)
        platform_service_launch_writer.add(self.platform_launch_file)

        for component in self.platform_components[self.platform_model]:
            platform_service_launch_writer.add(component)

        if self.namespace not in ('', '/'):
            platform_service_launch_writer.add(self.tf_namespaced_odom_publisher)
            platform_service_launch_writer.add(self.tf_namespaced_base_link_publisher)

        platform_service_launch_writer.generate_file()
