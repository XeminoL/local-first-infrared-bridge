#include "capture.h"

#include <algorithm>

namespace esphome::ir_learner {

std::vector<uint32_t> durations_between(const uint32_t *edge_times, size_t edge_count) {
  std::vector<uint32_t> durations;
  if (edge_count < 2)
    return durations;
  durations.reserve(edge_count - 1);
  for (size_t i = 1; i < edge_count; i++)
    durations.push_back(edge_times[i] - edge_times[i - 1]);
  if (durations.size() % 2 == 0)
    durations.pop_back();
  return durations;
}

void merge_glitches(std::vector<uint32_t> &durations, uint32_t shortest_pulse_us) {
  size_t i = 0;
  while (i < durations.size()) {
    if (durations[i] >= shortest_pulse_us) {
      i++;
      continue;
    }
    bool is_first = i == 0;
    bool is_last = i + 1 == durations.size();
    if (is_first) {
      size_t drop = durations.size() >= 2 ? 2 : 1;
      durations.erase(durations.begin(), durations.begin() + drop);
      continue;
    }
    if (is_last) {
      durations.erase(durations.end() - 2, durations.end());
      break;
    }
    durations[i - 1] += durations[i] + durations[i + 1];
    durations.erase(durations.begin() + i, durations.begin() + i + 2);
    i--;
  }
}

EchoComparison compare_echo(const std::vector<uint32_t> &sent, const std::vector<uint32_t> &heard,
                            float tolerance, uint32_t slack_us) {
  EchoComparison result{sent.size() == heard.size(), 0, 0, false};
  if (!result.same_length || sent.empty())
    return result;
  bool all_within = true;
  for (size_t i = 0; i < sent.size(); i++) {
    uint32_t difference = sent[i] > heard[i] ? sent[i] - heard[i] : heard[i] - sent[i];
    uint32_t allowed = static_cast<uint32_t>(sent[i] * tolerance) + slack_us;
    if (difference > result.worst_difference_us) {
      result.worst_difference_us = difference;
      result.worst_index = i;
    }
    if (difference > allowed)
      all_within = false;
  }
  result.agrees = all_within;
  return result;
}

uint32_t total_duration(const std::vector<uint32_t> &durations) {
  uint32_t total = 0;
  for (uint32_t duration : durations)
    total += duration;
  return total;
}

int32_t mark_shortening(const std::vector<uint32_t> &sent, const std::vector<uint32_t> &heard) {
  int64_t total = 0;
  size_t marks = 0;
  for (size_t i = 0; i < sent.size() && i < heard.size(); i += 2) {
    total += static_cast<int64_t>(sent[i]) - static_cast<int64_t>(heard[i]);
    marks++;
  }
  return marks == 0 ? 0 : static_cast<int32_t>(total / static_cast<int64_t>(marks));
}

static void snap_every_other(std::vector<uint32_t> &durations, size_t first, float spread) {
  std::vector<uint32_t> sorted;
  for (size_t i = first; i < durations.size(); i += 2)
    sorted.push_back(durations[i]);
  if (sorted.empty())
    return;
  std::sort(sorted.begin(), sorted.end());
  std::vector<std::pair<uint32_t, uint32_t>> ranges;
  size_t start = 0;
  for (size_t i = 1; i <= sorted.size(); i++) {
    if (i < sorted.size() && sorted[i] <= sorted[i - 1] * (1.0f + spread))
      continue;
    ranges.emplace_back(sorted[start], sorted[start + (i - start) / 2]);
    start = i;
  }
  for (size_t i = first; i < durations.size(); i += 2) {
    auto range = std::upper_bound(ranges.begin(), ranges.end(), durations[i],
                                  [](uint32_t value, const std::pair<uint32_t, uint32_t> &cluster) {
                                    return value < cluster.first;
                                  });
    durations[i] = std::prev(range)->second;
  }
}

void snap_to_clusters(std::vector<uint32_t> &durations, float spread) {
  snap_every_other(durations, 0, spread);
  snap_every_other(durations, 1, spread);
}

void undo_mark_shortening(std::vector<uint32_t> &durations, int32_t shortening_us) {
  for (size_t i = 0; i < durations.size(); i++) {
    int64_t corrected = static_cast<int64_t>(durations[i]) + (i % 2 == 0 ? shortening_us : -shortening_us);
    durations[i] = static_cast<uint32_t>(corrected < 1 ? 1 : corrected);
  }
}

}
