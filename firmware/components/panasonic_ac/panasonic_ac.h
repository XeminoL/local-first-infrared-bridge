#pragma once

#include "esphome/components/climate_ir/climate_ir.h"
#include "panasonic_frame.h"

namespace esphome::panasonic_ac {

class PanasonicClimate final : public climate_ir::ClimateIR {
 public:
  PanasonicClimate()
      : climate_ir::ClimateIR(MIN_CELSIUS, MAX_CELSIUS, 1.0f, true, true,
                              {climate::CLIMATE_FAN_AUTO, climate::CLIMATE_FAN_QUIET, climate::CLIMATE_FAN_LOW,
                               climate::CLIMATE_FAN_MEDIUM, climate::CLIMATE_FAN_MIDDLE, climate::CLIMATE_FAN_HIGH},
                              {climate::CLIMATE_SWING_OFF, climate::CLIMATE_SWING_VERTICAL}) {}

 protected:
  void transmit_state() override;
  bool on_receive(remote_base::RemoteReceiveData data) override;

  uint8_t remote_mode_() const;
  uint8_t remote_fan_() const;
  void apply_remote_state_(const AcState &state);

  uint8_t last_mode_{MODE_COOL};
};

}
