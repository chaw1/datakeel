// Copyright 2026 Datakeel contributors
// SPDX-License-Identifier: Apache-2.0

//! Reproduce the normalized training-text fingerprint without Python allocation loops.

use std::cell::RefCell;
#[cfg(test)]
use std::collections::BTreeSet;
use std::collections::HashMap;

use blake2::Blake2b;
use blake2::digest::{Digest, consts::U8};

const MAX_FEATURES: usize = 512;
const MAX_CACHED_FEATURES: usize = 65536;
thread_local! {
    static FEATURE_HASHES: RefCell<HashMap<u64, u64>> = RefCell::new(HashMap::new());
}
const SEEDS: [u64; 16] = [
    0x9E3779B185EBCA87,
    0xC2B2AE3D27D4EB4F,
    0x165667B19E3779F9,
    0x85EBCA77C2B2AE63,
    0x27D4EB2F165667C5,
    0x94D049BB133111EB,
    0xBF58476D1CE4E5B9,
    0xD6E8FEB86659FD93,
    0xA0761D6478BD642F,
    0xE7037ED1A0B428DB,
    0x8EBC6AF09C88C6E3,
    0x589965CC75374CC3,
    0x1D8E4E27C47D124F,
    0xEB44ACCAB455D165,
    0xDB4F0B9175AE2165,
    0xBBE0563303A4615F,
];

#[cfg(test)]
fn features(text: &str) -> BTreeSet<&str> {
    let mut boundaries: Vec<usize> = text.char_indices().map(|(offset, _)| offset).collect();
    if boundaries.len() <= 3 {
        return BTreeSet::from([text]);
    }
    boundaries.push(text.len());
    boundaries
        .windows(4)
        .map(|window| &text[window[0]..window[3]])
        .collect()
}

fn feature_hash(feature: &str) -> u64 {
    let bytes: [u8; 8] = Blake2b::<U8>::digest(feature.as_bytes()).into();
    u64::from_le_bytes(bytes)
}

fn packed_feature_hash(feature: u64, text: &str, cache: &mut HashMap<u64, u64>) -> u64 {
    if feature >> 63 != 0 {
        return feature_hash(text);
    }
    if let Some(&value) = cache.get(&feature) {
        return value;
    }
    let mut bytes = [0_u8; 12];
    let mut size = 0;
    for offset in [42, 21, 0] {
        let scalar = ((feature >> offset) & ((1 << 21) - 1)) as u32;
        let character = char::from_u32(scalar).expect("Packed shingles contain Unicode scalars");
        size += character.encode_utf8(&mut bytes[size..]).len();
    }
    let hash: [u8; 8] = Blake2b::<U8>::digest(&bytes[..size]).into();
    let value = u64::from_le_bytes(hash);
    if cache.len() == MAX_CACHED_FEATURES {
        cache.clear();
    }
    cache.insert(feature, value);
    value
}

pub(crate) fn fingerprint(text: &str) -> (u64, Vec<u8>) {
    let selected = shingle_values(text);
    let count = selected.len().min(MAX_FEATURES);
    let mut bits = [0_u16; 64];
    let mut minima = [u64::MAX; 16];
    FEATURE_HASHES.with_borrow_mut(|cache| {
        for feature in selected.into_iter().take(MAX_FEATURES) {
            let value = packed_feature_hash(feature, text, cache);
            for (offset, total) in bits.iter_mut().enumerate() {
                *total += ((value >> offset) & 1) as u16;
            }
            for (offset, &seed) in SEEDS.iter().enumerate() {
                let mixed = value.wrapping_mul(seed).wrapping_add(seed >> 1);
                minima[offset] = minima[offset].min(mixed);
            }
        }
    });
    let simhash = bits
        .iter()
        .enumerate()
        .fold(0_u64, |hash, (offset, &total)| {
            hash | (u64::from(usize::from(total) * 2 >= count) << offset)
        });
    let mut bands = Vec::with_capacity(8 * 17);
    for offset in (0..16).step_by(2) {
        bands.push(offset as u8);
        bands.extend_from_slice(&minima[offset].to_le_bytes());
        bands.extend_from_slice(&minima[offset + 1].to_le_bytes());
    }
    (simhash, bands)
}

