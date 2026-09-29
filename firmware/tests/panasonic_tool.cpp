#include <cstdio>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>

#include "panasonic_frame.h"

using namespace esphome::panasonic_ac;

static const uint8_t MODES[] = {MODE_AUTO, MODE_DRY, MODE_COOL, MODE_HEAT, MODE_FAN};
static const uint8_t FANS[] = {FAN_QUIET, FAN_LOW, FAN_MEDIUM, FAN_MIDDLE, FAN_HIGH, FAN_AUTO};
static const uint8_t SWINGS[] = {SWING_HIGHEST, 0x2, 0x3, 0x4, 0x5, SWING_AUTO};

static void print_hex(const std::array<uint8_t, STATE_LENGTH> &bytes) {
  for (uint8_t byte : bytes)
    std::printf("%02x", byte);
}

static int sweep() {
  for (int power = 0; power <= 1; power++)
    for (uint8_t mode : MODES)
      for (uint8_t celsius = MIN_CELSIUS; celsius <= MAX_CELSIUS; celsius++)
        for (uint8_t fan : FANS)
          for (uint8_t swing : SWINGS) {
            AcState state{power == 1, mode, celsius, fan, swing};
            auto bytes = encode_state(state);
            std::printf("%d %u %u %u %u ", power, mode, celsius, fan, swing);
            print_hex(bytes);
            for (int32_t timing : to_timings(bytes))
              std::printf(" %d", timing);
            std::printf("\n");
          }
  return 0;
}

static int decode_lines() {
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream stream(line);
    std::vector<int32_t> timings;
    int32_t value;
    for (size_t index = 0; stream >> value; index++)
      timings.push_back(index % 2 == 0 ? value : -value);
    std::array<uint8_t, STATE_LENGTH> bytes{};
    if (!state_from_frames(frames_from_timings(timings), bytes)) {
      std::printf("none\n");
      continue;
    }
    AcState state{};
    decode_state(bytes, state);
    print_hex(bytes);
    std::printf(" %d %u %u %u %u\n", state.power, state.mode, state.celsius, state.fan, state.swing_vertical);
  }
  return 0;
}

int main(int argc, char **argv) {
  if (argc == 2 && std::strcmp(argv[1], "sweep") == 0)
    return sweep();
  if (argc == 2 && std::strcmp(argv[1], "decode") == 0)
    return decode_lines();
  std::fprintf(stderr, "usage: panasonic_tool sweep | decode < timings\n");
  return 2;
}
