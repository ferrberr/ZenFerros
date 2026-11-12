/* TASK-510/710: shared ring-0/ring-3 interrupt linkage. Policy lives in Zen.
 * No swapgs, IST stacks, SIMD state, or nested maskable IRQ policy.
 * The compiler uses -mno-red-zone and -mgeneral-regs-only for all Zen handlers.
 */
.section .text.interrupts,"ax",@progbits
.code64

/* Normalize the entry stack to [vector,error,RIP,CS,RFLAGS,...]. */
.macro ISR vector, cpu_error=0
.type __ferros_isr_\vector, @function
__ferros_isr_\vector:
.if !\cpu_error
    pushq $0
.endif
    pushq $\vector
    jmp __ferros_isr_common
.size __ferros_isr_\vector, .-__ferros_isr_\vector
.endm
ISR 0, 0
ISR 1, 0
ISR 2, 0
ISR 3, 0
ISR 4, 0
ISR 5, 0
ISR 6, 0
ISR 7, 0
ISR 8, 1
ISR 9, 0
ISR 10, 1
ISR 11, 1
ISR 12, 1
ISR 13, 1
ISR 14, 1
ISR 15, 0
ISR 16, 0
ISR 17, 1
ISR 18, 0
ISR 19, 0
ISR 20, 0
ISR 21, 1
ISR 22, 0
ISR 23, 0
ISR 24, 0
ISR 25, 0
ISR 26, 0
ISR 27, 0
ISR 28, 0
ISR 29, 1
ISR 30, 1
ISR 31, 0
ISR 32, 0
ISR 33, 0
ISR 34, 0
ISR 35, 0
ISR 36, 0
ISR 37, 0
ISR 38, 0
ISR 39, 0
ISR 40, 0
ISR 41, 0
ISR 42, 0
ISR 43, 0
ISR 44, 0
ISR 45, 0
ISR 46, 0
ISR 47, 0
ISR 128, 0
ISR 255, 0

.type __ferros_isr_common, @function
__ferros_isr_common:
    /* Save every GPR except RSP, which is restored through the saved base. */
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
    cld /* Interrupted DF is restored by IRETQ from the CPU's RFLAGS frame. */
    movq %rsp, %rbx /* Callee-saved across the System V Zen dispatcher. */
    movq 120(%rbx), %rdi
    movq 128(%rbx), %rsi
    /* frame=RIP; saved RAX=-24, RDI=-64, RSI=-56, RDX=-48.
     * CPL3 CPU tail is RIP,CS,RFLAGS,userRSP,userSS; RSP0 comes from TSS. */
    leaq 136(%rbx), %rdx
    movq %cr2, %rcx
    andq $-16, %rsp
    call interrupt_dispatch
    movq %rbx, %rsp
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
    popq %rax
    addq $16, %rsp /* Discard normalized vector and error. */
    iretq
.size __ferros_isr_common, .-__ferros_isr_common

.global ferros_isr_address
.type ferros_isr_address, @function
ferros_isr_address:
    xorl %eax, %eax
    cmpq $256, %rdi
    jae .Lisr_address_return
    leaq __ferros_isr_128(%rip), %rax
    cmpq $128, %rdi
    je .Lisr_address_return
    leaq __ferros_isr_255(%rip), %rax
    cmpq $48, %rdi
    jae .Lisr_address_return
    leaq __ferros_isr_table(%rip), %rax
    movq (%rax,%rdi,8), %rax
.Lisr_address_return:
    ret
.size ferros_isr_address, .-ferros_isr_address

.global ferros_load_idt
.type ferros_load_idt, @function
ferros_load_idt:
    subq $16, %rsp
    movw %si, (%rsp)
    movq %rdi, 2(%rsp)
    lidt (%rsp)
    addq $16, %rsp
    ret
.size ferros_load_idt, .-ferros_load_idt

.global ferros_interrupt_disable
.type ferros_interrupt_disable, @function
ferros_interrupt_disable:
    cli
    ret
.size ferros_interrupt_disable, .-ferros_interrupt_disable

.global ferros_wait_interrupt
.type ferros_wait_interrupt, @function
ferros_wait_interrupt:
    /* STI blocks delivery until after HLT; no lost-wakeup window here. */
    sti
    hlt
    cli
    ret
.size ferros_wait_interrupt, .-ferros_wait_interrupt

.global ferros_breakpoint
.type ferros_breakpoint, @function
ferros_breakpoint:
    int3
    ret
.size ferros_breakpoint, .-ferros_breakpoint

.global ferros_probe_null
.type ferros_probe_null, @function
ferros_probe_null:
    xorl %eax, %eax
__ferros_null_fault_site:
    movq (%rax), %rax
__ferros_null_fault_resume:
    ret
.size ferros_probe_null, .-ferros_probe_null

.global ferros_probe_write_ro
.type ferros_probe_write_ro, @function
ferros_probe_write_ro:
    leaq __ferros_ro_fault_byte(%rip), %rax
__ferros_ro_fault_site:
    movb $0x5a, (%rax)
__ferros_ro_fault_resume:
    ret
.size ferros_probe_write_ro, .-ferros_probe_write_ro

.macro ADDRESS_GETTER name, symbol
.global \name
.type \name, @function
\name:
    leaq \symbol(%rip), %rax
    ret
.size \name, .-\name
.endm
ADDRESS_GETTER ferros_null_fault_site, __ferros_null_fault_site
ADDRESS_GETTER ferros_null_fault_resume, __ferros_null_fault_resume
ADDRESS_GETTER ferros_ro_fault_site, __ferros_ro_fault_site
ADDRESS_GETTER ferros_ro_fault_resume, __ferros_ro_fault_resume
ADDRESS_GETTER ferros_ro_fault_address, __ferros_ro_fault_byte

.section .rodata.interrupts,"a",@progbits
.balign 8
__ferros_isr_table:
    .quad __ferros_isr_0
    .quad __ferros_isr_1
    .quad __ferros_isr_2
    .quad __ferros_isr_3
    .quad __ferros_isr_4
    .quad __ferros_isr_5
    .quad __ferros_isr_6
    .quad __ferros_isr_7
    .quad __ferros_isr_8
    .quad __ferros_isr_9
    .quad __ferros_isr_10
    .quad __ferros_isr_11
    .quad __ferros_isr_12
    .quad __ferros_isr_13
    .quad __ferros_isr_14
    .quad __ferros_isr_15
    .quad __ferros_isr_16
    .quad __ferros_isr_17
    .quad __ferros_isr_18
    .quad __ferros_isr_19
    .quad __ferros_isr_20
    .quad __ferros_isr_21
    .quad __ferros_isr_22
    .quad __ferros_isr_23
    .quad __ferros_isr_24
    .quad __ferros_isr_25
    .quad __ferros_isr_26
    .quad __ferros_isr_27
    .quad __ferros_isr_28
    .quad __ferros_isr_29
    .quad __ferros_isr_30
    .quad __ferros_isr_31
    .quad __ferros_isr_32
    .quad __ferros_isr_33
    .quad __ferros_isr_34
    .quad __ferros_isr_35
    .quad __ferros_isr_36
    .quad __ferros_isr_37
    .quad __ferros_isr_38
    .quad __ferros_isr_39
    .quad __ferros_isr_40
    .quad __ferros_isr_41
    .quad __ferros_isr_42
    .quad __ferros_isr_43
    .quad __ferros_isr_44
    .quad __ferros_isr_45
    .quad __ferros_isr_46
    .quad __ferros_isr_47
__ferros_ro_fault_byte:
    .byte 0xa5
.section .note.GNU-stack,"",@progbits
