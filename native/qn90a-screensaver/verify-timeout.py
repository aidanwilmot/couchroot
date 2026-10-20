#!/usr/bin/env python3
"""Assemble and emulate the exact QN90A timeout thunk. No device connection.

Requires clang, pyelftools and unicorn (private research Python environment).
"""
import random
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import *

root = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as folder:
    obj = Path(folder) / 'policy.o'
    subprocess.run(['clang', '--target=armv7-linux-gnueabi', '-c',
                    str(root / 'timeout-policy.S'), '-o', str(obj)], check=True)
    with obj.open('rb') as stream:
        code = ELFFile(stream).get_section_by_name('.text').data()
embedded = re.search(r'const string TimeoutCode="([0-9a-f]+)"',
                     (root / 'Program.cs').read_text())[1]
assert code.hex() == embedded, 'C# policy bytes differ from assembly'
assert len(code) == 32
values = [struct.pack('<d', n) for n in
          (0, -0., 15, 30, 300, 600, 7199, 7200, 7200.00001, 7201, 14400,
           36000, -1, float('inf'), float('-inf'), float('nan'))]
rng = random.Random(90)
values += [rng.getrandbits(64).to_bytes(8, 'little') for _ in range(1000)]
saved = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
         UC_ARM_REG_SP, UC_ARM_REG_LR]
for bits in values:
    emu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    emu.mem_map(0x6000, 0x1000)
    emu.mem_map(0xbb000, 0x1000)
    emu.mem_write(0x6940, code)
    lo, hi = struct.unpack('<II', bits)
    emu.reg_write(UC_ARM_REG_R0, lo)
    emu.reg_write(UC_ARM_REG_R1, hi)
    for i, reg in enumerate(saved): emu.reg_write(reg, 0x80000 + 4 * i)
    emu.emu_start(0x6941, 0xbbf70, count=20)
    assert emu.reg_read(UC_ARM_REG_PC) == 0xbbf70, 'Wrong native destination'
    actual = struct.pack('<II', emu.reg_read(UC_ARM_REG_R0), emu.reg_read(UC_ARM_REG_R1))
    expected = struct.pack('<d', 300) if bits == struct.pack('<d', 7200) else bits
    assert actual == expected, (bits.hex(), actual.hex())
    for i, reg in enumerate(saved): assert emu.reg_read(reg) == 0x80000 + 4 * i
print(f'PASS: {len(values)} ARM cases; only exact 7200 becomes 300; ABI and tail call preserved')
