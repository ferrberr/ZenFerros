// Benchmark: Rust Collatz step count over 1..=500k.
fn steps(n: u64) -> u64 {
    let mut value = n;
    let mut count = 0u64;
    while value != 1 {
        if value % 2 == 0 {
            value /= 2;
        } else {
            value = value * 3 + 1;
        }
        count += 1;
    }
    count
}

fn main() {
    let mut total: u64 = 0;
    for n in 1..=500_000u64 {
        total += steps(n);
    }
    println!("{}", total);
}
