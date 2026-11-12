/* ELF64 payload + ELF32 Multiboot loader container, as in TASK-410.
 * REQUIRED ld flag: -z max-page-size=0x1000.
 * Text/rodata boundaries are whole pages for the Zen 4 KiB page-table policy.
 */
OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(multiboot_entry)
PHDRS {
    code PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
    stack PT_GNU_STACK FLAGS(6);
}
SECTIONS {
    . = 0x100000;
    __image_start = .;
    .multiboot ALIGN(4) : { KEEP(*(.multiboot)) } :code
    .text ALIGN(4096) : {
        __text_start = .;
        *(.text.boot) *(.text .text.*)
        . = ALIGN(4096);
        __text_end = .;
    } :code
    .rodata ALIGN(4096) : {
        __rodata_start = .;
        *(.rodata.boot) *(.rodata .rodata.*)
        . = ALIGN(4096);
        __rodata_end = .;
    } :rodata
    .data ALIGN(4096) : { *(.data .data.*) } :data
    .bss ALIGN(4096) (NOLOAD) : {
        __bss_start = .;
        *(.bss.boot) *(.bss .bss.*) *(COMMON)
        . = ALIGN(4096);
        __bss_end = .;
    } :data
    __image_end = .;
    /DISCARD/ : { *(.eh_frame .eh_frame_hdr) *(.comment) *(.note .note.*) }
}
ASSERT(SIZEOF(.multiboot) == 12, "expected one 12-byte Multiboot header")
ASSERT(ADDR(.multiboot) == __image_start, "Multiboot header must lead image")
ASSERT((__text_start & 4095) == 0 && (__text_end & 4095) == 0, "text page alignment required")
ASSERT((__rodata_start & 4095) == 0 && (__rodata_end & 4095) == 0, "rodata page alignment required")
ASSERT(__text_end <= __rodata_start, "text and rodata page ranges overlap")
ASSERT((__bss_start & 4095) == 0 && (__bss_end & 4095) == 0, "BSS page alignment required")
ASSERT((boot_stack_top & 15) == 0, "SysV kernel stack must be 16-byte aligned")
ASSERT(__image_end < 0x4000000, "kernel must fit Zen's initial 64 MiB mapping")
