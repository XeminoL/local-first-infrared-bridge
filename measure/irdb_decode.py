import argparse
import statistics
from pathlib import Path

HEADER_MARK_RANGE = (3000, 4000)
BIT_MARK_MAX = 700
ONE_SPACE_MIN = 900
ONE_SPACE_MAX = 2500
FRAME_GAP_MIN = 5000


def read_signals(path):
    name = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("name:"):
            name = line[5:].strip()
        elif line.startswith("type:") and "raw" not in line:
            name = None
        elif line.startswith("data:") and name:
            yield name, [int(value) for value in line[5:].split()]


def split_frames(timings):
    frames, current = [], []
    for index in range(0, len(timings), 2):
        mark = timings[index]
        space = timings[index + 1] if index + 1 < len(timings) else 0
        current.append((mark, space))
        if space > FRAME_GAP_MIN:
            frames.append(current)
            current = []
    if current:
        frames.append(current)
    return frames


def decode_frame(frame):
    low, high = HEADER_MARK_RANGE
    if not low < frame[0][0] < high:
        return None
    bits = [1 if space > ONE_SPACE_MIN else 0 for _, space in frame[1:] if 0 < space < FRAME_GAP_MIN]
    return bytes(sum(bits[8 * k + j] << j for j in range(8)) for k in range(len(bits) // 8))


def describe(frame):
    decoded = decode_frame(frame)
    if decoded is None:
        return "preamble"
    return f"{len(decoded)}B:{decoded.hex(' ')}"


def checksum_ok(data):
    return len(data) > 1 and sum(data[:-1]) & 0xFF == data[-1]


def median_us(values):
    return f"{statistics.median(values):.0f}" if values else "-"


def timing_profile(signals):
    header_marks, header_spaces, marks, zeros, ones, gaps = [], [], [], [], [], []
    low, high = HEADER_MARK_RANGE
    for _, timings in signals:
        for index in range(0, len(timings) - 1, 2):
            mark, space = timings[index], timings[index + 1]
            if low < mark < high:
                header_marks.append(mark)
                header_spaces.append(space)
            elif mark < BIT_MARK_MAX:
                marks.append(mark)
                if space < BIT_MARK_MAX:
                    zeros.append(space)
                elif space < ONE_SPACE_MAX:
                    ones.append(space)
                elif space > FRAME_GAP_MIN:
                    gaps.append(space)
    return (f"header {median_us(header_marks)}/{median_us(header_spaces)}, mark {median_us(marks)}, "
            f"zero {median_us(zeros)}, one {median_us(ones)}, gap {median_us(gaps)} (us, median)")


def main():
    parser = argparse.ArgumentParser(description="Decode Flipper IR raw captures into bytes, LSB first.")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    for path in args.files:
        signals = list(read_signals(path))
        print(f"== {Path(path).name}")
        print(f"   {timing_profile(signals)}")
        for name, timings in signals:
            frames = split_frames(timings)
            decoded = [decode_frame(frame) for frame in frames]
            verdicts = ["ok" if checksum_ok(data) else "BAD" for data in decoded if data]
            print(f"   {name:14s} {' | '.join(describe(frame) for frame in frames)}  [checksum {' '.join(verdicts)}]")


if __name__ == "__main__":
    main()
