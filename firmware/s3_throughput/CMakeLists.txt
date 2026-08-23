cmake_minimum_required(VERSION 3.16)
# Deliberately no EXTRA_COMPONENT_DIRS: this project must not pull in
# ../common. It measures the USB link and nothing else, so node_hal,
# telemetry and calibration are all excluded on purpose.
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(s3_throughput)
