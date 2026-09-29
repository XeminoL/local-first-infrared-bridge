#include <cstdio>
#include <cstdlib>
#include <vector>

#include "capture.h"

using esphome::ir_learner::compare_echo;
using esphome::ir_learner::durations_between;
using esphome::ir_learner::mark_shortening;
using esphome::ir_learner::merge_glitches;
using esphome::ir_learner::snap_to_clusters;
using esphome::ir_learner::undo_mark_shortening;
using esphome::ir_learner::total_duration;
using Timings = std::vector<uint32_t>;

static int failures = 0;
static int checks = 0;

static void expect_timings(const char *label, const Timings &actual, const Timings &expected) {
  checks++;
  if (actual == expected)
    return;
  failures++;
  std::printf("FAIL %s: got", label);
  for (uint32_t value : actual)
    std::printf(" %u", value);
  std::printf(", expected");
  for (uint32_t value : expected)
    std::printf(" %u", value);
  std::printf("\n");
}

static void expect_true(const char *label, bool condition) {
  checks++;
  if (condition)
    return;
  failures++;
  std::printf("FAIL %s\n", label);
}

static Timings merged(Timings durations) {
  merge_glitches(durations, 100);
  return durations;
}

int main() {
  const uint32_t edges[] = {1000, 10000, 14500, 15060, 16750, 17310};
  expect_timings("edges to durations", durations_between(edges, 6), {9000, 4500, 560, 1690, 560});
  expect_timings("trailing space is dropped", durations_between(edges, 5), {9000, 4500, 560});
  expect_timings("one edge gives nothing", durations_between(edges, 1), {});

  expect_timings("clean code is untouched", merged({9000, 4500, 560, 1690, 560}), {9000, 4500, 560, 1690, 560});
  expect_timings("dropout inside a mark", merged({9000, 4500, 300, 40, 220, 1690, 560}), {9000, 4500, 560, 1690, 560});
  expect_timings("spike inside a space", merged({9000, 4500, 560, 800, 30, 860, 560}), {9000, 4500, 560, 1690, 560});
  expect_timings("noise before the code", merged({60, 2000, 9000, 4500, 560}), {9000, 4500, 560});
  expect_timings("noise after the code", merged({9000, 4500, 560, 3000, 80}), {9000, 4500, 560});
  expect_timings("two dropouts in a row", merged({9000, 4500, 200, 50, 150, 40, 120, 1690, 560}),
                 {9000, 4500, 560, 1690, 560});
  expect_timings("only noise", merged({50}), {});

  Timings sent = {9000, 4500, 560, 1690, 560};
  auto close = compare_echo(sent, {9100, 4400, 640, 1600, 610}, 0.4f, 150);
  expect_true("echo within tolerance agrees", close.agrees && close.same_length);
  auto stretched = compare_echo(sent, {9000, 4500, 560, 1690, 1400}, 0.4f, 150);
  expect_true("echo with one wrong pulse disagrees", !stretched.agrees && stretched.worst_index == 4);
  auto shorter = compare_echo(sent, {9000, 4500, 560}, 0.4f, 150);
  expect_true("echo with missing pulses disagrees", !shorter.agrees && !shorter.same_length);
  expect_true("empty echo disagrees", !compare_echo(sent, {}, 0.4f, 150).agrees);

  expect_true("total duration", total_duration(sent) == 16310);

  Timings heard = {8945, 4555, 505, 1745, 505};
  expect_true("marks shortened by 55 us", mark_shortening(sent, heard) == 55);
  undo_mark_shortening(heard, 55);
  expect_timings("shortening undone", heard, sent);
  Timings tiny = {40, 30, 40};
  undo_mark_shortening(tiny, -60);
  expect_timings("correction never goes below 1 us", tiny, {1, 90, 1});

  Timings jittery = {9020, 4480, 410, 1650, 450, 520, 500, 1720, 545, 575, 600, 530, 650};
  snap_to_clusters(jittery, 0.15f);
  expect_timings("jitter spread wide still forms one cluster", jittery,
                 {9020, 4480, 545, 1720, 545, 530, 545, 1720, 545, 530, 545, 530, 545});
  Timings clean = {9000, 4500, 560, 1690, 560, 560, 560};
  snap_to_clusters(clean, 0.15f);
  expect_timings("clean code keeps its values", clean, {9000, 4500, 560, 1690, 560, 560, 560});
  Timings two_gaps = {3500, 25100, 3500, 35000, 3500, 25400, 3500};
  snap_to_clusters(two_gaps, 0.15f);
  expect_timings("25 ms and 35 ms gaps stay apart", two_gaps, {3500, 25400, 3500, 35000, 3500, 25400, 3500});

  std::printf("%d/%d checks passed\n", checks - failures, checks);
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
