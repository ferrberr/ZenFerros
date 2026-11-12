// Benchmark: Rust reference for volatile sequential byte write+read over 16 MiB.
use std::alloc::{alloc, dealloc, Layout};
use std::ptr::{read_volatile, write_volatile};

fn main() {
    let size: usize = 16_777_216;
    let layout = Layout::from_size_align(size, 1).unwrap();
    let buffer = unsafe { alloc(layout) };
    if buffer.is_null() {
        std::process::exit(2);
    }
    let mut state: u64 = 12345;
    for i in 0..size {
        state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        unsafe { write_volatile(buffer.add(i), (state >> 33) as u8) };
    }
    let mut sum: u64 = 0;
    for i in 0..size {
        sum += unsafe { read_volatile(buffer.add(i)) } as u64;
    }
    unsafe { dealloc(buffer, layout) };
    println!("{}", sum);
}
