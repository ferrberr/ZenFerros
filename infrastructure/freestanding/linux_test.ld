/* Linux process test layout; this is not the Ferros kernel linker script. */
ENTRY(_start)
PHDRS {
    code PT_LOAD FLAGS(5);
    data PT_LOAD FLAGS(6);
    stack PT_GNU_STACK FLAGS(6);
}
SECTIONS {
    . = 0x400000;
    .text : { *(.text .text.*) } :code
    .rodata : { *(.rodata .rodata.*) } :code
    . = ALIGN(0x1000);
    .data : { *(.data .data.*) } :data
    .bss : { *(.bss .bss.*) *(COMMON) } :data
    /DISCARD/ : { *(.comment) *(.eh_frame .eh_frame_hdr) *(.note .note.*) }
}
