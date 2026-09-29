#include "panasonic_ac.h"

#include <cmath>

namespace esphome::panasonic_ac {

uint8_t PanasonicClimate::remote_mode_() const {
  switch (this->mode) {
    case climate::CLIMATE_MODE_HEAT:
      return MODE_HEAT;
    case climate::CLIMATE_MODE_DRY:
      return MODE_DRY;
    case climate::CLIMATE_MODE_FAN_ONLY:
      return MODE_FAN;
    case climate::CLIMATE_MODE_HEAT_COOL:
      return MODE_AUTO;
    case climate::CLIMATE_MODE_COOL:
      return MODE_COOL;
    default:
      return this->last_mode_;
  }
}

uint8_t PanasonicClimate::remote_fan_() const {
  switch (this->fan_mode.value_or(climate::CLIMATE_FAN_AUTO)) {
    case climate::CLIMATE_FAN_QUIET:
      return FAN_QUIET;
    case climate::CLIMATE_FAN_LOW:
      return FAN_LOW;
    case climate::CLIMATE_FAN_MEDIUM:
      return FAN_MEDIUM;
    case climate::CLIMATE_FAN_MIDDLE:
      return FAN_MIDDLE;
    case climate::CLIMATE_FAN_HIGH:
      return FAN_HIGH;
    default:
      return FAN_AUTO;
  }
}

void PanasonicClimate::transmit_state() {
  AcState state{};
  state.power = this->mode != climate::CLIMATE_MODE_OFF;
  state.mode = this->remote_mode_();
  if (state.power)
    this->last_mode_ = state.mode;
  state.celsius = static_cast<uint8_t>(std::lround(this->target_temperature));
  state.fan = this->remote_fan_();
  state.swing_vertical = this->swing_mode == climate::CLIMATE_SWING_VERTICAL ? SWING_AUTO : SWING_HIGHEST;

  auto transmit = this->transmitter_->transmit();
  auto *data = transmit.get_data();
  data->set_carrier_frequency(CARRIER_HZ);
  for (int32_t timing : to_timings(encode_state(state))) {
    if (timing > 0)
      data->mark(timing);
    else
      data->space(-timing);
  }
  transmit.perform();
}

void PanasonicClimate::apply_remote_state_(const AcState &state) {
  if (state.power) {
    this->last_mode_ = state.mode;
    switch (state.mode) {
      case MODE_HEAT:
        this->mode = climate::CLIMATE_MODE_HEAT;
        break;
      case MODE_DRY:
        this->mode = climate::CLIMATE_MODE_DRY;
        break;
      case MODE_FAN:
        this->mode = climate::CLIMATE_MODE_FAN_ONLY;
        break;
      case MODE_AUTO:
        this->mode = climate::CLIMATE_MODE_HEAT_COOL;
        break;
      default:
        this->mode = climate::CLIMATE_MODE_COOL;
    }
  } else {
    this->mode = climate::CLIMATE_MODE_OFF;
  }
  if (state.mode != MODE_FAN)
    this->target_temperature = state.celsius;
  switch (state.fan) {
    case FAN_QUIET:
      this->fan_mode = climate::CLIMATE_FAN_QUIET;
      break;
    case FAN_LOW:
      this->fan_mode = climate::CLIMATE_FAN_LOW;
      break;
    case FAN_MEDIUM:
      this->fan_mode = climate::CLIMATE_FAN_MEDIUM;
      break;
    case FAN_MIDDLE:
      this->fan_mode = climate::CLIMATE_FAN_MIDDLE;
      break;
    case FAN_HIGH:
      this->fan_mode = climate::CLIMATE_FAN_HIGH;
      break;
    default:
      this->fan_mode = climate::CLIMATE_FAN_AUTO;
  }
  this->swing_mode = state.swing_vertical == SWING_AUTO ? climate::CLIMATE_SWING_VERTICAL : climate::CLIMATE_SWING_OFF;
}

bool PanasonicClimate::on_receive(remote_base::RemoteReceiveData data) {
  std::array<uint8_t, STATE_LENGTH> bytes{};
  if (!state_from_frames(frames_from_timings(data.get_raw_data()), bytes))
    return false;
  AcState state{};
  if (!decode_state(bytes, state))
    return false;
  this->apply_remote_state_(state);
  this->publish_state();
  return true;
}

}