fn shingle_values(text: &str) -> Vec<u64> {
    let mut values = Vec::new();
    let mut packed = 0_u64;
    let mut count = 0_usize;
    for character in text.chars() {
        // Three 21-bit Unicode scalar values fit in 63 bits without hash collisions.
        packed = ((packed << 21) | u64::from(u32::from(character))) & (u64::MAX >> 1);
        count += 1;
        if count >= 3 {
            values.push(packed);
        }
    }
    if count < 3 {
        // The high bit and length distinguish empty/short features from all trigrams.
        values.push((1_u64 << 63) | ((count as u64) << 61) | packed);
    }
    values.sort_unstable();
    values.dedup();
    values
}

pub(crate) fn shingles(text: &str) -> Vec<u8> {
    shingle_values(text)
        .into_iter()
        .flat_map(u64::to_le_bytes)
        .collect()
}

fn value_at(blob: &[u8], offset: usize) -> u64 {
    let mut bytes = [0_u8; 8];
    bytes.copy_from_slice(&blob[offset..offset + 8]);
    u64::from_le_bytes(bytes)
}

pub(crate) fn dice(left: &[u8], right: &[u8]) -> f64 {
    let mut left_offset = 0;
    let mut right_offset = 0;
    let mut intersection = 0_usize;
    while left_offset < left.len() && right_offset < right.len() {
        let left_value = value_at(left, left_offset);
        let right_value = value_at(right, right_offset);
        if left_value == right_value {
            intersection += 1;
            left_offset += 8;
            right_offset += 8;
        } else if left_value < right_value {
            left_offset += 8;
        } else {
            right_offset += 8;
        }
    }
    (2 * intersection) as f64 / ((left.len() + right.len()) / 8).max(1) as f64
}

#[cfg(test)]
mod tests {
    use super::{dice, feature_hash, features, fingerprint, shingles};

    #[test]
    fn features_use_unicode_scalars_and_preserve_short_text() {
        for text in ["", "a", "中文", "\u{20000}文\u{1f603}"] {
            assert_eq!(features(text), [text].into_iter().collect());
        }
        assert_eq!(
            features("\u{20000}文\u{1f603}字"),
            ["\u{20000}文\u{1f603}", "文\u{1f603}字"]
                .into_iter()
                .collect()
        );
    }

    #[test]
    fn blake2b_uses_eight_byte_output_parameters_and_little_endian() {
        assert_eq!(feature_hash(""), 0xb4b2797457a0a6e4);
        assert_eq!(feature_hash("abc"), 0x5995d533d814bbd8);
    }

    #[test]
    fn bands_are_fixed_width_and_include_the_original_offsets() {
        let (hashed, bands) = fingerprint("");
        assert_eq!(hashed, feature_hash(""));
        assert_eq!(bands.len(), 136);
        for (index, band) in bands.chunks_exact(17).enumerate() {
            assert_eq!(band[0], (index * 2) as u8);
        }
    }

    #[test]
    fn repeated_character_features_are_counted_once() {
        assert_eq!(fingerprint("aaa"), fingerprint("aaaaaaaaaaa"));
    }

    #[test]
    fn packed_shingles_preserve_scalar_width_and_short_lengths() {
        for text in ["", "a", "ab", "abc", "\u{20000}文\u{1f603}", "a\0b\0c"] {
            assert_eq!(shingles(text).len() / 8, features(text).len());
            assert_eq!(dice(&shingles(text), &shingles(text)), 1.0);
        }
        for (left, right) in [("", "\0"), ("a", "\0a"), ("ab", "\0ab")] {
            assert_eq!(dice(&shingles(left), &shingles(right)), 0.0);
        }
    }

    #[test]
    fn packed_dice_matches_full_string_set_overlap() {
        let cases = [
            ("abcdef", "abcxyz"),
            ("中文字符顺序测试", "中文字符逆序测试"),
            ("\u{20000}文\u{1f603}字", "文\u{1f603}字符"),
            ("a\0b\0c\0d", "b\0c\0d\0e"),
        ];
        for (left, right) in cases {
            let left_features = features(left);
            let right_features = features(right);
            let expected = (2 * left_features.intersection(&right_features).count()) as f64
                / (left_features.len() + right_features.len()) as f64;
            assert_eq!(dice(&shingles(left), &shingles(right)), expected);
        }
    }
}
