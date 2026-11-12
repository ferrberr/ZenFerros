use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand, ValueEnum};
use codespan_reporting::{
    diagnostic::{Diagnostic, Label},
    files::SimpleFiles,
    term::{
        self,
        termcolor::{ColorChoice, StandardStream},
    },
};
use std::{
    fs,
    io::Write,
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
    process::{Command, ExitCode},
};
use zen_compiler::{
    fmt as formatter,
    lexer::{Lexer, TokenKind},
    lint as linter, lsp, module, mvp, native,
};

#[derive(Clone, Copy, ValueEnum)]
enum Target {
    Host,
    #[value(name = "x86_64-unknown-none")]
    X86_64UnknownNone,
}
impl Target {
    fn mode(self) -> mvp::Mode {
        match self {
            Self::Host => mvp::Mode::Hosted,
            Self::X86_64UnknownNone => mvp::Mode::Freestanding,
        }
    }
}
#[derive(Clone, Copy, ValueEnum)]
enum Emit {
    Exe,
    Obj,
    C,
}
impl Emit {
    fn artifact(self) -> native::Artifact {
        match self {
            Self::Exe => native::Artifact::Executable,
            Self::Obj => native::Artifact::Object,
            Self::C => native::Artifact::CSource,
        }
    }
}

#[derive(Parser)]
#[command(name = "zen", version, about = "Zen native bootstrap compiler")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}
#[derive(Subcommand)]
enum Commands {
    /// Compile a .zen file to a native executable, object or C source
    Build {
        path: PathBuf,
        /// Optimize the native executable
        #[arg(short, long)]
        release: bool,
        /// Output executable path (defaults to source without .zen)
        #[arg(short, long)]
        output: Option<PathBuf>,
        /// Compilation environment (freestanding requires --emit obj or c)
        #[arg(long, value_enum, default_value = "host")]
        target: Target,
        #[arg(long, value_enum, default_value = "exe")]
        emit: Emit,
    },
    /// Compile and run a .zen file; propagate its exit status
    Run {
        path: PathBuf,
        #[arg(short, long)]
        release: bool,
        #[arg(last = true)]
        args: Vec<String>,
    },
    /// Check syntax, names and types without generating a binary
    Check {
        path: PathBuf,
        #[arg(long, value_enum, default_value = "host")]
        target: Target,
    },
    /// Show compiler version and backend
    Version,
    /// Print tokens for a .zen file
    Lex { path: PathBuf },
    /// Report unused variables/parameters/functions and unreachable code
    Lint {
        path: PathBuf,
        /// Emit a JSON array with one object per diagnostic on stdout
        #[arg(long)]
        json: bool,
        /// Exit with status 2 when warnings are reported
        #[arg(long)]
        deny_warnings: bool,
        #[arg(long, value_enum, default_value = "host")]
        target: Target,
    },
    /// Run the Language Server Protocol server over stdin/stdout
    Lsp,
    /// Format a .zen file with the canonical style
    Fmt {
        path: PathBuf,
        /// Exit with status 1 when the file is not already formatted (never writes)
        #[arg(long, conflicts_with = "write")]
        check: bool,
        /// Rewrite the file atomically, only when formatting changes it
        #[arg(long, conflicts_with = "check")]
        write: bool,
    },
}
fn read_source(path: &Path) -> Result<String> {
    if path.extension().and_then(|s| s.to_str()) != Some("zen") {
        bail!("expected a .zen source file: {}", path.display());
    }
    fs::read_to_string(path).with_context(|| format!("cannot read {}", path.display()))
}
/// Replace `path` with `contents` using a sibling temporary file and `rename`,
/// so readers never observe a partially written source file. Permissions are
/// copied from the original file.
fn write_atomic(path: &Path, contents: &str) -> Result<()> {
    let metadata = fs::metadata(path).with_context(|| format!("cannot stat {}", path.display()))?;
    let directory = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let name = path
        .file_name()
        .with_context(|| format!("invalid file name: {}", path.display()))?
        .to_string_lossy()
        .into_owned();
    for attempt in 0..100u32 {
        let temporary = directory.join(format!(
            ".{name}.zen-fmt.{}.{attempt}.tmp",
            std::process::id()
        ));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)
        {
            Ok(mut file) => {
                let written = file
                    .write_all(contents.as_bytes())
                    .and_then(|()| file.sync_all())
                    .with_context(|| format!("cannot write {}", temporary.display()));
                drop(file);
                if let Err(error) = written {
                    let _ = fs::remove_file(&temporary);
                    return Err(error);
                }
                if let Err(error) = fs::set_permissions(&temporary, metadata.permissions()) {
                    let _ = fs::remove_file(&temporary);
                    return Err(error).with_context(|| {
                        format!("cannot preserve permissions on {}", path.display())
                    });
                }
                return match fs::rename(&temporary, path) {
                    Ok(()) => Ok(()),
                    Err(error) => {
                        let _ = fs::remove_file(&temporary);
                        Err(error).with_context(|| format!("cannot replace {}", path.display()))
                    }
                };
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(error).with_context(|| {
                    format!("cannot create a temporary file for {}", path.display())
                })
            }
        }
    }
    bail!(
        "cannot create a unique temporary file next to {}",
        path.display()
    )
}
fn diagnose<T>(result: Result<T, mvp::CompileError>, path: &Path, source: &str) -> Result<T> {
    result.map_err(|error| {
        let mut files = SimpleFiles::new();
        let id = files.add(path.display().to_string(), source);
        let diagnostic = Diagnostic::error()
            .with_message(error.message.clone())
            .with_labels(vec![Label::primary(
                id,
                error.span.start as usize..error.span.end as usize,
            )]);
        let writer = StandardStream::stderr(ColorChoice::Auto);
        let _ = term::emit(
            &mut writer.lock(),
            &term::Config::default(),
            &files,
            &diagnostic,
        );
        anyhow::anyhow!("compilation failed")
    })
}
fn diagnose_resolved<T>(
    result: Result<T, mvp::CompileError>,
    resolved: &module::Resolved,
) -> Result<T> {
    result.map_err(|error| {
        let mut files = SimpleFiles::new();
        let ids: Vec<_> = resolved
            .files
            .iter()
            .map(|file| files.add(file.path.display().to_string(), &file.text))
            .collect();
        let (file, start, end) = resolved.locate_span(error.span);
        let id = ids.get(file).copied().unwrap_or(0);
        let diagnostic = Diagnostic::error()
            .with_message(error.message.clone())
            .with_labels(vec![Label::primary(id, start..end)]);
        let writer = StandardStream::stderr(ColorChoice::Auto);
        let _ = term::emit(
            &mut writer.lock(),
            &term::Config::default(),
            &files,
            &diagnostic,
        );
        anyhow::anyhow!("compilation failed")
    })
}
fn execute(cli: Cli) -> Result<u8> {
    match cli.command {
        Commands::Build {
            path,
            release,
            output,
            target,
            emit,
        } => {
            let source = module::resolve(&path)?;
            if matches!(target, Target::X86_64UnknownNone) && matches!(emit, Emit::Exe) {
                bail!("freestanding builds require --emit obj or --emit c");
            }
            let c_source =
                diagnose_resolved(mvp::emit_c_with_mode(&source.text, target.mode()), &source)?;
            let output = output.unwrap_or_else(|| {
                path.with_extension(match emit {
                    Emit::Exe => "",
                    Emit::Obj => "o",
                    Emit::C => "c",
                })
            });
            if output.exists() && fs::canonicalize(&path)? == fs::canonicalize(&output)? {
                bail!("output would overwrite the Zen source file");
            }
            native::build_artifact(&c_source, &output, release, emit.artifact(), target.mode())?;
            println!("Built {}", output.display());
        }
        Commands::Run {
            path,
            release,
            args,
        } => {
            let source = module::resolve(&path)?;
            let c_source = diagnose_resolved(mvp::emit_c(&source.text), &source)?;
            let scratch = native::ScratchDir::new(&std::env::temp_dir())?;
            let output = scratch.0.join("program");
            native::build(&c_source, &output, release)?;
            let status = Command::new(&output)
                .args(args)
                .status()
                .context("cannot execute native program")?;
            return Ok(status.code().map(|c| c as u8).unwrap_or(1));
        }
        Commands::Check { path, target } => {
            let source = module::resolve(&path)?;
            diagnose_resolved(mvp::check_with_mode(&source.text, target.mode()), &source)?;
            println!("Checked {}", path.display());
        }
        Commands::Version => {
            println!("zen {} (bootstrap)", env!("CARGO_PKG_VERSION"));
            println!("Host: {}-{}", std::env::consts::ARCH, std::env::consts::OS);
            println!("Backend: C11 via host cc (override with CC)");
            println!("Targets: host, x86_64-unknown-none (ELF object; GCC-compatible x86_64 CC)");
            println!(
                "Compiler build: {}",
                if cfg!(debug_assertions) {
                    "debug"
                } else {
                    "release"
                }
            );
        }
        Commands::Lex { path } => {
            let source = read_source(&path)?;
            for token in Lexer::new(&source, 0).collect_all() {
                if let TokenKind::Error(message) = &token.kind {
                    return diagnose(
                        Err(mvp::CompileError {
                            message: message.clone(),
                            span: token.span,
                        }),
                        &path,
                        &source,
                    );
                }
                println!("{:?} {}..{}", token.kind, token.span.start, token.span.end);
            }
        }
        Commands::Lint {
            path,
            json,
            deny_warnings,
            target,
        } => {
            let source = read_source(&path)?;
            let diagnostics = match mvp::lint_with_mode(&source, target.mode()) {
                Ok(diagnostics) => diagnostics,
                Err(mvp::CompileError { message, span }) => vec![linter::LintDiagnostic::error(
                    linter::COMPILE_ERROR,
                    message,
                    span,
                    &source,
                )],
            };
            let file = path.display().to_string();
            if json {
                print!("{}", linter::render_json(&file, &diagnostics));
            } else {
                print!("{}", linter::render_text(&file, &diagnostics));
            }
            return Ok(linter::exit_code(&diagnostics, deny_warnings));
        }
        Commands::Lsp => {
            // The protocol loop owns stdin/stdout; stdout must stay free of
            // human-readable output so clients only see framed JSON-RPC.
            return lsp::run().context("LSP server failed");
        }
        Commands::Fmt { path, check, write } => {
            let source = read_source(&path)?;
            let formatted = formatter::format(&source)
                .with_context(|| format!("cannot format {}", path.display()))?;
            if check {
                if formatted == source {
                    return Ok(0);
                }
                eprintln!(
                    "zen fmt: {} is not formatted; run `zen fmt --write {}`",
                    path.display(),
                    path.display()
                );
                return Ok(1);
            }
            if write {
                // Belt and braces: never replace a user file with output that
                // the formatter cannot reproduce on a second pass.
                let again = formatter::format(&formatted)
                    .with_context(|| format!("cannot verify formatting of {}", path.display()))?;
                if again != formatted {
                    bail!(
                        "refusing to write {}: formatter output is not idempotent",
                        path.display()
                    );
                }
                if formatted != source {
                    write_atomic(&path, &formatted)?;
                }
                return Ok(0);
            }
            print!("{formatted}");
        }
    }
    Ok(0)
}
fn main() -> ExitCode {
    match execute(Cli::parse()) {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            eprintln!("zen: {error:#}");
            ExitCode::FAILURE
        }
    }
}
