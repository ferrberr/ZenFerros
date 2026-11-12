//! Invoke the host C toolchain without a shell. Publish only successful builds.
use anyhow::{bail, Context, Result};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIR: AtomicU64 = AtomicU64::new(0);
pub struct ScratchDir(pub PathBuf);
impl ScratchDir {
    pub fn new(parent: &Path) -> Result<Self> {
        for _ in 0..100 {
            let id = NEXT_DIR.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(".zen-build-{}-{id}", std::process::id()));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e).context("cannot create build directory"),
            }
        }
        bail!("cannot allocate build directory")
    }
}
impl Drop for ScratchDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
#[derive(Debug, Clone, Copy)]
pub enum Artifact {
    Executable,
    Object,
    CSource,
}

pub fn build(c_source: &str, output: &Path, release: bool) -> Result<()> {
    build_artifact(
        c_source,
        output,
        release,
        Artifact::Executable,
        crate::mvp::Mode::Hosted,
    )
}

pub fn build_artifact(
    c_source: &str,
    output: &Path,
    release: bool,
    artifact: Artifact,
    mode: crate::mvp::Mode,
) -> Result<()> {
    let freestanding = matches!(mode, crate::mvp::Mode::Freestanding);
    if freestanding && matches!(artifact, Artifact::Executable) {
        bail!("freestanding builds require --emit obj or --emit c; link objects with your entry point and linker script");
    }
    if freestanding && !cfg!(target_arch = "x86_64") {
        bail!("the freestanding backend currently requires an x86_64 host C toolchain");
    }
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let scratch = ScratchDir::new(parent)?;
    let source = scratch.0.join("program.c");
    let executable = scratch.0.join("program");
    fs::write(&source, c_source).context("cannot write generated C")?;
    if matches!(artifact, Artifact::CSource) {
        fs::rename(&source, output)
            .with_context(|| format!("cannot publish {}", output.display()))?;
        return Ok(());
    }
    let cc = std::env::var_os("CC").unwrap_or_else(|| "cc".into());
    let mut command = Command::new(cc);
    command
        .arg("-std=c11")
        .arg(if release { "-O2" } else { "-O0" })
        .arg("-Wall")
        .arg("-Wextra");
    if matches!(artifact, Artifact::Object) {
        command.arg("-c");
    }
    if freestanding {
        command.args([
            "-ffreestanding",
            "-fno-builtin",
            "-fno-stack-protector",
            "-fno-pic",
            "-fno-pie",
            "-fno-common",
            "-m64",
            "-mno-red-zone",
            "-mgeneral-regs-only",
            "-mcmodel=kernel",
            "-fno-asynchronous-unwind-tables",
            "-fno-unwind-tables",
            "-fno-ident",
            "-fno-tree-loop-distribute-patterns",
            "-ffunction-sections",
            "-fdata-sections",
        ]);
    }
    let result = command
        .arg(&source)
        .arg("-o")
        .arg(&executable)
        .output()
        .context("cannot start native compiler; install cc or set CC to a compiler executable")?;
    if !result.status.success() {
        bail!(
            "native compiler failed ({}):\n{}",
            result.status,
            String::from_utf8_lossy(&result.stderr)
        );
    }
    fs::rename(&executable, output)
        .with_context(|| format!("cannot publish {}", output.display()))?;
    Ok(())
}
