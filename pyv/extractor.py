from pyv.csr import CSRUnit
from pyv.module import Module
from pyv.port import Input, Output, Wire, Constant
from pyv.reg import Reg, Regfile
from pyv.mem import ReadPort, WritePort
from pyv.simulator import Simulator
import pyv.isa as isa
from pyv.util import getBit, getBits, MASK_32, XLEN, msb_32, signext
from pyv.log import logger
from dataclasses import dataclass, field

STOP_INSTR = 0xffffffff

@dataclass
class IFXT_t:
    inst: int = 0

@dataclass
class TXT_t:
    flush_bits_ready: bool = False

@dataclass
class XTIF_t:
    active: bool = False
    ready: bool = False
    flush_bits: bool = False

class Extractor(Module):
    """Entropy extractor.

    Inputs:
        IFXT_t: Interface from IFStage (instruction)
        TXT_t:  Interface from top (memory flush ready signal)
    
    Outputs:
        XTIF_t: Interface to IFStage (active, ready, flush)
        eb_o: Entropy bits output
    """

    def __init__(self, regf: Regfile, csr: CSRUnit):
        super().__init__()
        self.entropy_bits = []     # TODO turn into a register
        self.regfile = regf
        self.csr = csr
        self.ready = False
        self.ready_out = False
        self.active_out = True
        self.flush_bits = False

        self.IFXT_i = Input(IFXT_t)     # fetch module in: instruction
        self.TXT_i = Input(TXT_t)       # top in
        self.XTIF_o = Output(XTIF_t)    # signals out
        self.eb_o = Output(list)        # entropy bits out
    
    def process(self):
        top_val: TXT_t = self.TXT_i.read()
        flush_ready = top_val.flush_bits_ready

        val: IFXT_t = self.IFXT_i.read()
        inst = val.inst

        # set ready signal
        if inst == STOP_INSTR:
            self.ready = True
        
        # set ready output
        if self.ready and self.active_out:
            self.ready_out = True
        
        # set active output
        if self.ready and self.active_out:
            self.active_out = False

        opcode = getBits(inst, 6, 2)
        funct7 = getBits(inst, 31, 25)
        # Get entropy bits from funct7
        if opcode == isa.OPCODES['OP']:
            self.entropy_bits.append(self.get_entropy_bits(funct7))

        # set flush signal
        if (self.flush_bits or len(self.entropy_bits) == 16 or (self.ready and len(self.entropy_bits) > 0)) and not flush_ready:
            self.flush_bits = True
        else:
            self.flush_bits = False

        # write output
        self.XTIF_o.write(XTIF_t(
            self.active_out, self.ready_out, self.flush_bits
        ))
        self.eb_o.write(self.entropy_bits)
    
    def get_entropy_bits(self, funct7):
        bit_high = getBit(funct7, 6)
        bits_low = getBits(funct7, 4, 0)
        bits = str(bin(bit_high))[2:] + str(bin(bits_low))[2:]
        entropy_bits = int(bits, 2)
        return entropy_bits
