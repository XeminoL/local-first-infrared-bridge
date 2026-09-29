#include <cstdio>
#include <cstdlib>
#include <string>

#include "panasonic_frame.h"

using namespace esphome::panasonic_ac;

static int failures = 0;
static int checks = 0;

static void expect(const char *label, bool condition) {
  checks++;
  if (condition)
    return;
  failures++;
  std::printf("FAIL %s\n", label);
}

static std::string hex(const std::array<uint8_t, STATE_LENGTH> &bytes) {
  std::string text;
  char pair[3];
  for (uint8_t byte : bytes) {
    std::snprintf(pair, sizeof(pair), "%02x", byte);
    text += pair;
  }
  return text;
}

int main() {
  const std::string real_remote_off = "0220e004000000060220e004003838807100000ee00000890006e4";
  const std::string real_remote_on = "0220e004000000060220e004003938807100000ee00000890006e5";
  AcState cool_28{false, MODE_COOL, 28, FAN_HIGH, SWING_HIGHEST};
  expect("off frame equals the real remote byte for byte", hex(encode_state(cool_28)) == real_remote_off);
  cool_28.power = true;
  expect("on frame equals the real remote byte for byte", hex(encode_state(cool_28)) == real_remote_on);

  AcState heat{true, MODE_HEAT, 22, FAN_AUTO, SWING_AUTO};
  auto bytes = encode_state(heat);
  std::array<uint8_t, STATE_LENGTH> parsed{};
  expect("timings parse back to the same bytes", state_from_frames(frames_from_timings(to_timings(bytes)), parsed));
  expect("parsed bytes match", parsed == bytes);
  AcState back{};
  expect("parsed state is valid", decode_state(parsed, back));
  expect("parsed state matches", back.power && back.mode == MODE_HEAT && back.celsius == 22 && back.fan == FAN_AUTO &&
                                     back.swing_vertical == SWING_AUTO);

  AcState fan_only{true, MODE_FAN, 18, FAN_LOW, SWING_HIGHEST};
  AcState fan_back{};
  decode_state(encode_state(fan_only), fan_back);
  expect("fan mode sends 27 C like the remote", fan_back.celsius == FAN_MODE_CELSIUS);

  AcState too_hot{true, MODE_COOL, 40, FAN_LOW, SWING_HIGHEST};
  AcState clamped{};
  decode_state(encode_state(too_hot), clamped);
  expect("temperature is clamped to 30 C", clamped.celsius == MAX_CELSIUS);

  auto broken = encode_state(heat);
  broken[TEMPERATURE_BYTE] ^= 0x02;
  AcState ignored{};
  expect("bad checksum is rejected", !decode_state(broken, ignored));

  std::printf("%d/%d checks passed\n", checks - failures, checks);
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
