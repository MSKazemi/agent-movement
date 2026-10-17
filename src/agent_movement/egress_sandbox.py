"""Linux/x86_64 synthetic-agent *egress* fence. Experimental, not a sandbox.

A trusted launcher installs an irreversible seccomp-BPF rule before running
untrusted Python source in a distinct OS process. It blocks socket and process
creation, including raw syscalls, while allowing an inherited pipe broker.

It DOES NOT confine filesystem access, inherited non-pipe FDs, compromised hosts,
IPC already open, device access, covert channels, or remote participants.
"""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import runpy
import sys
from pathlib import Path

# Linux x86_64 syscall numbers; refuse another architecture rather than silently
# applying the wrong filter. Kill attempts to switch to an unexpected ABI.
_DENY_SYSCALLS = frozenset({
    41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,  # socket family
    56, 57, 58, 59,  # clone/fork/vfork/execve
    62, 101, 200, 234,  # kill/ptrace/tkill/tgkill (OS-process tampering)
    288, 299, 307, 310, 311,  # accept4/recvmmsg/sendmmsg/process_vm_readv/writev
    322, 425, 426, 427, 434, 435, 438,  # execveat/io_uring/pidfd_open/clone3/pidfd_getfd
})

_LD_W_ABS = 0x20
_JMP_JEQ_K = 0x15
_JMP_JGE_K = 0x35
_RET_K = 0x06
_ARCH_X86_64 = 0xC000003E
_X32_BIT = 0x40000000
_RET_KILL_PROCESS = 0x80000000
_RET_ALLOW = 0x7FFF0000
_RET_ERRNO = 0x00050000
_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2


class _SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]


class _SockFProg(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_SockFilter))]


def supported() -> bool:
    """Only the Linux x86_64 syscall ABI has been audited for this experiment."""
    return sys.platform == "linux" and platform.machine() == "x86_64"


def install_egress_fence() -> None:
    """Trusted-launcher-only installation. Raises instead of running unfenced.

    The BPF filter is enforced by the kernel and inherited by every thread and
    process (although the policy denies creating either). This isn't an OS
    container or a complete data-exfiltration prevention policy.
    """
    if not supported():
        raise RuntimeError("seccomp egress experiment requires Linux x86_64")

    def stmt(code: int, k: int) -> _SockFilter:
        return _SockFilter(code, 0, 0, k)

    def jmp(code: int, k: int, jt: int, jf: int) -> _SockFilter:
        return _SockFilter(code, jt, jf, k)

    deny = _RET_ERRNO | errno.EPERM
    rules = [
        stmt(_LD_W_ABS, 4),  # seccomp_data.arch
        jmp(_JMP_JEQ_K, _ARCH_X86_64, 1, 0),
        stmt(_RET_K, _RET_KILL_PROCESS),
        stmt(_LD_W_ABS, 0),  # seccomp_data.nr
        jmp(_JMP_JGE_K, _X32_BIT, 0, 1),
        stmt(_RET_K, _RET_KILL_PROCESS),
    ]
    for number in sorted(_DENY_SYSCALLS):
        rules.append(jmp(_JMP_JEQ_K, number, 0, 1))
        rules.append(stmt(_RET_K, deny))
    rules.append(stmt(_RET_K, _RET_ALLOW))

    array_type = _SockFilter * len(rules)
    filters = array_type(*rules)
    program = _SockFProg(len(rules), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                          ctypes.c_ulong, ctypes.c_ulong]
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
    if libc.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER,
                  ctypes.addressof(program), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_SECCOMP failed")


def _drop_worker_privileges() -> None:
    """Irreversibly drop supplementary, saved, effective and real credentials.

    Only the trusted operator may choose these IDs. The script is run AFTER
    dropping credentials and installing seccomp; if anything fails, never run it.
    """
    uid_text = os.environ.get("AMV_ISOLATION_UID")
    gid_text = os.environ.get("AMV_ISOLATION_GID")
    if uid_text is None and gid_text is None:
        return  # The existing same-UID test profile remains clearly separate.
    if (uid_text is None or gid_text is None or not uid_text.isdecimal()
            or not gid_text.isdecimal() or os.geteuid() != 0):
        raise RuntimeError("privileged worker isolation configuration unavailable")
    uid, gid = int(uid_text), int(gid_text)
    if not 1 <= uid <= 65534 or not 1 <= gid <= 65534:
        raise RuntimeError("invalid non-root worker credentials")
    # A root supervisor launches only trusted module code here; do not import
    # attacker-controlled modules between this point and the irreversible drop.
    os.setgroups([])
    os.setresgid(gid, gid, gid)
    os.setresuid(uid, uid, uid)
    if (os.getresuid() != (uid, uid, uid) or os.getresgid() != (gid, gid, gid)
            or os.getgroups()):
        raise RuntimeError("worker privilege isolation was not established")
    # Linux-only import: preserve core's stdlib imports on other platforms.
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m agent_movement.egress_sandbox SCRIPT.py")
    script = Path(sys.argv[1]).resolve(strict=True)
    if not script.is_file():
        raise SystemExit("not a script")
    # The trusted launcher has not imported attacker-controlled code yet.
    # Never fall back to same-UID execution when an explicit UID is requested.
    _drop_worker_privileges()
    install_egress_fence()
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
