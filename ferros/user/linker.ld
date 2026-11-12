/* Static ELF64 user image. The kernel supplies stack/guard separately. */
OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(_user_start)
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
    stack PT_GNU_STACK FLAGS(6);
}
SECTIONS {
    . = 0x40000000;
    .text ALIGN(4096) : {
        KEEP(*(.text.entry))
        *(.text .text.*)
        . = ALIGN(4096);
    } :text
    .rodata ALIGN(4096) : {
        *(.rodata .rodata.*)
        . = ALIGN(4096);
    } :rodata
    .data ALIGN(4096) : { *(.data .data.*) } :data
    .bss ALIGN(4096) (NOLOAD) : {
        *(.bss .bss.*) *(COMMON)
        . = ALIGN(4096);
    } :data
    __user_image_end = .;
    /DISCARD/ : { *(.eh_frame .eh_frame_hdr) *(.comment) *(.note .note.*) }
}
ASSERT(_user_start == 0x40000000, "entry must begin at user base")
ASSERT(__user_image_end <= 0x400f0000, "image overlaps intentional gap probe")
