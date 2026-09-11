cmake_minimum_required(VERSION 3.8)
project(ros_robot_controller_msgs)

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/BusServoState.msg"
  "msg/ButtonState.msg"
  "msg/BuzzerState.msg"
  "msg/ConveyorSpeed.msg"
  "msg/GetBusServoCmd.msg"
  "msg/GetPWMServoCmd.msg"
  "msg/LedState.msg"
  "msg/MotorSpeedControl.msg"
  "msg/MotorsSpeedControl.msg"
  "msg/MotorsState.msg"
  "msg/MotorState.msg"
  "msg/OLEDState.msg"
  "msg/PWMServoState.msg"
  "msg/Sbus.msg"
  "msg/ServoPosition.msg"
  "msg/ServosPosition.msg"
  "msg/SetBusServoState.msg"
  "msg/SetPWMServoState.msg"
  "msg/StepperSubdivision.msg"
  "srv/GetBusServoState.srv"
  "srv/GetPWMServoState.srv"
  "srv/MoveStepper.srv"
  DEPENDENCIES std_msgs
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
