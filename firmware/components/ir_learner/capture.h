#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace esphome::ir_learner {

std::vector<uint32_t> durations_between(const uint32_t *edge_times, size_t edge_count);

void merge_glitches(std::vector<uint32_t> &durations, uint32_t shortest_pulse_us);

struct EchoComparison {
  bool same_length;
  size_t worst_index;
  uint32_t worst_difference_us;
  bool agrees;
};

EchoComparison compare_echo(const std::vector<uint32_t> &sent, const std::vector<uint32_t> &heard,
                            float tolerance, uint32_t slack_us);

uint32_t total_duration(const std::vector<uint32_t> &durations);

int32_t mark_shortening(const std::vector<uint32_t> &sent, const std::vector<uint32_t> &heard);

void undo_mark_shortening(std::vector<uint32_t> &durations, int32_t shortening_us);

void snap_to_clusters(std::vector<uint32_t> &durations, float spread);

}
