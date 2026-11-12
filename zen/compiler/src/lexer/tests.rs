#[cfg(test)]
mod tests {
    use crate::lexer::debug::debug_lex;
    use crate::lexer::{Base, FloatSuffix, IntSuffix, Lexer, TokenKind};

    fn lex(source: &str) -> Vec<TokenKind> {
        let mut lexer = Lexer::new(source, 0);
        let tokens = lexer.collect_all();
        tokens.into_iter().map(|t| t.kind).collect()
    }

    // Helper for pattern matching without moving
    fn assert_ident(kinds: &[TokenKind], idx: usize, expected: &str) {
        assert!(
            matches!(&kinds[idx], TokenKind::Ident(s) if s == expected),
            "Expected Ident({}) at index {}",
            expected,
            idx
        );
    }

    fn assert_string(kinds: &[TokenKind], idx: usize, expected: &str) {
        assert!(
            matches!(&kinds[idx], TokenKind::String(s) if s == expected),
            "Expected String({}) at index {}",
            expected,
            idx
        );
    }

    #[test]
    fn test_keywords() {
        let kinds = lex("fn let mut const if else while for return break continue struct impl mod use pub as type enum match loop unsafe extern sizeof alignof offsetof cast transmute");
        assert!(matches!(kinds[0], TokenKind::Fn));
        assert!(matches!(kinds[1], TokenKind::Let));
        assert!(matches!(kinds[2], TokenKind::Mut));
        assert!(matches!(kinds[3], TokenKind::Const));
        assert!(matches!(kinds[4], TokenKind::If));
        assert!(matches!(kinds[5], TokenKind::Else));
        assert!(matches!(kinds[6], TokenKind::While));
        assert!(matches!(kinds[7], TokenKind::For));
        assert!(matches!(kinds[8], TokenKind::Return));
        assert!(matches!(kinds[9], TokenKind::Break));
        assert!(matches!(kinds[10], TokenKind::Continue));
        assert!(matches!(kinds[11], TokenKind::Struct));
        assert!(matches!(kinds[12], TokenKind::Impl));
        assert!(matches!(kinds[13], TokenKind::Mod));
        assert!(matches!(kinds[14], TokenKind::Use));
        assert!(matches!(kinds[15], TokenKind::Pub));
        assert!(matches!(kinds[16], TokenKind::As));
        assert!(matches!(kinds[17], TokenKind::Type));
        assert!(matches!(kinds[18], TokenKind::Enum));
        assert!(matches!(kinds[19], TokenKind::Match));
        assert!(matches!(kinds[20], TokenKind::Loop));
        assert!(matches!(kinds[21], TokenKind::Unsafe));
        assert!(matches!(kinds[22], TokenKind::Extern));
        assert!(matches!(kinds[23], TokenKind::Sizeof));
        assert!(matches!(kinds[24], TokenKind::Alignof));
        assert!(matches!(kinds[25], TokenKind::Offsetof));
        assert!(matches!(kinds[26], TokenKind::Cast));
        assert!(matches!(kinds[27], TokenKind::Transmute));
    }

    #[test]
    fn test_primitive_types() {
        let kinds =
            lex("void bool char i8 i16 i32 i64 i128 isize u8 u16 u32 u64 u128 usize f32 f64 never");
        assert!(matches!(kinds[0], TokenKind::Void));
        assert!(matches!(kinds[1], TokenKind::Bool_));
        assert!(matches!(kinds[2], TokenKind::Char_));
        assert!(matches!(kinds[3], TokenKind::I8));
        assert!(matches!(kinds[4], TokenKind::I16));
        assert!(matches!(kinds[5], TokenKind::I32));
        assert!(matches!(kinds[6], TokenKind::I64));
        assert!(matches!(kinds[7], TokenKind::I128));
        assert!(matches!(kinds[8], TokenKind::Isize));
        assert!(matches!(kinds[9], TokenKind::U8));
        assert!(matches!(kinds[10], TokenKind::U16));
        assert!(matches!(kinds[11], TokenKind::U32));
        assert!(matches!(kinds[12], TokenKind::U64));
        assert!(matches!(kinds[13], TokenKind::U128));
        assert!(matches!(kinds[14], TokenKind::Usize));
        assert!(matches!(kinds[15], TokenKind::F32));
        assert!(matches!(kinds[16], TokenKind::F64));
        assert!(matches!(kinds[17], TokenKind::Never));
    }

