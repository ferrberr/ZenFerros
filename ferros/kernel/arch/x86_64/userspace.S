/* TASK-710: single-CPU, single active ring-3 invocation. Original linkage.
 * Caller validates user entry/stack/mappings and enters with IF clear.
 * No TLS, SIMD, CR3 switching, IST, or concurrent/nested user invocations.
 * Compile every reachable kernel/user function with no red zone/general GPRs.
 */
.section .text.userspace,"ax",@progbits
.code64

.global ferros_user_arch_init
.type ferros_user_arch_init, @function
ferros_user_arch_init:
    cli
    cld
    /* 104-byte architectural TSS: reserved fields and all IST slots zero. */
    leaq .Luser_tss(%rip), %rdi
    xorl %eax, %eax
    movl $13, %ecx
    rep stosq
    leaq .Luser_kernel_stack_top(%rip), %rax
    movq %rax, .Luser_tss+4(%rip) /* TSS.RSP0, intentionally unaligned. */
    /* I/O bitmap begins beyond TSS limit 103: all ring-3 port IO denied. */
    movw $104, .Luser_tss+102(%rip)
    leaq .Luser_tss(%rip), %rax
    movw %ax, .Luser_tss_descriptor+2(%rip)
    shrq $16, %rax
    movb %al, .Luser_tss_descriptor+4(%rip)
    shrq $8, %rax
    movb %al, .Luser_tss_descriptor+7(%rip)
    shrq $8, %rax
    movl %eax, .Luser_tss_descriptor+8(%rip)
    /* LTR marks the descriptor busy; allow a later serial reinitialization. */
    movb $0x89, .Luser_tss_descriptor+5(%rip)
    lgdt .Luser_gdt_pointer(%rip)
    /* CS cache already holds the identical selector-8 64-bit descriptor. */
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    xorw %ax, %ax
    movw %ax, %fs
    movw %ax, %gs
    movw $0x28, %ax
    ltr %ax
    movl $1, %eax
    ret
.size ferros_user_arch_init, .-ferros_user_arch_init

/* SysV (entry, user RSP, arg). Supplied RSP must be 8 mod 16, with a
 * loader-owned dummy return slot. Save six callee GPRs plus caller return
 * address on the controller stack; an exit/fault abandons the trap stack.
 */
.global ferros_user_enter
.type ferros_user_enter, @function
ferros_user_enter:
    cli
    cld
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rsp, .Luser_controller_rsp(%rip)
    pushq $0x1b
    pushq %rsi
    /* Fixed flags: bit1=1, IF=1; IOPL/NT/VM/TF/DF/AC all clear. */
    pushq $0x202
    pushq $0x23
    pushq %rdi
    movq %rdx, %rdi
    movw $0x1b, %ax
    movw %ax, %ds
    movw %ax, %es
    xorw %ax, %ax
    movw %ax, %fs
    movw %ax, %gs
    xorl %eax, %eax
    xorl %ebx, %ebx
    xorl %ecx, %ecx
    xorl %edx, %edx
    xorl %esi, %esi
    xorl %ebp, %ebp
    xorl %r8d, %r8d
    xorl %r9d, %r9d
    xorl %r10d, %r10d
    xorl %r11d, %r11d
    xorl %r12d, %r12d
    xorl %r13d, %r13d
    xorl %r14d, %r14d
    xorl %r15d, %r15d
    iretq
.size ferros_user_enter, .-ferros_user_enter

/* Called only by the active invocation's kernel dispatcher. Never returns to
 * that dispatcher: restore the suspended controller stack and return result.
 */
.global ferros_user_leave
.type ferros_user_leave, @function
ferros_user_leave:
    cli
    cld
    movq %rdi, %rax
    movw $0x10, %dx
    movw %dx, %ds
    movw %dx, %es
    movw %dx, %ss
    xorw %dx, %dx
    movw %dx, %fs
    movw %dx, %gs
    movq .Luser_controller_rsp(%rip), %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
.size ferros_user_leave, .-ferros_user_leave

.macro USER_ADDRESS_GETTER name, symbol
.global \name
.type \name, @function
\name:
    leaq \symbol(%rip), %rax
    ret
.size \name, .-\name
.endm
USER_ADDRESS_GETTER ferros_user_state, .Luser_state
USER_ADDRESS_GETTER ferros_user_tables, .Luser_tables
USER_ADDRESS_GETTER ferros_user_kernel_stack_bottom, .Luser_kernel_stack_bottom
USER_ADDRESS_GETTER ferros_user_kernel_stack_top, .Luser_kernel_stack_top
USER_ADDRESS_GETTER ferros_user_scratch, .Luser_scratch

USER_ADDRESS_GETTER ferros_ramfs_pool, __ferros_ramfs_storage
USER_ADDRESS_GETTER ferros_vfs_state, __ferros_vfs_state_storage

/* Writable supervisor GDT: LTR must set the TSS descriptor's busy bit. */
.section .data.userspace,"aw",@progbits
.balign 16
.Luser_gdt:
    .quad 0
    .quad 0x00af9b000000ffff /* 0x08: kernel code, identical to bootstrap. */
    .quad 0x00cf93000000ffff /* 0x10: kernel data. */
    .quad 0x00cff3000000ffff /* 0x1b: DPL3 writable data, accessed. */
    .quad 0x00affb000000ffff /* 0x23: DPL3 64-bit code, accessed. */
.Luser_tss_descriptor:
    .word 103
    .word 0
    .byte 0, 0x89, 0, 0 /* base pieces, present available 64-bit TSS. */
    .long 0, 0
.Luser_gdt_end:
.Luser_gdt_pointer:
    .word .Luser_gdt_end - .Luser_gdt - 1
    .quad .Luser_gdt

.section .bss.userspace,"aw",@nobits
.balign 4096
.Luser_state:
    .skip 4096 /* Public Zen-owned state, no hidden arch fields. */
.Luser_tables:
    .skip 8192 /* PD then PT; root owns mapping policy and contents. */
.Luser_kernel_stack_bottom:
    .skip 32768 /* Dedicated TSS.RSP0 trap stack. */
.Luser_kernel_stack_top:
.balign 16
.Luser_tss:
    .skip 104
.balign 8
.Luser_controller_rsp:
    .skip 8

.section .bss.vfs,"aw",@nobits
.balign 4096
__ferros_vfs_state_storage:
    .skip 4096
__ferros_ramfs_storage:
    .skip 1048576 /* 1MiB RAMFS storage */
.balign 16
.Luser_scratch:
    .skip 512 /* Kernel-side path staging for VFS syscalls. */
.section .note.GNU-stack,"",@progbits
