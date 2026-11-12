/* TASK-610: single-CPU, ring-0 SysV context primitives.
 * All callers use -mno-red-zone and -mgeneral-regs-only. The scheduler owns
 * policy; no CR3, SIMD, userspace, or nested-maskable-interrupt support here.
 */
.section .text.context,"ax",@progbits
.code64

/* IF must already be clear. Save only the six SysV callee-saved GPRs.
 * old_slot points to a u64 RSP slot; new_rsp points to the saved r15.
 * Initial 64-byte frame, from low address:
 *   r15, r14, r13, r12(thread id), rbx, rbp, trampoline, dummy-return.
 * A 16-byte-aligned stack top gives trampoline entry RSP == 8 (mod 16).
 */
.global ferros_context_switch
.type ferros_context_switch, @function
ferros_context_switch:
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rsp, (%rdi)
    movq %rsi, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
.size ferros_context_switch, .-ferros_context_switch

/* Getter, not the thread entry itself. */
.global ferros_thread_trampoline
.type ferros_thread_trampoline, @function
ferros_thread_trampoline:
    leaq .Lthread_trampoline(%rip), %rax
    ret
.size ferros_thread_trampoline, .-ferros_thread_trampoline

.type .Lthread_trampoline, @function
.Lthread_trampoline:
    subq $8, %rsp
    movq %r12, %rdi
    call thread_entry
    /* A returning worker is fatal; never consume its dummy return slot. */
    call thread_returned
    cli
.Lthread_halted:
    hlt
    jmp .Lthread_halted
.size .Lthread_trampoline, .-.Lthread_trampoline

.global ferros_scheduler_state
.type ferros_scheduler_state, @function
ferros_scheduler_state:
    leaq .Lscheduler_state(%rip), %rax
    ret
.size ferros_scheduler_state, .-ferros_scheduler_state

/* IDs 1..3 only; invalid IDs return zero. */
.global ferros_thread_stack_guard
.type ferros_thread_stack_guard, @function
ferros_thread_stack_guard:
    cmpq $1, %rdi
    je .Lguard_1
    cmpq $2, %rdi
    je .Lguard_2
    cmpq $3, %rdi
    je .Lguard_3
    xorl %eax, %eax
    ret
.Lguard_1:
    leaq .Lthread_1_guard(%rip), %rax
    ret
.Lguard_2:
    leaq .Lthread_2_guard(%rip), %rax
    ret
.Lguard_3:
    leaq .Lthread_3_guard(%rip), %rax
    ret
.size ferros_thread_stack_guard, .-ferros_thread_stack_guard

/* IDs 1..3 only; invalid IDs return zero. */
.global ferros_thread_stack_top
.type ferros_thread_stack_top, @function
ferros_thread_stack_top:
    cmpq $1, %rdi
    je .Ltop_1
    cmpq $2, %rdi
    je .Ltop_2
    cmpq $3, %rdi
    je .Ltop_3
    xorl %eax, %eax
    ret
.Ltop_1:
    leaq .Lthread_1_top(%rip), %rax
    ret
.Ltop_2:
    leaq .Lthread_2_top(%rip), %rax
    ret
.Ltop_3:
    leaq .Lthread_3_top(%rip), %rax
    ret
.size ferros_thread_stack_top, .-ferros_thread_stack_top

/* Return prior RFLAGS; the caller is now noninterruptible. */
.global ferros_irq_save
.type ferros_irq_save, @function
ferros_irq_save:
    pushfq
    popq %rax
    cli
    ret
.size ferros_irq_save, .-ferros_irq_save

/* Restore IF alone, never privileged/unrelated bits from supplied flags. */
.global ferros_irq_restore
.type ferros_irq_restore, @function
ferros_irq_restore:
    testq $0x200, %rdi
    jz .Lrestore_if_clear
    sti
    ret
.Lrestore_if_clear:
    cli
    ret
.size ferros_irq_restore, .-ferros_irq_restore

