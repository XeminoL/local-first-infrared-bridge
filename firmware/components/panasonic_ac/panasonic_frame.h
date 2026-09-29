#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace esphome::panasonic_ac {

const size_t STATE_LENGTH = 27;
const size_t FIRST_SECTION_LENGTH = 8;
const size_t SECOND_SECTION_LENGTH = STATE_LENGTH - FIRST_SECTION_LENGTH;

const uint32_t CARRIER_HZ = 36700;
const uint32_t HEADER_MARK_US = 3456;
const uint32_t HEADER_SPACE_US = 1728;
const uint32_t BIT_MARK_US = 432;
const uint32_t ONE_SPACE_US = 1296;
const uint32_t ZERO_SPACE_US = 432;
const uint32_t SECTION_GAP_US = 10000;
const uint32_t BIT_THRESHOLD_US = (ONE_SPACE_US + ZERO_SPACE_US) / 2;
const uint32_t HEADER_THRESHOLD_US = 2500;
const uint8_t CHECKSUM_START = 0xF4;

const uint8_t MODE_AUTO = 0;
const uint8_t MODE_DRY = 2;
const uint8_t MODE_COOL = 3;
const uint8_t MODE_HEAT = 4;
const uint8_t MODE_FAN = 6;

const uint8_t FAN_QUIET = 0;
const uint8_t FAN_LOW = 1;
const uint8_t FAN_MEDIUM = 2;
const uint8_t FAN_MIDDLE = 3;
const uint8_t FAN_HIGH = 4;
const uint8_t FAN_AUTO = 7;
const uint8_t FAN_OFFSET = 3;

const uint8_t SWING_HIGHEST = 0x1;
const uint8_t SWING_AUTO = 0xF;

const uint8_t MIN_CELSIUS = 16;
const uint8_t MAX_CELSIUS = 30;
const uint8_t FAN_MODE_CELSIUS = 27;

const size_t MODE_BYTE = 13;
const size_t TEMPERATURE_BYTE = 14;
const size_t FAN_SWING_BYTE = 16;
const size_t CHECKSUM_BYTE = STATE_LENGTH - 1;
const uint8_t RKR_MODEL_FLAG = 0x08;
const uint8_t POWER_BIT = 0x01;

const std::array<uint8_t, STATE_LENGTH> RKR_TEMPLATE = {0x02, 0x20, 0xE0, 0x04, 0x00, 0x00, 0x00, 0x06, 0x02,
                                                        0x20, 0xE0, 0x04, 0x00, 0x38, 0x38, 0x80, 0x71, 0x00,
                                                        0x00, 0x0E, 0xE0, 0x00, 0x00, 0x89, 0x00, 0x06, 0xE4};

struct AcState {
  bool power;
  uint8_t mode;
  uint8_t celsius;
  uint8_t fan;
  uint8_t swing_vertical;
};

uint8_t checksum(const std::array<uint8_t, STATE_LENGTH> &state);

std::array<uint8_t, STATE_LENGTH> encode_state(const AcState &state);

bool decode_state(const std::array<uint8_t, STATE_LENGTH> &bytes, AcState &state);

std::vector<int32_t> to_timings(const std::array<uint8_t, STATE_LENGTH> &bytes);

std::vector<std::vector<uint8_t>> frames_from_timings(const std::vector<int32_t> &timings);

bool state_from_frames(const std::vector<std::vector<uint8_t>> &frames, std::array<uint8_t, STATE_LENGTH> &bytes);

}
