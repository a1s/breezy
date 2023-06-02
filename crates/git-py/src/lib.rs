use pyo3::prelude::*;
use std::path::PathBuf;

#[pyfunction]
fn bzr_url_to_git_url(location: &str) -> PyResult<(String, Option<String>, Option<String>)> {
    let (url, revno, branch) = breezy_git::bzr_url_to_git_url(location)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(("Invalid URL",)))?;
    Ok((url, revno, branch))
}

#[pyfunction]
fn get_cache_dir() -> PyResult<PathBuf> {
    breezy_git::get_cache_dir().map_err(|e| -> PyErr { e.into() })
}

#[pymodule]
pub fn _git_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_wrapped(wrap_pyfunction!(bzr_url_to_git_url))?;
    m.add_wrapped(wrap_pyfunction!(get_cache_dir))?;
    Ok(())
}
