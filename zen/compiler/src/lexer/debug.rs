//! Debug helper for lexer

pub fn debug_lex(source: &str) {
    use crate::lexer::Lexer;
    let mut lexer = Lexer::new(source, 0);
    let tokens = lexer.collect_all();
    for (i, token) in tokens.iter().enumerate() {
        println!("{:3}: {:?} @ {:?}", i, token.kind, token.span);
    }
}
