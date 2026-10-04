# MeasureX vision core (PRD §4) — C++17 + OpenCV (ArUco in objdetect, >= 4.7).
#
# Builds one portable library used by both the Flutter Android `.so` (added via
# the app's cpp/CMakeLists.txt) and the host unit tests. ArUco uses the main
# `objdetect` module so the same code builds against the official OpenCV Android
# SDK (which has no contrib modules).
cmake_minimum_required(VERSION 3.18)
project(measurex_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(MEASUREX_BUILD_TESTS "Build host unit tests (needs desktop OpenCV)" OFF)
option(MEASUREX_BUILD_TOOLS "Build the mat generator CLI" OFF)

find_package(OpenCV REQUIRED COMPONENTS core imgproc objdetect)

# --- Core library ----------------------------------------------------------
add_library(measurex_core
  src/measure.cpp
  src/aruco_detect.cpp
  src/plane_scale.cpp
  src/box_measure.cpp
  src/confidence.cpp
)
target_include_directories(measurex_core
  PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
  PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(measurex_core PRIVATE ${OpenCV_LIBS})
target_include_directories(measurex_core PRIVATE ${OpenCV_INCLUDE_DIRS})

# --- Host unit tests -------------------------------------------------------
if(MEASUREX_BUILD_TESTS)
  enable_testing()
  find_package(OpenCV REQUIRED COMPONENTS imgcodecs)
  add_executable(measurex_tests test/measure_test.cpp)
  target_link_libraries(measurex_tests PRIVATE measurex_core ${OpenCV_LIBS})
  target_include_directories(measurex_tests PRIVATE ${OpenCV_INCLUDE_DIRS})
  add_test(NAME measurex_tests COMMAND measurex_tests)
endif()

# --- Mat generator CLI -----------------------------------------------------
if(MEASUREX_BUILD_TOOLS)
  find_package(OpenCV REQUIRED COMPONENTS imgcodecs)
  add_executable(measurex_matgen tools/matgen.cpp)
  target_link_libraries(measurex_matgen PRIVATE ${OpenCV_LIBS})
  target_include_directories(measurex_matgen PRIVATE ${OpenCV_INCLUDE_DIRS})
endif()
