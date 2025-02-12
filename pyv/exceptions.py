"""Custom exceptions for Py-V
"""

class IllegalInstructionException(Exception):
    def __init__(self, pc, inst):
        msg = f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"
        super().__init__(msg)

class PCOutOfBoundException(Exception):
    def __init__(self, pc):
        msg = f"PC out of bound: {pc:08X}"
        super().__init__(msg)

class SegmentationFaultException(Exception):
    def __init__(self, addr):
        msg = f"Attempt to access invalid memory address: {addr:08X}"
        super().__init__(msg)

class InstructionAddressMisalignedException(Exception):
    def __init__(self, pc):
        msg = f"Target instruction address misaligned exception at PC = 0x{pc:08X}"
        super().__init__(msg)
