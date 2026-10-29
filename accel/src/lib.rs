// Copyright 2026 Datakeel contributors
// SPDX-License-Identifier: Apache-2.0

//! Comparison and training fingerprint kernels. Image decoding stays in Python.

mod kernel;
mod training;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Return canonical input-index pairs sorted lexicographically.
#[pyfunction]
#[pyo3(signature = (hashes, threshold=8, prefix_bits=4, mode="prefix"))]
fn compare(
    py: Python<'_>,
    hashes: Vec<u64>,
    threshold: u32,
    prefix_bits: u32,
    mode: &str,
) -> PyResult<Vec<(usize, usize, u32)>> {
    if threshold > 64 || prefix_bits > 64 {
        return Err(PyValueError::new_err(
            "threshold and prefix_bits must be between 0 and 64",
        ));
    }
    let exact = match mode {
        "prefix" => false,
        "exact" => true,
        _ => return Err(PyValueError::new_err("mode must be 'prefix' or 'exact'")),
    };
    Ok(py.detach(|| kernel::pairs(&hashes, threshold, prefix_bits, exact)))
}

/// Fingerprint already-normalized training text and pack eight original MinHash bands.
#[pyfunction]
fn training_fingerprint(py: Python<'_>, text: &str) -> (u64, Py<PyBytes>) {
    let (simhash, bands) = py.detach(|| training::fingerprint(text));
    (simhash, PyBytes::new(py, &bands).unbind())
}

/// Pack exact Unicode-scalar trigrams as canonical sorted unsigned integer bytes.
#[pyfunction]
fn training_shingles(py: Python<'_>, text: &str) -> Py<PyBytes> {
    let packed = py.detach(|| training::shingles(text));
    PyBytes::new(py, &packed).unbind()
}

/// Measure exact Dice overlap of canonical packed trigram sets.
#[pyfunction]
fn training_dice(py: Python<'_>, left: &[u8], right: &[u8]) -> PyResult<f64> {
    if left.len() % 8 != 0 || right.len() % 8 != 0 {
        return Err(PyValueError::new_err(
            "Packed training shingles must contain complete unsigned 64-bit values",
        ));
    }
    Ok(py.detach(|| training::dice(left, right)))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add_function(wrap_pyfunction!(compare, module)?)?;
    module.add_function(wrap_pyfunction!(training_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(training_shingles, module)?)?;
    module.add_function(wrap_pyfunction!(training_dice, module)?)
}
