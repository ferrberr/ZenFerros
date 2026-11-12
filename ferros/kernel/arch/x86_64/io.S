/* Minimal architecture primitives, authored for TASK-410.
 * UART policy/configuration/polling and all message output live in Zen.
 * System V AMD64 scalar arguments: DI=port, SIL/ESI=value; AL=u8 result.
 * These privileged instructions may run only in a guest kernel, never as host
 * userspace test code. Unit tests must supply mock C implementations instead.
 */
.section .text,"ax",@progbits
.code64
.global ferros_in8
.type ferros_in8, @function
ferros_in8:
    movl %edi, %edx
    xorl %eax, %eax
    inb %dx, %al
    ret
.size ferros_in8, .-ferros_in8

.global ferros_out8
.type ferros_out8, @function
ferros_out8:
    movl %edi, %edx
    movl %esi, %eax
    outb %al, %dx
    ret
.size ferros_out8, .-ferros_out8

.global ferros_out32
.type ferros_out32, @function
ferros_out32:
    movl %edi, %edx
    movl %esi, %eax
    outl %eax, %dx
    ret
.size ferros_out32, .-ferros_out32

.global ferros_halt
.type ferros_halt, @function
ferros_halt:
    cli
.Lhalt:
    hlt
    jmp .Lhalt
.size ferros_halt, .-ferros_halt
/* CPU-register operations: policy and address validation remain in Zen. */
.global ferros_read_cr0
.type ferros_read_cr0, @function
ferros_read_cr0:
    movq %cr0, %rax
    ret
.size ferros_read_cr0, .-ferros_read_cr0

.global ferros_read_cr3
.type ferros_read_cr3, @function
ferros_read_cr3:
    movq %cr3, %rax
    ret
.size ferros_read_cr3, .-ferros_read_cr3

.global ferros_load_cr3
.type ferros_load_cr3, @function
ferros_load_cr3:
    movq %rdi, %cr3
    ret
.size ferros_load_cr3, .-ferros_load_cr3

.global ferros_invlpg
.type ferros_invlpg, @function
ferros_invlpg:
    invlpg (%rdi)
    ret
.size ferros_invlpg, .-ferros_invlpg

.global ferros_enable_nx
.type ferros_enable_nx, @function
ferros_enable_nx:
    pushq %rbx
    movl $0x80000000, %eax
    cpuid
    cmpl $0x80000001, %eax
    jb .Lno_nx
    movl $0x80000001, %eax
    cpuid
    btl $20, %edx
    jnc .Lno_nx
    movl $0xc0000080, %ecx
    rdmsr
    btsl $11, %eax /* EFER.NXE, preserving LME and every other EFER bit. */
    wrmsr
    movl $1, %eax
    popq %rbx
    ret
.Lno_nx:
    xorl %eax, %eax
    popq %rbx
    ret
.size ferros_enable_nx, .-ferros_enable_nx

/* All address getters are pure: host-safe tests may call these without running
 * privileged entry/IO/interrupt instructions. Storage is reserved, not allocated.
 */
.macro ADDRESS_GETTER name, symbol
.global \name
.type \name, @function
\name:
    leaq \symbol(%rip), %rax
    ret
.size \name, .-\name
.endm
ADDRESS_GETTER ferros_memory_state, __ferros_memory_state_storage
ADDRESS_GETTER ferros_pmm_bitmap, __ferros_pmm_bitmap_storage
ADDRESS_GETTER ferros_page_tables, __ferros_page_tables_storage
ADDRESS_GETTER ferros_heap_start, __ferros_heap_storage_start
ADDRESS_GETTER ferros_heap_end, __ferros_heap_storage_end
ADDRESS_GETTER ferros_interrupt_state, __ferros_interrupt_state_storage
ADDRESS_GETTER ferros_idt_address, __ferros_idt_storage
ADDRESS_GETTER ferros_kernel_end, __image_end
ADDRESS_GETTER ferros_text_start, __text_start
ADDRESS_GETTER ferros_text_end, __text_end
ADDRESS_GETTER ferros_rodata_start, __rodata_start
ADDRESS_GETTER ferros_rodata_end, __rodata_end

.section .bss.kernel.memory,"aw",@nobits
.balign 4096
__ferros_memory_state_storage:
    .skip 4096
__ferros_pmm_bitmap_storage:
    .skip 8192
__ferros_page_tables_storage:
    .skip 147456 /* 36 pages: PML4, PDPT, PD, 32 PTs, one spare. */
__ferros_heap_storage_start:
    .skip 65536
__ferros_heap_storage_end:
__ferros_interrupt_state_storage:
    .skip 4096
__ferros_idt_storage:
    .skip 4096
.section .note.GNU-stack,"",@progbits
