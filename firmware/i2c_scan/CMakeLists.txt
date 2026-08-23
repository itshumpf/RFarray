cmake_minimum_required(VERSION 3.16)
# Deliberately no EXTRA_COMPONENT_DIRS: this project must not pull in
# ../common. It is a bus probe, and node_hal (which owns ssd1306.c and its
# hard-coded pin assumptions) is exactly what it exists to check.
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(i2c_scan)
