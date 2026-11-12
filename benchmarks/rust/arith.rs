// Benchmark: Rust reference for 64-bit wrapping LCG arithmetic.
fn main() {
    let mut state: u64 = 0x2545F4914F6CDD1D;
    let mut sum: u64 = 0;
    for _ in 0..50_000_000u64 {
        state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        sum ^= state >> 32;
    }
    println!("{}", sum);
}
