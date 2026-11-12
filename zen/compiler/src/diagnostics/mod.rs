//! Diagnostics module for Zen compiler

use codespan_reporting::diagnostic::{Diagnostic, Label, LabelStyle, Severity};
use codespan_reporting::files::SimpleFiles;
use codespan_reporting::term::termcolor::{ColorChoice, StandardStream, WriteColor};
use codespan_reporting::term::{self, Config};

pub type FileMap = SimpleFiles<String, String>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct FileId(pub usize);

#[derive(Debug, Clone)]
pub struct DiagnosticError {
    pub severity: Severity,
    pub message: String,
    pub labels: Vec<Label<usize>>,
    pub notes: Vec<String>,
}

impl DiagnosticError {
    pub fn error(message: impl Into<String>) -> Self {
        Self {
            severity: Severity::Error,
            message: message.into(),
            labels: Vec::new(),
            notes: Vec::new(),
        }
    }

    pub fn warning(message: impl Into<String>) -> Self {
        Self {
            severity: Severity::Warning,
            message: message.into(),
            labels: Vec::new(),
            notes: Vec::new(),
        }
    }

    pub fn note(message: impl Into<String>) -> Self {
        Self {
            severity: Severity::Note,
            message: message.into(),
            labels: Vec::new(),
            notes: Vec::new(),
        }
    }

    pub fn with_label(
        mut self,
        file_id: usize,
        start: usize,
        end: usize,
        message: impl Into<String>,
    ) -> Self {
        self.labels
            .push(Label::new(LabelStyle::Primary, file_id, start..end).with_message(message));
        self
    }

    pub fn with_note(mut self, note: impl Into<String>) -> Self {
        self.notes.push(note.into());
        self
    }

    pub fn emit(&self, files: &FileMap, writer: &mut dyn WriteColor) {
        let diagnostic = Diagnostic::new(self.severity)
            .with_message(&self.message)
            .with_labels(self.labels.clone())
            .with_notes(self.notes.clone());
        let config = Config::default();
        term::emit(writer, &config, files, &diagnostic).unwrap();
    }
}

pub fn emit_diagnostics(files: &FileMap, diagnostics: &[DiagnosticError]) {
    let mut writer = StandardStream::stderr(ColorChoice::Auto);
    for diag in diagnostics {
        diag.emit(files, &mut writer);
    }
}
