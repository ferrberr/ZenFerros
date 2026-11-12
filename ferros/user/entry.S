/* Ring-3 architecture/syscall adapters only. Policy and checks live in Zen.
 * int0x80 ABI: RAX=number; RDI/RSI/RDX=arguments; RAX=result.
 * The kernel enters _user_start with RDI=case id and a valid user stack.
 */
.section .text.entry,"ax",@progbits
.code64
.global _user_start
.type _user_start,@function
_user_start:
    cld
    andq $-16,%rsp /* Normalize an ABI-style entry stack before making a call. */
    call user_entry
    movl $2,%eax
    movl $255,%edi
    xorl %esi,%esi
    xorl %edx,%edx
    int $0x80
    ud2
.size _user_start,.-_user_start

.section .text.user,"ax",@progbits
.global user_syscall
.type user_syscall,@function
user_syscall:
    movq %rdi,%rax
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    int $0x80
    ret
.size user_syscall,.-user_syscall

.global user_cpl
.type user_cpl,@function
user_cpl:
    xorl %eax,%eax
    movw %cs,%ax
    andl $3,%eax
    ret
.size user_cpl,.-user_cpl

.global user_rflags
.type user_rflags,@function
user_rflags:
    pushfq
    popq %rax
    ret
.size user_rflags,.-user_rflags

.global user_storage_address
.type user_storage_address,@function
user_storage_address:
    leaq __user_storage(%rip),%rax
    ret
.size user_storage_address,.-user_storage_address
.global user_storage_end
.type user_storage_end,@function
user_storage_end:
    leaq __user_storage_end(%rip),%rax
    ret
.size user_storage_end,.-user_storage_end

/* Check trap linkage preserves GPRs other than the result register. */
.global user_syscall_preserved
.type user_syscall_preserved,@function
user_syscall_preserved:
    pushq %rbx
    pushq %rbp
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movl $0x1111,%ebx
    movl $0x2222,%ebp
    movl $0x3333,%r12d
    movl $0x4444,%r13d
    movl $0x5555,%r14d
    movl $0x6666,%r15d
    movl $0x7777,%edi
    movl $0x8888,%esi
    movl $0x9999,%edx
    movl $0xaaaa,%ecx
    movl $0xbbbb,%r8d
    movl $0xcccc,%r9d
    movl $0xdddd,%r10d
    movl $0xeeee,%r11d
    movl $0xffff,%eax
    int $0x80
    cmpq $-38,%rax
    jne .Lregister_failure
    cmpq $0x1111,%rbx
    jne .Lregister_failure
    cmpq $0x2222,%rbp
    jne .Lregister_failure
    cmpq $0x3333,%r12
    jne .Lregister_failure
    cmpq $0x4444,%r13
    jne .Lregister_failure
    cmpq $0x5555,%r14
    jne .Lregister_failure
    cmpq $0x6666,%r15
    jne .Lregister_failure
    cmpq $0x7777,%rdi
    jne .Lregister_failure
    cmpq $0x8888,%rsi
    jne .Lregister_failure
    cmpq $0x9999,%rdx
    jne .Lregister_failure
    cmpq $0xaaaa,%rcx
    jne .Lregister_failure
    cmpq $0xbbbb,%r8
    jne .Lregister_failure
    cmpq $0xcccc,%r9
    jne .Lregister_failure
    cmpq $0xdddd,%r10
    jne .Lregister_failure
    cmpq $0xeeee,%r11
    jne .Lregister_failure
    movl $1,%eax
    jmp .Lregister_done
.Lregister_failure:
    xorl %eax,%eax
.Lregister_done:
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbp
    popq %rbx
    ret
.size user_syscall_preserved,.-user_syscall_preserved

.global user_fault_read_kernel
.type user_fault_read_kernel,@function
user_fault_read_kernel:
    movl $0x100000,%eax
    movq (%rax),%rax
    ret
.size user_fault_read_kernel,.-user_fault_read_kernel
.global user_fault_write_text
.type user_fault_write_text,@function
user_fault_write_text:
    movl $0x40000000,%eax
    movb $0x90,(%rax)
    ret
.size user_fault_write_text,.-user_fault_write_text
.global user_fault_cli
.type user_fault_cli,@function
user_fault_cli:
    cli
    ret
.size user_fault_cli,.-user_fault_cli
.global user_fault_execute_stack
.type user_fault_execute_stack,@function
user_fault_execute_stack:
    subq $16,%rsp
    movb $0xc3,(%rsp)
    movq %rsp,%rax
    call *%rax
    addq $16,%rsp
    ret
.size user_fault_execute_stack,.-user_fault_execute_stack
.global user_fault_read_guard
.type user_fault_read_guard,@function
user_fault_read_guard:
    movl $0x401fb000,%eax
    movq (%rax),%rax
    ret
.size user_fault_read_guard,.-user_fault_read_guard
.global user_fault_int81
.type user_fault_int81,@function
user_fault_int81:
    int $0x81
    ret
.size user_fault_int81,.-user_fault_int81

.section .bss.user,"aw",@nobits
.balign 4096
__user_storage:
    .skip 4096
__user_storage_end:
.section .note.GNU-stack,"",@progbits