    #[test]
    fn test_identifiers() {
        let kinds = lex("foo bar _ baz123");
        assert_ident(&kinds, 0, "foo");
        assert_ident(&kinds, 1, "bar");
        assert_ident(&kinds, 2, "_");
        assert_ident(&kinds, 3, "baz123");
    }

    #[test]
    fn test_integer_literals() {
        let kinds = lex("42 0xFF 0b1010 0o77 123_i32 456u64");
        // decimal
        assert!(matches!(
            kinds[0],
            TokenKind::Integer {
                value: 42,
                base: Base::Decimal,
                suffix: None
            }
        ));
        // hex
        assert!(matches!(
            kinds[1],
            TokenKind::Integer {
                value: 255,
                base: Base::Hex,
                suffix: None
            }
        ));
        // binary
        assert!(matches!(
            kinds[2],
            TokenKind::Integer {
                value: 10,
                base: Base::Binary,
                suffix: None
            }
        ));
        // octal
        assert!(matches!(
            kinds[3],
            TokenKind::Integer {
                value: 63,
                base: Base::Octal,
                suffix: None
            }
        ));
        // with suffix
        assert!(matches!(
            kinds[4],
            TokenKind::Integer {
                value: 123,
                base: Base::Decimal,
                suffix: Some(IntSuffix::I32)
            }
        ));
        assert!(matches!(
            kinds[5],
            TokenKind::Integer {
                value: 456,
                base: Base::Decimal,
                suffix: Some(IntSuffix::U64)
            }
        ));
    }

    #[test]
    fn test_float_literals() {
        let kinds = lex("3.14 1.5e10 2.0_f32 3.0f64");
        assert!(
            matches!(kinds[0], TokenKind::Float { value: v, suffix: None } if (v - 3.14).abs() < f64::EPSILON)
        );
        assert!(
            matches!(kinds[1], TokenKind::Float { value: v, suffix: None } if (v - 1.5e10).abs() < f64::EPSILON)
        );
        assert!(
            matches!(kinds[2], TokenKind::Float { value: v, suffix: Some(FloatSuffix::F32) } if (v - 2.0).abs() < f64::EPSILON)
        );
        assert!(
            matches!(kinds[3], TokenKind::Float { value: v, suffix: Some(FloatSuffix::F64) } if (v - 3.0).abs() < f64::EPSILON)
        );
    }

    #[test]
    fn test_bool_literals() {
        debug_lex("true false");
        let kinds = lex("true false");
        assert!(matches!(kinds[0], TokenKind::True));
        assert!(matches!(kinds[1], TokenKind::False));
    }

    #[test]
    fn test_char_literals() {
        debug_lex("'a' '\\n' '\\t' '\\\\' \"hello\"");
        let kinds = lex("'a' '\\n' '\\t' '\\\\' \"hello\"");
        assert!(matches!(kinds[0], TokenKind::Char('a')));
        assert!(matches!(kinds[1], TokenKind::Char('\n')));
        assert!(matches!(kinds[2], TokenKind::Char('\t')));
        assert!(matches!(kinds[3], TokenKind::Char('\\')));
        assert_string(&kinds, 4, "hello");
    }

