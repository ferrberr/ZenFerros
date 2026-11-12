//! Simple driver to test lexer on files

use crate::lexer::{Lexer, TokenKind};

pub fn lex_file(source: &str) {
    let mut lexer = Lexer::new(source, 0);
    let tokens = lexer.collect_all();

    println!("Tokens for source:");
    println!("{}", source);
    println!("\n--- Token Stream ---");
    for (i, token) in tokens.iter().enumerate() {
        match &token.kind {
            TokenKind::Ident(s) => {
                println!("{:3}: {:?}(\"{}\") @ {:?}", i, token.kind, s, token.span)
            }
            TokenKind::String(s) => {
                println!("{:3}: {:?}(\"{}\") @ {:?}", i, token.kind, s, token.span)
            }
            TokenKind::Integer {
                value,
                base,
                suffix,
            } => println!(
                "{:3}: {:?}(value={}, base={:?}, suffix={:?}) @ {:?}",
                i, token.kind, value, base, suffix, token.span
            ),
            TokenKind::Float { value, suffix } => println!(
                "{:3}: {:?}(value={}, suffix={:?}) @ {:?}",
                i, token.kind, value, suffix, token.span
            ),
            TokenKind::Char(c) => println!("{:3}: {:?}('{}') @ {:?}", i, token.kind, c, token.span),
            TokenKind::Error(msg) => {
                println!("{:3}: {:?}({}) @ {:?}", i, token.kind, msg, token.span)
            }
            _ => println!("{:3}: {:?} @ {:?}", i, token.kind, token.span),
        }
    }
}