/* Probe all 15 GPRs plus a stack-local canary across a real interrupt.
 * Save originals before loading distinct positive imm32 patterns. Entry RSP
 * is 8 mod 16; 15 pushes and 16 local bytes leave the wait stack aligned.
 * No nested calls: the timer IRQ may suspend this entire frame. Leave IF off.
 */
.global ferros_context_probe
.type ferros_context_probe, @function
ferros_context_probe:
    cli
    pushq %rax
    pushq %rbx
    pushq %rcx
    pushq %rdx
    pushq %rsi
    pushq %rdi
    pushq %rbp
    pushq %r8
    pushq %r9
    pushq %r10
    pushq %r11
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $16, %rsp
    movq $0x13572468, (%rsp)
    movq $0x11010101, %rax
    movq $0x11020202, %rbx
    movq $0x11030303, %rcx
    movq $0x11040404, %rdx
    movq $0x11050505, %rsi
    movq $0x11060606, %rdi
    movq $0x11070707, %rbp
    movq $0x11080808, %r8
    movq $0x11090909, %r9
    movq $0x110a0a0a, %r10
    movq $0x110b0b0b, %r11
    movq $0x110c0c0c, %r12
    movq $0x110d0d0d, %r13
    movq $0x110e0e0e, %r14
    movq $0x110f0f0f, %r15
    sti
    hlt
    cli
    cmpq $0x11010101, %rax
    jne .Lprobe_bad
    cmpq $0x11020202, %rbx
    jne .Lprobe_bad
    cmpq $0x11030303, %rcx
    jne .Lprobe_bad
    cmpq $0x11040404, %rdx
    jne .Lprobe_bad
    cmpq $0x11050505, %rsi
    jne .Lprobe_bad
    cmpq $0x11060606, %rdi
    jne .Lprobe_bad
    cmpq $0x11070707, %rbp
    jne .Lprobe_bad
    cmpq $0x11080808, %r8
    jne .Lprobe_bad
    cmpq $0x11090909, %r9
    jne .Lprobe_bad
    cmpq $0x110a0a0a, %r10
    jne .Lprobe_bad
    cmpq $0x110b0b0b, %r11
    jne .Lprobe_bad
    cmpq $0x110c0c0c, %r12
    jne .Lprobe_bad
    cmpq $0x110d0d0d, %r13
    jne .Lprobe_bad
    cmpq $0x110e0e0e, %r14
    jne .Lprobe_bad
    cmpq $0x110f0f0f, %r15
    jne .Lprobe_bad
    cmpq $0x13572468, (%rsp)
    jne .Lprobe_bad
    movq $1, 8(%rsp)
    jmp .Lprobe_restore
.Lprobe_bad:
    movq $0, 8(%rsp)
.Lprobe_restore:
    movq 8(%rsp), %rax
    addq $16, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %r11
    popq %r10
    popq %r9
    popq %r8
    popq %rbp
    popq %rdi
    popq %rsi
    popq %rdx
    popq %rcx
    popq %rbx
    /* Discard original caller-saved RAX, returning the probe result. */
    addq $8, %rsp
    ret
.size ferros_context_probe, .-ferros_context_probe

/* All state is loader-zeroed BSS. Each guard is its own aligned 4 KiB page;
 * Zen unmaps guards before running workers. Stack tops are 16-byte aligned.
 */
.section .bss.context,"aw",@nobits
.balign 4096
.Lscheduler_state:
    .skip 4096

.balign 4096
.Lthread_1_guard:
    .skip 4096
.Lthread_1_stack:
    .skip 32768
.Lthread_1_top:

.balign 4096
.Lthread_2_guard:
    .skip 4096
.Lthread_2_stack:
    .skip 32768
.Lthread_2_top:

.balign 4096
.Lthread_3_guard:
    .skip 4096
.Lthread_3_stack:
    .skip 32768
.Lthread_3_top:

.section .note.GNU-stack,"",@progbits
