#include "panasonic_frame.h"

#include <algorithm>

namespace esphome::panasonic_ac {

uint8_t checksum(const std::array<uint8_t, STATE_LENGTH> &state) {
  uint8_t sum = CHECKSUM_START;
  for (size_t i = 0; i < CHECKSUM_BYTE; i++)
    sum += state[i];
  return sum;
}

std::array<uint8_t, STATE_LENGTH> encode_state(const AcState &state) {
  std::array<uint8_t, STATE_LENGTH> bytes = RKR_TEMPLATE;
  uint8_t celsius = state.mode == MODE_FAN ? FAN_MODE_CELSIUS : state.celsius;
  celsius = std::min(std::max(celsius, MIN_CELSIUS), MAX_CELSIUS);
  bytes[MODE_BYTE] = static_cast<uint8_t>(state.mode << 4) | RKR_MODEL_FLAG | (state.power ? POWER_BIT : 0);
  bytes[TEMPERATURE_BYTE] = static_cast<uint8_t>(celsius << 1);
  bytes[FAN_SWING_BYTE] = static_cast<uint8_t>((state.fan + FAN_OFFSET) << 4) | (state.swing_vertical & 0x0F);
  bytes[CHECKSUM_BYTE] = checksum(bytes);
  return bytes;
}

bool decode_state(const std::array<uint8_t, STATE_LENGTH> &bytes, AcState &state) {
  if (bytes[CHECKSUM_BYTE] != checksum(bytes))
    return false;
  if (!std::equal(RKR_TEMPLATE.begin(), RKR_TEMPLATE.begin() + FIRST_SECTION_LENGTH + 5, bytes.begin()))
    return false;
  state.power = bytes[MODE_BYTE] & POWER_BIT;
  state.mode = bytes[MODE_BYTE] >> 4;
  state.celsius = (bytes[TEMPERATURE_BYTE] >> 1) & 0x1F;
  state.fan = static_cast<uint8_t>((bytes[FAN_SWING_BYTE] >> 4) - FAN_OFFSET);
  state.swing_vertical = bytes[FAN_SWING_BYTE] & 0x0F;
  return true;
}

static void append_section(std::vector<int32_t> &timings, const uint8_t *bytes, size_t length) {
  timings.push_back(HEADER_MARK_US);
  timings.push_back(-static_cast<int32_t>(HEADER_SPACE_US));
  for (size_t i = 0; i < length; i++) {
    for (uint8_t bit = 0; bit < 8; bit++) {
      timings.push_back(BIT_MARK_US);
      bool one = (bytes[i] >> bit) & 1;
      timings.push_back(-static_cast<int32_t>(one ? ONE_SPACE_US : ZERO_SPACE_US));
    }
  }
  timings.push_back(BIT_MARK_US);
}

std::vector<int32_t> to_timings(const std::array<uint8_t, STATE_LENGTH> &bytes) {
  std::vector<int32_t> timings;
  append_section(timings, bytes.data(), FIRST_SECTION_LENGTH);
  timings.push_back(-static_cast<int32_t>(SECTION_GAP_US));
  append_section(timings, bytes.data() + FIRST_SECTION_LENGTH, SECOND_SECTION_LENGTH);
  return timings;
}

std::vector<std::vector<uint8_t>> frames_from_timings(const std::vector<int32_t> &timings) {
  std::vector<std::vector<uint8_t>> frames;
  size_t i = 0;
  while (i + 1 < timings.size()) {
    bool header = timings[i] > static_cast<int32_t>(HEADER_THRESHOLD_US) &&
                  -timings[i + 1] > static_cast<int32_t>(HEADER_THRESHOLD_US / 2);
    if (!header) {
      i++;
      continue;
    }
    i += 2;
    std::vector<uint8_t> frame;
    uint8_t current = 0;
    uint8_t bits = 0;
    while (i + 1 < timings.size()) {
      int32_t mark = timings[i];
      int32_t space = -timings[i + 1];
      if (mark <= 0 || mark >= static_cast<int32_t>(BIT_THRESHOLD_US) || space <= 0 ||
          space >= static_cast<int32_t>(HEADER_THRESHOLD_US))
        break;
      if (space > static_cast<int32_t>(BIT_THRESHOLD_US))
        current |= static_cast<uint8_t>(1 << bits);
      bits++;
      i += 2;
      if (bits == 8) {
        frame.push_back(current);
        current = 0;
        bits = 0;
      }
    }
    if (!frame.empty())
      frames.push_back(frame);
  }
  return frames;
}

bool state_from_frames(const std::vector<std::vector<uint8_t>> &frames, std::array<uint8_t, STATE_LENGTH> &bytes) {
  for (const auto &frame : frames) {
    if (frame.size() != SECOND_SECTION_LENGTH)
      continue;
    std::copy(RKR_TEMPLATE.begin(), RKR_TEMPLATE.begin() + FIRST_SECTION_LENGTH, bytes.begin());
    std::copy(frame.begin(), frame.end(), bytes.begin() + FIRST_SECTION_LENGTH);
    AcState ignored{};
    if (decode_state(bytes, ignored))
      return true;
  }
  return false;
}

}
