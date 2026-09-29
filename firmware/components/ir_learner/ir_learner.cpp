#include "ir_learner.h"

#include <algorithm>
#include <cstring>

#include <esp_timer.h>

#include "capture.h"
#include "esphome/core/log.h"

namespace esphome::ir_learner {

static const char *const TAG = "ir_learner";

void IRAM_ATTR IRLearner::edge_isr(IRLearner *self) {
  if (!self->armed_)
    return;
  uint32_t count = self->edge_count_;
  if (count >= self->edge_times_.size()) {
    self->overflowed_ = true;
    return;
  }
  if (count == 0)
    self->first_edge_starts_mark_ = self->isr_pin_.digital_read();
  self->edge_times_[count] = static_cast<uint32_t>(esp_timer_get_time());
  self->edge_count_ = count + 1;
}

std::string IRLearner::clean_name(const std::string &requested_name) {
  std::string name;
  for (char character : requested_name) {
    if (name.size() + 1 >= NAME_CAPACITY)
      break;
    if (character >= 'A' && character <= 'Z')
      name += static_cast<char>(character - 'A' + 'a');
    else if ((character >= 'a' && character <= 'z') || (character >= '0' && character <= '9') || character == '_')
      name += character;
    else if (character == ' ' || character == '-')
      name += '_';
  }
  return name;
}

void IRLearner::setup() {
  this->edge_times_.assign(this->max_timings_ + 2, 0);
  this->index_.assign(this->slot_count_, SlotRecord{});
  this->index_preference_ = global_preferences->make_preference(sizeof(SlotRecord) * this->slot_count_,
                                                                fnv1_hash("ir_learner_index"), true);
  if (!this->index_preference_.load(reinterpret_cast<uint8_t *>(this->index_.data()),
                                    sizeof(SlotRecord) * this->slot_count_))
    this->index_.assign(this->slot_count_, SlotRecord{});
  uint32_t timings_key = fnv1_hash("ir_learner_timings");
  for (uint8_t slot = 0; slot < this->slot_count_; slot++) {
    this->index_[slot].name[NAME_CAPACITY - 1] = '\0';
    this->timing_preferences_.push_back(
        global_preferences->make_preference(this->max_timings_ * sizeof(uint16_t), timings_key + slot, true));
  }
  this->calibration_preference_ =
      global_preferences->make_preference<int32_t>(fnv1_hash("ir_learner_calibration"), true);
  this->calibrated_ = this->calibration_preference_.load(&this->mark_shortening_us_);
  this->pin_->setup();
  this->isr_pin_ = this->pin_->to_isr();
  this->pin_->attach_interrupt(IRLearner::edge_isr, this, gpio::INTERRUPT_ANY_EDGE);
  this->report_(this->saved_count() == 0 ? "ready, no codes saved" : "ready");
}

void IRLearner::dump_config() {
  ESP_LOGCONFIG(TAG, "IR learner:");
  LOG_PIN("  Pin: ", this->pin_);
  ESP_LOGCONFIG(TAG, "  Slots: %u (%u used), up to %u timings each", this->slot_count_,
                static_cast<unsigned>(this->saved_count()), this->max_timings_);
  ESP_LOGCONFIG(TAG, "  Code ends after %u us of silence", static_cast<unsigned>(this->end_silence_us_));
  if (this->calibrated_)
    ESP_LOGCONFIG(TAG, "  Receiver shortens marks by %d us", static_cast<int>(this->mark_shortening_us_));
  else
    ESP_LOGCONFIG(TAG, "  Receiver not calibrated");
}

bool IRLearner::learn(const std::string &requested_name) {
  std::string name = IRLearner::clean_name(requested_name);
  if (name.empty()) {
    this->report_("give the code a name first");
    return false;
  }
  if (this->mode_ != Mode::IDLE) {
    this->report_("busy, try again in a moment");
    return false;
  }
  if (this->find_slot_(name) < 0 && this->free_slot_() < 0) {
    this->report_("all slots are full, delete a code first");
    return false;
  }
  this->pending_name_ = name;
  this->arm_capture_(Mode::LEARNING);
  this->report_("point the remote at the bridge and press the button for " + name);
  return true;
}

bool IRLearner::send(const std::string &requested_name) {
  std::string name = IRLearner::clean_name(requested_name);
  int slot = this->find_slot_(name);
  if (slot < 0) {
    this->report_("no code named " + name);
    return false;
  }
  if (this->mode_ == Mode::LEARNING || this->mode_ == Mode::CALIBRATING) {
    this->report_("busy, cannot send now");
    return false;
  }
  if (!this->load_(slot, this->sent_durations_)) {
    this->report_("could not read " + name + " from flash");
    return false;
  }
  this->pending_name_ = name;
  this->transmit_(this->sent_durations_, Mode::ECHO);
  return true;
}

bool IRLearner::calibrate() {
  if (this->mode_ != Mode::IDLE) {
    this->report_("busy, try again in a moment");
    return false;
  }
  this->sent_durations_ = {CALIBRATION_HEADER_MARK_US, CALIBRATION_HEADER_SPACE_US};
  for (uint32_t width : CALIBRATION_WIDTHS_US) {
    this->sent_durations_.push_back(width);
    this->sent_durations_.push_back(CALIBRATION_BASE_US);
    this->sent_durations_.push_back(CALIBRATION_BASE_US);
    this->sent_durations_.push_back(width);
  }
  this->sent_durations_.push_back(CALIBRATION_BASE_US);
  this->transmit_(this->sent_durations_, Mode::CALIBRATING);
  return true;
}

void IRLearner::transmit_(const std::vector<uint32_t> &durations, Mode mode) {
  auto call = this->transmitter_->transmit();
  auto *data = call.get_data();
  data->set_carrier_frequency(this->carrier_frequency_);
  for (size_t i = 0; i < durations.size(); i++) {
    if (i % 2 == 0)
      data->mark(durations[i]);
    else
      data->space(durations[i]);
  }
  this->echo_wait_ms_ = total_duration(durations) / 1000 + ECHO_MARGIN_MS;
  this->arm_capture_(mode);
  call.perform();
}

bool IRLearner::forget(const std::string &requested_name) {
  std::string name = IRLearner::clean_name(requested_name);
  int slot = this->find_slot_(name);
  if (slot < 0) {
    this->report_("no code named " + name);
    return false;
  }
  this->index_[slot] = SlotRecord{};
  this->save_index_();
  this->report_("deleted " + name);
  return true;
}

std::vector<int32_t> IRLearner::signed_timings(const std::string &requested_name) {
  std::vector<int32_t> timings;
  std::vector<uint32_t> durations;
  int slot = this->find_slot_(IRLearner::clean_name(requested_name));
  if (slot < 0 || !this->load_(slot, durations))
    return timings;
  timings.reserve(durations.size());
  for (size_t i = 0; i < durations.size(); i++) {
    int32_t duration = static_cast<int32_t>(durations[i]);
    timings.push_back(i % 2 == 0 ? duration : -duration);
  }
  return timings;
}

std::vector<int32_t> IRLearner::last_raw_capture() const {
  std::vector<int32_t> timings;
  timings.reserve(this->last_raw_capture_.size());
  for (size_t i = 0; i < this->last_raw_capture_.size(); i++) {
    int32_t duration = static_cast<int32_t>(this->last_raw_capture_[i]);
    timings.push_back(i % 2 == 0 ? duration : -duration);
  }
  return timings;
}

std::string IRLearner::saved_names() const {
  std::string names;
  for (const auto &record : this->index_) {
    if (record.count == 0)
      continue;
    if (!names.empty())
      names += ", ";
    names += record.name;
  }
  return names;
}

size_t IRLearner::saved_count() const {
  return std::count_if(this->index_.begin(), this->index_.end(),
                       [](const SlotRecord &record) { return record.count > 0; });
}

void IRLearner::arm_capture_(Mode mode) {
  this->armed_ = false;
  this->edge_count_ = 0;
  this->overflowed_ = false;
  this->first_edge_starts_mark_ = true;
  this->mode_ = mode;
  this->started_ms_ = millis();
  this->armed_ = true;
}

bool IRLearner::capture_still_running_(uint32_t edge_count) {
  if (edge_count == 0 || this->overflowed_)
    return false;
  uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
  return now_us - this->edge_times_[edge_count - 1] < this->end_silence_us_;
}

void IRLearner::loop() {
  if (this->mode_ == Mode::IDLE)
    return;
  uint32_t edge_count = this->edge_count_;
  if (this->capture_still_running_(edge_count))
    return;
  uint32_t elapsed_ms = millis() - this->started_ms_;
  if (this->mode_ == Mode::LEARNING) {
    if (edge_count == 0 && elapsed_ms < this->learn_timeout_ms_)
      return;
    this->armed_ = false;
    this->finish_learning_();
  } else {
    if (edge_count == 0 && elapsed_ms < this->echo_wait_ms_)
      return;
    this->armed_ = false;
    if (this->mode_ == Mode::CALIBRATING)
      this->finish_calibration_();
    else
      this->finish_echo_();
  }
  this->mode_ = Mode::IDLE;
}

std::vector<uint32_t> IRLearner::captured_durations_(bool corrected) {
  uint32_t edge_count = this->edge_count_;
  const uint32_t *edges = this->edge_times_.data();
  if (edge_count > 0 && !this->first_edge_starts_mark_) {
    edges++;
    edge_count--;
  }
  std::vector<uint32_t> durations = durations_between(edges, edge_count);
  merge_glitches(durations, this->shortest_pulse_us_);
  for (auto &duration : durations)
    duration = std::min(duration, MAX_STORED_DURATION_US);
  if (corrected) {
    undo_mark_shortening(durations, this->mark_shortening_us_);
    snap_to_clusters(durations, CLUSTER_SPREAD);
  }
  return durations;
}

void IRLearner::finish_learning_() {
  if (this->edge_count_ == 0) {
    this->report_("nothing heard, try again closer to the bridge");
    return;
  }
  if (this->overflowed_) {
    this->report_("code too long to store, press the button more briefly");
    return;
  }
  this->last_raw_capture_ = this->captured_durations_(false);
  std::vector<uint32_t> durations = this->captured_durations_(true);
  if (durations.size() < MIN_TIMINGS) {
    this->report_("only noise heard, try again");
    return;
  }
  int slot = this->find_slot_(this->pending_name_);
  if (slot < 0)
    slot = this->free_slot_();
  if (!this->store_(slot, this->pending_name_, durations)) {
    this->report_("could not save " + this->pending_name_ + " to flash");
    return;
  }
  ESP_LOGI(TAG, "Learned '%s': %u timings, %u us", this->pending_name_.c_str(),
           static_cast<unsigned>(durations.size()), static_cast<unsigned>(total_duration(durations)));
  this->report_("learned " + this->pending_name_ + " (" + std::to_string(durations.size()) + " timings)");
  this->learned_callbacks_.call(this->pending_name_, static_cast<uint16_t>(durations.size()));
}

void IRLearner::finish_echo_() {
  std::vector<uint32_t> heard = this->captured_durations_(true);
  EchoComparison comparison =
      compare_echo(this->sent_durations_, heard, this->echo_tolerance_, this->echo_slack_us_);
  ESP_LOGI(TAG, "Echo of '%s': sent %u, heard %u timings, worst difference %u us at %u", this->pending_name_.c_str(),
           static_cast<unsigned>(this->sent_durations_.size()), static_cast<unsigned>(heard.size()),
           static_cast<unsigned>(comparison.worst_difference_us), static_cast<unsigned>(comparison.worst_index));
  if (comparison.agrees)
    this->report_("sent " + this->pending_name_ + ", echo confirmed");
  else if (heard.empty())
    this->report_("sent " + this->pending_name_ + ", no echo heard");
  else
    this->report_("sent " + this->pending_name_ + ", echo did not match");
  this->echo_callbacks_.call(this->pending_name_, comparison.agrees);
}

void IRLearner::finish_calibration_() {
  std::vector<uint32_t> heard = this->captured_durations_(false);
  if (heard.size() != this->sent_durations_.size()) {
    this->report_("calibration failed: heard " + std::to_string(heard.size()) + " of " +
                  std::to_string(this->sent_durations_.size()) + " pulses, check that the receiver sees the LED");
    return;
  }
  int32_t shortening = mark_shortening(this->sent_durations_, heard);
  if (shortening > MAX_BELIEVABLE_SHORTENING_US || shortening < -MAX_BELIEVABLE_SHORTENING_US) {
    this->report_("calibration failed: marks off by " + std::to_string(shortening) + " us, too much to trust");
    return;
  }
  this->mark_shortening_us_ = shortening;
  this->calibrated_ = true;
  this->calibration_preference_.save(&this->mark_shortening_us_);
  global_preferences->sync();
  this->report_("calibrated: receiver shortens marks by " + std::to_string(shortening) + " us");
}

bool IRLearner::store_(int slot, const std::string &name, const std::vector<uint32_t> &durations) {
  std::vector<uint16_t> packed(durations.begin(), durations.end());
  if (!this->timing_preferences_[slot].save(reinterpret_cast<const uint8_t *>(packed.data()),
                                            packed.size() * sizeof(uint16_t)))
    return false;
  SlotRecord record{};
  std::strncpy(record.name, name.c_str(), NAME_CAPACITY - 1);
  record.count = static_cast<uint16_t>(packed.size());
  this->index_[slot] = record;
  this->save_index_();
  return true;
}

bool IRLearner::load_(int slot, std::vector<uint32_t> &durations) {
  std::vector<uint16_t> packed(this->index_[slot].count);
  if (!this->timing_preferences_[slot].load(reinterpret_cast<uint8_t *>(packed.data()),
                                            packed.size() * sizeof(uint16_t)))
    return false;
  durations.assign(packed.begin(), packed.end());
  return true;
}

int IRLearner::find_slot_(const std::string &name) const {
  for (size_t slot = 0; slot < this->index_.size(); slot++) {
    if (this->index_[slot].count > 0 && name == this->index_[slot].name)
      return static_cast<int>(slot);
  }
  return -1;
}

int IRLearner::free_slot_() const {
  for (size_t slot = 0; slot < this->index_.size(); slot++) {
    if (this->index_[slot].count == 0)
      return static_cast<int>(slot);
  }
  return -1;
}

void IRLearner::save_index_() {
  this->index_preference_.save(reinterpret_cast<const uint8_t *>(this->index_.data()),
                               sizeof(SlotRecord) * this->index_.size());
  global_preferences->sync();
}

void IRLearner::report_(const std::string &status) {
  ESP_LOGI(TAG, "%s", status.c_str());
  this->status_callbacks_.call(status);
}

}
