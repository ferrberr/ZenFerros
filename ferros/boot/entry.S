/* Ferros bootstrap, authored for TASK-410 (no copied bootloader code).
 * Multiboot v1 supplies a flat 32-bit protected-mode environment.
 * Enter long mode with an identity mapping of [0, 1 GiB), interrupts disabled,
 * then call the Zen kernel through the System V AMD64 ABI.
 * This temporary mapping includes page zero and is RWX: it is bootstrap setup,
 * not a protected virtual-memory manager.
 */
.set MULTIBOOT_MAGIC, 0x1badb002
.set MULTIBOOT_FLAGS, 0x00000003

.section .multiboot,"a",@progbits
.balign 4
.long MULTIBOOT_MAGIC
.long MULTIBOOT_FLAGS
.long -(MULTIBOOT_MAGIC + MULTIBOOT_FLAGS)

.section .text.boot,"ax",@progbits
.code32
.global multiboot_entry
.type multiboot_entry, @function
multiboot_entry:
    cli
    cld
    /* Preserve both loader arguments in registers untouched by initialization. */
    movl %eax, %esi
    movl %ebx, %ebp

    /* Replace the loader GDT before loading any segment selectors. */
    lgdt boot_gdt_descriptor
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    movl $boot_stack_top, %esp

    /* Clear all BSS explicitly, including the page tables and bootstrap stack.
     * No push/call occurs until this completes; clearing the active stack is safe.
     */
    xorl %eax, %eax
    movl $__bss_start, %edi
    movl $__bss_end, %ecx
    subl %edi, %ecx
    shrl $2, %ecx
    rep stosl

    movl $boot_pdpt, %eax
    orl $0x03, %eax
    movl %eax, boot_pml4
    movl $boot_page_directory, %eax
    orl $0x03, %eax
    movl %eax, boot_pdpt

    /* 512 present/writable 2 MiB leaves cover exactly the first GiB.
     * High halves remain zero from BSS initialization.
     */
    xorl %ecx, %ecx
.Lmap_pages:
    movl %ecx, %eax
    shll $21, %eax
    orl $0x83, %eax
    movl %eax, boot_page_directory(,%ecx,8)
    incl %ecx
    cmpl $512, %ecx
    jne .Lmap_pages

    /* PAE -> CR3 -> EFER.LME -> CR0.PG/PE/WP -> far jump to a 64-bit CS. */
    /* Establish four-level PAE paging explicitly; do not inherit LA57/PCIDE. */
    movl $0x20, %eax
    movl %eax, %cr4
    movl $boot_pml4, %eax
    movl %eax, %cr3
    movl $0xc0000080, %ecx
    rdmsr
    orl $0x100, %eax
    wrmsr
    movl %cr0, %eax
    orl $0x80010001, %eax
    movl %eax, %cr0
    ljmp $0x08, $long_mode_entry

.code64
long_mode_entry:
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    xorw %ax, %ax
    movw %ax, %fs
    movw %ax, %gs
    leaq boot_stack_top(%rip), %rsp
    /* RSP is 16-byte aligned before call, 8 mod 16 on kernel entry. */
    movl %esi, %edi
    movl %ebp, %esi
    xorl %ebp, %ebp
    call kernel_entry
.Lreturned:
    cli
    hlt
    jmp .Lreturned
.size multiboot_entry, .-multiboot_entry

.section .rodata.boot,"a",@progbits
.balign 8
boot_gdt:
    .quad 0
    .quad 0x00af9b000000ffff /* 64-bit code: L=1, D=0, accessed=1 for future RO GDT */
    .quad 0x00cf93000000ffff /* flat writable data, accessed=1 for future RO GDT */
boot_gdt_end:
boot_gdt_descriptor:
    .word boot_gdt_end - boot_gdt - 1
    .long boot_gdt

.section .bss.boot,"aw",@nobits
.balign 4096
boot_pml4:
    .skip 4096
boot_pdpt:
    .skip 4096
boot_page_directory:
    .skip 4096
.balign 16
boot_stack_bottom:
    .skip 65536
.global boot_stack_top
boot_stack_top:
.section .note.GNU-stack,"",@progbits
