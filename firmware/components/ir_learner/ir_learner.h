#pragma once

#include <string>
#include <vector>

#include "esphome/components/remote_base/remote_base.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/preferences.h"

namespace esphome::ir_learner {

const size_t NAME_CAPACITY = 24;
const size_t MIN_TIMINGS = 7;
const uint32_t MAX_STORED_DURATION_US = 65535;
const uint32_t ECHO_MARGIN_MS = 300;
const uint32_t CALIBRATION_HEADER_MARK_US = 9000;
const uint32_t CALIBRATION_HEADER_SPACE_US = 4500;
const uint32_t CALIBRATION_BASE_US = 560;
const uint32_t CALIBRATION_WIDTHS_US[] = {450, 560, 700, 900, 1200, 1690, 2500};
const int32_t MAX_BELIEVABLE_SHORTENING_US = 250;
const float CLUSTER_SPREAD = 0.15f;

struct SlotRecord {
  char name[NAME_CAPACITY];
  uint16_t count;
};

class IRLearner : public Component {
 public:
  void set_pin(InternalGPIOPin *pin) { this->pin_ = pin; }
  void set_transmitter(remote_base::RemoteTransmitterBase *transmitter) { this->transmitter_ = transmitter; }
  void set_slot_count(uint8_t slot_count) { this->slot_count_ = slot_count; }
  void set_max_timings(uint16_t max_timings) { this->max_timings_ = max_timings; }
  void set_end_silence_us(uint32_t end_silence_us) { this->end_silence_us_ = end_silence_us; }
  void set_learn_timeout_ms(uint32_t learn_timeout_ms) { this->learn_timeout_ms_ = learn_timeout_ms; }
  void set_shortest_pulse_us(uint32_t shortest_pulse_us) { this->shortest_pulse_us_ = shortest_pulse_us; }
  void set_carrier_frequency(uint32_t carrier_frequency) { this->carrier_frequency_ = carrier_frequency; }
  void set_echo_tolerance(float echo_tolerance) { this->echo_tolerance_ = echo_tolerance; }
  void set_echo_slack_us(uint32_t echo_slack_us) { this->echo_slack_us_ = echo_slack_us; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  bool learn(const std::string &requested_name);
  bool send(const std::string &requested_name);
  bool forget(const std::string &requested_name);
  bool calibrate();
  int32_t mark_shortening_us() const { return this->mark_shortening_us_; }
  std::vector<int32_t> signed_timings(const std::string &requested_name);
  std::vector<int32_t> last_raw_capture() const;
  std::string saved_names() const;
  size_t saved_count() const;

  void add_on_status_callback(std::function<void(const std::string &)> &&callback) {
    this->status_callbacks_.add(std::move(callback));
  }
  void add_on_learned_callback(std::function<void(const std::string &, uint16_t)> &&callback) {
    this->learned_callbacks_.add(std::move(callback));
  }
  void add_on_echo_callback(std::function<void(const std::string &, bool)> &&callback) {
    this->echo_callbacks_.add(std::move(callback));
  }

 protected:
  enum class Mode { IDLE, LEARNING, ECHO, CALIBRATING };

  static void edge_isr(IRLearner *self);
  static std::string clean_name(const std::string &requested_name);

  void arm_capture_(Mode mode);
  void transmit_(const std::vector<uint32_t> &durations, Mode mode);
  std::vector<uint32_t> captured_durations_(bool corrected);
  bool capture_still_running_(uint32_t edge_count);
  void finish_learning_();
  void finish_echo_();
  void finish_calibration_();
  bool store_(int slot, const std::string &name, const std::vector<uint32_t> &durations);
  bool load_(int slot, std::vector<uint32_t> &durations);
  int find_slot_(const std::string &name) const;
  int free_slot_() const;
  void save_index_();
  void report_(const std::string &status);

  InternalGPIOPin *pin_{nullptr};
  ISRInternalGPIOPin isr_pin_;
  remote_base::RemoteTransmitterBase *transmitter_{nullptr};
  uint8_t slot_count_{24};
  uint16_t max_timings_{1024};
  uint32_t end_silence_us_{150000};
  uint32_t learn_timeout_ms_{10000};
  uint32_t shortest_pulse_us_{100};
  uint32_t carrier_frequency_{38000};
  float echo_tolerance_{0.4f};
  uint32_t echo_slack_us_{150};

  std::vector<uint32_t> edge_times_;
  volatile uint32_t edge_count_{0};
  volatile bool armed_{false};
  volatile bool overflowed_{false};
  volatile bool first_edge_starts_mark_{true};

  Mode mode_{Mode::IDLE};
  uint32_t started_ms_{0};
  uint32_t echo_wait_ms_{0};
  std::string pending_name_;
  std::vector<uint32_t> sent_durations_;
  std::vector<uint32_t> last_raw_capture_;

  int32_t mark_shortening_us_{0};
  bool calibrated_{false};
  ESPPreferenceObject calibration_preference_;

  std::vector<SlotRecord> index_;
  ESPPreferenceObject index_preference_;
  std::vector<ESPPreferenceObject> timing_preferences_;

  CallbackManager<void(const std::string &)> status_callbacks_;
  CallbackManager<void(const std::string &, uint16_t)> learned_callbacks_;
  CallbackManager<void(const std::string &, bool)> echo_callbacks_;
};

class StatusTrigger : public Trigger<std::string> {
 public:
  explicit StatusTrigger(IRLearner *parent) {
    parent->add_on_status_callback([this](const std::string &status) { this->trigger(status); });
  }
};

class LearnedTrigger : public Trigger<std::string, uint16_t> {
 public:
  explicit LearnedTrigger(IRLearner *parent) {
    parent->add_on_learned_callback([this](const std::string &name, uint16_t count) { this->trigger(name, count); });
  }
};

class EchoTrigger : public Trigger<std::string, bool> {
 public:
  explicit EchoTrigger(IRLearner *parent) {
    parent->add_on_echo_callback([this](const std::string &name, bool confirmed) { this->trigger(name, confirmed); });
  }
};

}
