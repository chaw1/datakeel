// Copyright 2026 Datakeel contributors
// SPDX-License-Identifier: Apache-2.0

//! Integer-only kernels. Image decoding and dHash generation stay in Python.

mod kernel;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

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

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add_function(wrap_pyfunction!(compare, module)?)
}