    #[test]
    fn test_operators() {
        debug_lex("+ - * / % ** == != < > <= >= && || ! & | ^ ~ << >> = += -= *= /= %= &= |= ^= <<= >>= . .. ... -> => :: : ; , ( ) [ ] { } | | ? @");
        let kinds = lex("+ - * / % ** == != < > <= >= && || ! & | ^ ~ << >> = += -= *= /= %= &= |= ^= <<= >>= . .. ... -> => :: : ; , ( ) [ ] { } | | ? @");
        // Check key operators
        assert!(matches!(kinds[0], TokenKind::Plus));
        assert!(matches!(kinds[1], TokenKind::Minus));
        assert!(matches!(kinds[2], TokenKind::Star));
        assert!(matches!(kinds[3], TokenKind::Slash));
        assert!(matches!(kinds[4], TokenKind::Percent));
        assert!(matches!(kinds[5], TokenKind::StarStar));
        assert!(matches!(kinds[6], TokenKind::EqEq));
        assert!(matches!(kinds[7], TokenKind::NotEq));
        assert!(matches!(kinds[8], TokenKind::Lt));
        assert!(matches!(kinds[9], TokenKind::Gt));
        assert!(matches!(kinds[10], TokenKind::LtEq));
        assert!(matches!(kinds[11], TokenKind::GtEq));
        assert!(matches!(kinds[12], TokenKind::AndAnd));
        assert!(matches!(kinds[13], TokenKind::OrOr));
        assert!(matches!(kinds[14], TokenKind::Not));
        assert!(matches!(kinds[15], TokenKind::Amp));
        assert!(matches!(kinds[16], TokenKind::Pipe));
        assert!(matches!(kinds[17], TokenKind::Caret));
        assert!(matches!(kinds[18], TokenKind::Tilde));
        assert!(matches!(kinds[19], TokenKind::Shl));
        assert!(matches!(kinds[20], TokenKind::Shr));
        assert!(matches!(kinds[21], TokenKind::Assign));
        assert!(matches!(kinds[22], TokenKind::PlusEq));
        assert!(matches!(kinds[23], TokenKind::MinusEq));
        assert!(matches!(kinds[24], TokenKind::StarEq));
        assert!(matches!(kinds[25], TokenKind::SlashEq));
        assert!(matches!(kinds[26], TokenKind::PercentEq));
        assert!(matches!(kinds[27], TokenKind::AmpEq));
        assert!(matches!(kinds[28], TokenKind::PipeEq));
        assert!(matches!(kinds[29], TokenKind::CaretEq));
        assert!(matches!(kinds[30], TokenKind::ShlEq));
        assert!(matches!(kinds[31], TokenKind::ShrEq));
        assert!(matches!(kinds[32], TokenKind::Dot));
        assert!(matches!(kinds[33], TokenKind::DotDot));
        assert!(matches!(kinds[34], TokenKind::DotDotDot));
        assert!(matches!(kinds[35], TokenKind::Arrow));
        assert!(matches!(kinds[36], TokenKind::FatArrow));
        assert!(matches!(kinds[37], TokenKind::DoubleColon));
        assert!(matches!(kinds[38], TokenKind::Colon));
        assert!(matches!(kinds[39], TokenKind::Semi));
        assert!(matches!(kinds[40], TokenKind::Comma));
        assert!(matches!(kinds[41], TokenKind::LParen));
        assert!(matches!(kinds[42], TokenKind::RParen));
        assert!(matches!(kinds[43], TokenKind::LBracket));
        assert!(matches!(kinds[44], TokenKind::RBracket));
        assert!(matches!(kinds[45], TokenKind::LBrace));
        assert!(matches!(kinds[46], TokenKind::RBrace));
        assert!(matches!(kinds[47], TokenKind::Pipe));
        assert!(matches!(kinds[48], TokenKind::Pipe));
        assert!(matches!(kinds[49], TokenKind::Question));
        assert!(matches!(kinds[50], TokenKind::At));
        assert!(!kinds.iter().any(|kind| matches!(kind, TokenKind::Error(_))));
    }

