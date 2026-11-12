// Benchmark: Rust reference for volatile in-place heapsort over 500k u32.
use std::alloc::{alloc, dealloc, Layout};
use std::ptr::{read_volatile, write_volatile};

unsafe fn load(array: *const u32, index: u64) -> u32 {
    read_volatile(array.add(index as usize))
}
unsafe fn store(array: *mut u32, index: u64, value: u32) {
    write_volatile(array.add(index as usize), value)
}
unsafe fn sift(array: *mut u32, start: u64, end: u64) {
    let mut root = start;
    while root * 2 + 1 <= end {
        let mut child = root * 2 + 1;
        if child + 1 <= end && load(array, child) < load(array, child + 1) {
            child += 1;
        }
        if load(array, root) < load(array, child) {
            let left = load(array, root);
            let right = load(array, child);
            store(array, root, right);
            store(array, child, left);
            root = child;
        } else {
            return;
        }
    }
}

fn main() {
    let count: u64 = 500_000;
    let layout = Layout::from_size_align((count as usize) * 4, 4).unwrap();
    unsafe {
        let array = alloc(layout) as *mut u32;
        if array.is_null() {
            std::process::exit(2);
        }
        let mut state: u64 = 987654321;
        for i in 0..count {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            store(array, i, (state >> 33) as u32);
        }
        if count > 1 {
            let mut start = count / 2;
            while start > 0 {
                start -= 1;
                sift(array, start, count - 1);
            }
            let mut end = count - 1;
            while end > 0 {
                let first = load(array, 0);
                let last = load(array, end);
                store(array, 0, last);
                store(array, end, first);
                end -= 1;
                sift(array, 0, end);
            }
        }
        let mut checksum: u64 = 0;
        for i in 0..count {
            checksum = checksum * 31 + load(array, i) as u64;
        }
        dealloc(array as *mut u8, layout);
        println!("{}", checksum);
    }
}
