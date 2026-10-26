// Copyright 2026 Datakeel contributors
// SPDX-License-Identifier: Apache-2.0

use rayon::prelude::*;

type Pair = (usize, usize, u32);

#[derive(Clone, Copy)]
struct Segment {
    offset: u32,
    mask: u64,
}

impl Segment {
    fn key(self, hash: u64) -> u64 {
        (hash >> self.offset) & self.mask
    }
}

fn segments(threshold: u32) -> Vec<Segment> {
    let count = threshold + 1;
    let mut offset = 0;
    (0..count)
        .map(|index| {
            let width = 64 / count + u32::from(index < 64 % count);
            let mask = u64::MAX >> (64 - width);
            let segment = Segment { offset, mask };
            offset += width;
            segment
        })
        .collect()
}

fn bucket_pairs(
    hashes: &[u64],
    threshold: u32,
    segment: Segment,
    previous: &[Segment],
) -> Vec<Pair> {
    let mut index: Vec<(u64, usize)> = hashes
        .iter()
        .enumerate()
        .map(|(index, &hash)| (segment.key(hash), index))
        .collect();
    index.sort_unstable();
    let mut groups = Vec::new();
    let mut start = 0;
    while start < index.len() {
        let mut end = start + 1;
        while end < index.len() && index[end].0 == index[start].0 {
            end += 1;
        }
        if end - start > 1 {
            groups.push(&index[start..end]);
        }
        start = end;
    }
    groups
        .par_iter()
        .flat_map_iter(|group| {
            group
                .iter()
                .enumerate()
                .flat_map(move |(position, &(_, left))| {
                    group[position + 1..].iter().filter_map(move |&(_, right)| {
                        let distance = (hashes[left] ^ hashes[right]).count_ones();
                        if distance > threshold
                            || previous
                                .iter()
                                .any(|prior| prior.key(hashes[left]) == prior.key(hashes[right]))
                        {
                            return None;
                        }
                        Some((left.min(right), left.max(right), distance))
                    })
                })
        })
        .collect()
}

pub(crate) fn pairs(hashes: &[u64], threshold: u32, prefix_bits: u32, exact: bool) -> Vec<Pair> {
    let mut output = if exact && threshold < 64 {
        let segments = segments(threshold);
        segments
            .par_iter()
            .enumerate()
            .flat_map_iter(|(index, &segment)| {
                bucket_pairs(hashes, threshold, segment, &segments[..index])
            })
            .collect()
    } else {
        let bits = if exact { 0 } else { prefix_bits };
        let segment = Segment {
            offset: if bits == 0 { 0 } else { 64 - bits },
            mask: if bits == 0 {
                0
            } else {
                u64::MAX >> (64 - bits)
            },
        };
        bucket_pairs(hashes, threshold, segment, &[])
    };
    output.sort_unstable();
    output
}

#[cfg(test)]
mod tests {
    use super::{pairs, segments};

    fn brute(hashes: &[u64], threshold: u32) -> Vec<(usize, usize, u32)> {
        (0..hashes.len())
            .flat_map(|left| {
                (left + 1..hashes.len()).filter_map(move |right| {
                    let distance = (hashes[left] ^ hashes[right]).count_ones();
                    (distance <= threshold).then_some((left, right, distance))
                })
            })
            .collect()
    }

    #[test]
    fn empty_and_single_inputs_have_no_pairs() {
        for exact in [false, true] {
            assert!(pairs(&[], 8, 4, exact).is_empty());
            assert!(pairs(&[7], 8, 4, exact).is_empty());
        }
    }

    #[test]
    fn identical_hashes_produce_every_pair_once() {
        for threshold in [0, 1, 8, 63, 64] {
            for exact in [false, true] {
                assert_eq!(pairs(&[7; 6], threshold, 4, exact), brute(&[7; 6], 0));
            }
        }
    }

    #[test]
    fn threshold_includes_boundary_and_excludes_next_distance() {
        let hashes = [0, 0xff, 0x1ff];
        for exact in [false, true] {
            assert_eq!(pairs(&hashes, 8, 4, exact), vec![(0, 1, 8), (1, 2, 1)]);
        }
    }

    #[test]
    fn maximum_threshold_matches_all_hashes_in_exact_mode() {
        let hashes = [0, u64::MAX, 1, 1 << 63];
        assert_eq!(pairs(&hashes, 64, 64, true), brute(&hashes, 64));
        assert!(pairs(&hashes, 64, 64, false).is_empty());
    }

    #[test]
    fn exact_finds_pairs_across_prefix_boundaries() {
        let hashes = [0, 1 << 63, 3, u64::MAX];
        assert_eq!(pairs(&hashes, 1, 4, false), vec![]);
        assert_eq!(pairs(&hashes, 1, 4, true), brute(&hashes, 1));
    }

    #[test]
    fn segments_cover_each_bit_exactly_once() {
        for threshold in 0..64 {
            let segments = segments(threshold);
            assert_eq!(segments.len(), threshold as usize + 1);
            let mut combined = 0;
            for segment in segments {
                let bits = segment.mask << segment.offset;
                assert_eq!(combined & bits, 0);
                combined |= bits;
            }
            assert_eq!(combined, u64::MAX);
        }
    }

    #[test]
    fn exact_randomized_results_equal_brute_force_for_every_threshold() {
        let mut state = 0x1234_5678_9abc_def0u64;
        let mut hashes = Vec::new();
        for _ in 0..96 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            hashes.extend([state, state ^ 0xff, state]);
        }
        for threshold in 0..=64 {
            assert_eq!(
                pairs(&hashes, threshold, 4, true),
                brute(&hashes, threshold)
            );
        }
    }

    #[test]
    fn prefix_zero_equals_brute_and_full_width_keeps_only_identical() {
        let hashes = [u64::MAX, 7, 7, 0, 1 << 63];
        assert_eq!(pairs(&hashes, 8, 0, false), brute(&hashes, 8));
        assert_eq!(pairs(&hashes, 64, 64, false), vec![(1, 2, 0)]);
    }
}