    #[test]
    fn test_comments() {
        let kinds = lex("fn main() { // line comment\n  let x = 1; /* block comment */ }");
        // Should not contain comment tokens
        let non_eof: Vec<_> = kinds
            .into_iter()
            .filter(|k| !matches!(k, TokenKind::Eof))
            .collect();
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::Fn)));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::Ident(s) if s == "main")));
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::Let)));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::Integer { value: 1, .. })));
    }

    #[test]
    fn test_nested_block_comments() {
        let kinds = lex("/* outer /* inner */ outer */");
        let non_eof: Vec<_> = kinds
            .into_iter()
            .filter(|k| !matches!(k, TokenKind::Eof))
            .collect();
        assert_eq!(non_eof.len(), 0); // Only EOF
    }

    #[test]
    fn test_hello_world() {
        let source = r#"fn main() -> i32 {
    print("Hello, Zen!\n");
    return 0;
}"#;
        let kinds = lex(source);
        let non_eof: Vec<_> = kinds
            .into_iter()
            .filter(|k| !matches!(k, TokenKind::Eof))
            .collect();

        // Check key tokens present
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::Fn)));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::Ident(ref s) if s == "main")));
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::Arrow)));
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::I32)));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::Ident(ref s) if s == "print")));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::String(ref s) if s == "Hello, Zen!\n")));
        assert!(non_eof.iter().any(|k| matches!(k, TokenKind::Return)));
        assert!(non_eof
            .iter()
            .any(|k| matches!(k, TokenKind::Integer { value: 0, .. })));
    }

    #[test]
    fn malformed_literals_are_errors() {
        for source in [
            "0x",
            "0x_1",
            "0b102",
            "0o8",
            "0xffg",
            "123abc",
            "123u65",
            "340282366920938463463374607431768211456",
            "1.2f65",
            "1.2e",
            "1.2e+",
            "1.2e99999",
            "1e_3",
            "1.2e+_1",
            "1e99999",
            "\"unfinished",
            "\"unfinished\\",
            "\"bad\\q\"",
            "\"bad\\x1\"",
            "\"bad\\xgg\"",
            "''",
            "'ab'",
            "'\\q'",
            "'\\x1'",
            "/* unfinished",
        ] {
            assert!(
                lex(source).iter().any(|k| matches!(k, TokenKind::Error(_))),
                "Expected lexical error for {source:?}"
            );
        }
    }

    #[test]
    fn range_operators_do_not_consume_following_tokens() {
        assert_eq!(
            lex("..x ...y 1..2"),
            vec![
                TokenKind::DotDot,
                TokenKind::Ident("x".into()),
                TokenKind::DotDotDot,
                TokenKind::Ident("y".into()),
                TokenKind::Integer {
                    value: 1,
                    base: Base::Decimal,
                    suffix: None
                },
                TokenKind::DotDot,
                TokenKind::Integer {
                    value: 2,
                    base: Base::Decimal,
                    suffix: None
                },
                TokenKind::Eof,
            ]
        );
    }

    #[test]
    fn utf8_spans_cover_bytes_and_lexing_continues() {
        let tokens = Lexer::new("\"á🦀\" + é 7", 17).collect_all();
        assert_eq!(tokens[0].span, crate::lexer::Span::new(17, 0, 8));
        assert_eq!(tokens[0].kind, TokenKind::String("á🦀".into()));
        assert_eq!(tokens[1].span, crate::lexer::Span::new(17, 9, 10));
        assert_eq!(tokens[2].span, crate::lexer::Span::new(17, 11, 13));
        assert!(matches!(tokens[2].kind, TokenKind::Error(_)));
        assert!(matches!(
            tokens[3].kind,
            TokenKind::Integer { value: 7, .. }
        ));
    }

    #[test]
    fn many_consecutive_comments_use_constant_stack() {
        let source = "/* comment */ // comment\n".repeat(100_000) + "42";
        let tokens = lex(&source);
        assert_eq!(tokens.len(), 2);
        assert!(matches!(tokens[0], TokenKind::Integer { value: 42, .. }));
    }

    #[test]
    fn valid_strings_keep_nul_utf8_and_hex() {
        assert_eq!(
            lex(r#""a\0é\x41" '🦀'"#),
            vec![
                TokenKind::String("a\0éA".into()),
                TokenKind::Char('🦀'),
                TokenKind::Eof,
            ]
        );
    }

    #[test]
    fn numeric_extremes_and_exponent_literals() {
        assert!(matches!(
            lex("340282366920938463463374607431768211455")[0],
            TokenKind::Integer {
                value: u128::MAX,
                ..
            }
        ));
        assert!(matches!(
            lex("0xffffffffffffffffffffffffffffffff")[0],
            TokenKind::Integer {
                value: u128::MAX,
                ..
            }
        ));
        assert!(matches!(lex("1e3")[0], TokenKind::Float { value, .. } if value == 1000.0));
    }

    #[test]
    fn peek_and_eof_are_stable() {
        let mut lexer = Lexer::new("42", 0);
        let first = lexer.peek_token().kind.clone();
        assert_eq!(first, lexer.peek_token().kind);
        assert!(matches!(
            lexer.next_token().kind,
            TokenKind::Integer { value: 42, .. }
        ));
        assert!(matches!(lexer.next_token().kind, TokenKind::Eof));
        assert!(matches!(lexer.peek_token().kind, TokenKind::Eof));
        assert!(matches!(lexer.next_token().kind, TokenKind::Eof));
        assert!(matches!(lexer.next_token().kind, TokenKind::Eof));
    }
}
