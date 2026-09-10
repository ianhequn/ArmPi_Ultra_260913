#include <chrono>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "serial_driver/serial_driver.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class SerialSendNode : public rclcpp::Node
{
public:
  SerialSendNode()
  : Node("serial_send_node")
  {
    this->declare_parameter("device_name", "/dev/ttyUSB0");
    this->declare_parameter("baud_rate", 115200);
    this->declare_parameter("send_interval_ms", 1000);
    this->declare_parameter("send_message", "Hello from ROS2 serial node!");

    device_name_ = this->get_parameter("device_name").as_string();
    baud_rate_ = this->get_parameter("baud_rate").as_int();
    send_interval_ms_ = this->get_parameter("send_interval_ms").as_int();
    send_message_ = this->get_parameter("send_message").as_string();

    try {
      io_ctx_ = std::make_unique<drivers::common::IoContext>();
      serial_driver_ = std::make_unique<drivers::serial_driver::SerialDriver>(*io_ctx_);

      drivers::serial_driver::SerialPortConfig port_config(
        baud_rate_,
        drivers::serial_driver::FlowControl::NONE,
        drivers::serial_driver::Parity::NONE,
        drivers::serial_driver::StopBits::ONE);

      serial_driver_->init_port(device_name_, port_config);
      serial_driver_->port()->open();

      RCLCPP_INFO(
        this->get_logger(),
        "Serial port %s opened at %d baud",
        device_name_.c_str(), baud_rate_);
    } catch (const std::exception & e) {
      RCLCPP_ERROR(this->get_logger(), "Failed to open serial port: %s", e.what());
      throw;
    }

    timer_ = this->create_wall_timer(
      std::chrono::milliseconds(send_interval_ms_),
      std::bind(&SerialSendNode::timer_callback, this));

    RCLCPP_INFO(
      this->get_logger(),
      "Serial send node started, sending every %d ms",
      send_interval_ms_);
  }

  ~SerialSendNode()
  {
    try {
      if (serial_driver_ && serial_driver_->port() && serial_driver_->port()->is_open()) {
        serial_driver_->port()->close();
        RCLCPP_INFO(this->get_logger(), "Serial port closed");
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(this->get_logger(), "Error closing serial port: %s", e.what());
    }
  }

private:
  void timer_callback()
  {
    try {
      std::vector<uint8_t> data(send_message_.begin(), send_message_.end());
      data.push_back('\n');
      size_t bytes_sent = serial_driver_->port()->send(data);
      RCLCPP_DEBUG(this->get_logger(), "Sent %zu bytes: %s", bytes_sent, send_message_.c_str());
    } catch (const std::exception & e) {
      RCLCPP_ERROR(this->get_logger(), "Send failed: %s", e.what());
    }
  }

  std::string device_name_;
  int baud_rate_;
  int send_interval_ms_;
  std::string send_message_;

  std::unique_ptr<drivers::common::IoContext> io_ctx_;
  std::unique_ptr<drivers::serial_driver::SerialDriver> serial_driver_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  try {
    auto node = std::make_shared<SerialSendNode>();
    rclcpp::spin(node);
  } catch (const std::exception & e) {
    RCLCPP_ERROR(rclcpp::get_logger("serial_send_node"), "Fatal error: %s", e.what());
  }
  rclcpp::shutdown();
  return 0;
}
