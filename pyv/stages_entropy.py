from pyv.csr import CSRUnit
from pyv.module import Module
from pyv.port import Input, Output, Wire, Constant
from pyv.reg import Reg, Regfile
from pyv.mem import ReadPort, WritePort
from pyv.simulator import Simulator
from pyv.extractor import IFXT_t, XTIF_t, TXT_t
from pyv.exceptions import PCOutOfBoundException, InstructionAddressMisalignedException, IllegalInstructionException
import pyv.isa as isa
from pyv.util import getBit, getBits, MASK_32, XLEN, msb_32, signext
from pyv.log import logger
from dataclasses import dataclass


@dataclass
class IFID_t:
    inst: int = 0
    pc: int = 0


@dataclass
class IDEX_t:
    rs1: int = 0
    rs2: int = 0
    imm: int = 0
    pc: int = 0
    rd: int = 0
    we: int = 0
    wb_sel: int = 0
    opcode: int = 0
    funct3: int = 0
    funct7: int = 0
    mem: int = 0
    csr_addr: int = 0
    csr_read_val: int = 0
    csr_write_en: bool = False


@dataclass
class EXMEM_t:
    rd: int = 0
    we: int = 0
    wb_sel: int = 0
    take_branch: bool = False
    alu_res: int = 0
    pc4: int = 0
    rs2: int = 0
    mem: int = 0
    funct3: int = 0
    csr_addr: int = 0
    csr_read_val: int = 0
    csr_write_en: bool = False
    csr_write_val: int = 0


@dataclass
class MEMWB_t:
    rd: int = 0
    we: int = 0
    alu_res: int = 0
    pc4: int = 0
    mem_rdata: int = 0
    wb_sel: int = 0
    csr_addr: int = 0
    csr_read_val: int = 0
    csr_write_en: bool = False
    csr_write_val: int = 0


LOAD = 1
STORE = 2

ENTROPY_ADDRESS = 1024


class IFStage(Module):
    """Instruction Fetch Stage.

    Inputs:
        npc_i: Next program counter (PC)
        XTIF_i: Input from entropy extractor (entropy and signals)

    Outputs:
        IFID_o: Interface to IDStage
        IFXT_o: Interface to entropy extractor (instruction)
        XT_o: Output of entropy data and signals
    """

    def __init__(self, imem: ReadPort):
        super().__init__()
        # Next PC
        self.npc_i = Input(int)
        self.IFID_o = Output(IFID_t)

        #### Entropy extractor integration
        self.IFXT_o = Output(IFXT_t)     # output to extractor: instruction
        self.XTIF_i = Input(XTIF_t)      # input from extractor: entropy, active, ready 
        self.XT_o = Output(XTIF_t)       # output of entropy and signals from IF out
        self.XT_w = Wire(XTIF_t, [self.writeOutput])
        self.XT_w << self.XTIF_i

        self.npc_w = Wire(int)
        self.epc_reg = Reg(int, -4, [self.process])
        self.npc_w << self.epc_reg.next

        # Program counter (PC)
        self.pc_reg = Reg(int, -4)

        # Instruction register (IR)
        self.ir_reg = Reg(int, 0x00000013)

        # Helper wires
        self.pc_reg_w = Wire(int, [self.writeOutput])
        self.ir_reg_w = Wire(int, [self.writeOutput])    # wire writing to extractor output
        self.pc_reg_w << self.pc_reg.cur
        self.ir_reg_w << self.ir_reg.cur
        self.ir_out_w = Wire(int, [self.writeOutput])    # wire writing to next stages

        self.ir_out_reg = Reg(int, 0x00000013, [self.writeOutput])    # reg writing to next stages

        # Instruction memory
        # Force read-enable
        self.const1 = Constant(True)
        self.const2 = Constant(4)
        imem.re_i << self.const1
        imem.addr_i << self.npc_w
        imem.width_i << self.const2
        self.ir_reg.next << imem.rdata_o

        # Connect next PC to input of PC reg
        # self.pc_reg.next << self.npc_w        # connect to a wire that receives either next pc or zero
        self.pc_reg.next << self.epc_reg.next        # connect to a wire that receives either next pc or zero
    
    def process(self):
        XT = self.XT_w.read()
        ready = XT.ready
        active = XT.active
        flush = XT.flush_bits
        
        # split the PC
        if active:
            if flush:
                self.epc_reg.next.write(self.epc_reg.cur.read())
            else:
                self.epc_reg.next.write(self.epc_reg.cur.read() + 4)
        elif ready:
            self.epc_reg.next.write(-8)
        elif not flush:
            self.epc_reg.next.write(self.npc_i.read())
        
        # split the instruction
        if active or flush or ready:
            self.ir_out_reg.next.write(0x00000013)
        elif self.epc_reg.cur.read()<=-4:
            self.ir_out_reg.cur.write(0x00000013)
        else:
            self.ir_out_reg.cur.write(self.ir_reg_w.read())

    def writeOutput(self):
        # self.IFID_o.write(IFID_t(self.ir_out_w.read(), self.pc_reg_w.read()))
        self.IFID_o.write(IFID_t(self.ir_out_reg.cur.read(), self.pc_reg_w.read()))
        self.IFXT_o.write(IFXT_t(self.ir_reg_w.read()))      # output instruction to extractor
        self.XT_o.write(self.XT_w.read())


class IDStage(Module):
    """Instruction decode stage.

    Inputs:
        IFID_i: Interface from IFStage

    Outputs:
        IDEX_o: Interface to EXStage
    """

    def __init__(self, regf: Regfile, csr: CSRUnit):
        super().__init__()
        self.regfile = regf
        self.csr = csr
        
        self.pc_bound = 0

        self.registerStableCallbacks([self.check_exception])
        self.STOP_INSTR = 0xffffffff
        self.NOP_INSTR = 0x00000013

        # Inputs
        self.IFID_i = Input(IFID_t)

        # Outputs
        self.IDEX_o = Output(IDEX_t)

    def process(self):
        # Read inputs
        val: IFID_t = self.IFID_i.read()
        inst = val.inst
        self.pc = val.pc
        logger.info(f"Fetched instruction code: {inst:08X}")
        logger.info(f"Current PC: {self.pc:08X}")

        curr_cycle = Simulator.globalSim.getCycles() - 1
        fi_cycle = Simulator.globalSim.getFICycle()

        # entropy extraction stop instruction replacement
        if inst == self.STOP_INSTR:
            inst = self.NOP_INSTR

        # Determine opcode (inst[6:2])
        opcode = getBits(inst, 6, 2)

        if fi_cycle and curr_cycle == fi_cycle:
            ### Inject fault
            inst = self.inject_fault(inst, 12, 2, "flip")
            logger.info(f"Instruction after FI: {inst:08X}")

        # funct3, funct7
        funct3 = getBits(inst, 14, 12)
        if opcode == isa.OPCODES['OP']:
            f7_bit = getBit(inst, 30)
            funct7 = int(f"0{f7_bit}00000", 2)
        else:
            funct7 = getBits(inst, 31, 25)

        self.check_exception_inputs = (self.pc, inst, opcode, funct3, funct7)

        # Determine register indeces
        rs1_idx = getBits(inst, 19, 15)
        rs2_idx = getBits(inst, 24, 20)
        rd_idx = getBits(inst, 11, 7)

        # Read regfile
        rs1 = self.regfile.read(rs1_idx)
        rs2 = self.regfile.read(rs2_idx)

        # Decode immediate
        imm = self.decImm(opcode, inst)

        # Determine register file write enable
        we = self.we(opcode, funct3)

        # Determine what to write-back into regfile
        wb_sel = self.wb_sel(opcode, funct3)

        # Determine none/load/store
        mem = self.mem_sel(opcode)

        # CSR
        csr_addr, csr_read_val, csr_write_en, csr_isImm, csr_uimm = \
            self.dec_csr(inst, opcode, funct3, rd_idx, rs1_idx)
        if csr_isImm:
            rs1 = csr_uimm

        # Outputs
        self.IDEX_o.write(IDEX_t(
            rs1, rs2, imm, self.pc, rd_idx, we, wb_sel,
            opcode, funct3, funct7, mem, csr_addr, csr_read_val, csr_write_en))
    
    def inject_fault(self, inst, index, num_bits, injection_type):
        if injection_type == "flip":
            fault = int('0'*(32-(index+num_bits)) + '1'*num_bits + '0'*(index), 2)
            inst_fi = inst ^ fault
        elif injection_type == "set":
            fault = int('0'*(32-(index+num_bits)) + '1'*num_bits + '0'*(index), 2)
            inst_fi = inst | fault
        elif injection_type == "clear":
            fault = int('1'*(32-(index+num_bits)) + '0'*num_bits + '1'*(index), 2)
            inst_fi = inst & fault
        else:
            return inst
        return inst_fi
    
    def is_csr(self, opcode, f3):
        return opcode == isa.OPCODES["SYSTEM"] and f3 in isa.CSR_F3.values()

    def is_csr_imm(self, f3):
        return f3 in [
            isa.CSR_F3["CSRRWI"],
            isa.CSR_F3["CSRRSI"],
            isa.CSR_F3["CSRRCI"]
        ]

    def we(self, opcode, f3):
        return (
            opcode in isa.REG_OPS
            or self.is_csr(opcode, f3)
        )

    def mem_sel(self, opcode):
        """Generates control signal for memory access.

        Args:
            opcode: Opcode of current instruction.

        Returns:
            A special value when the instruction is LOAD/STORE.
            0 otherwise.
        """
        if opcode == isa.OPCODES['LOAD']:
            return LOAD
        elif opcode == isa.OPCODES['STORE']:
            return STORE
        else:
            return 0

    def wb_sel(self, opcode, funct3):
        """Generates control signal for write-back.

        Args:
            opcode: Opcode of current instruction.

        Returns:
            * 1: JAL instruction
            * 2: LOAD instruction
            * 0: otherwise
        """
        if opcode == isa.OPCODES['JAL']:
            return 1
        elif opcode == isa.OPCODES['LOAD']:
            return 2
        elif self.is_csr(opcode, funct3):
            return 3
        else:
            return 0

    def decImm(self, opcode, inst):
        """Decodes the immediate from the instruction word.

        Args:
            opcode: Opcode of current instruction.
            inst: Current instruction word.

        Returns:
            The decoded immediate.
        """

        # Save sign bit
        sign = getBit(inst, 31)

        sign_ext = 0

        imm = 0
        # Decode + sign-extend immediate
        if opcode in isa.INST_I:
            imm_11_0 = getBits(inst, 31, 20)
            imm = imm_11_0
            if sign:
                sign_ext = 0xfffff << 12

        elif opcode in isa.INST_S:
            imm_11_5 = getBits(inst, 31, 25)
            imm_4_0 = getBits(inst, 11, 7)
            imm = (imm_11_5 << 5) | imm_4_0
            if sign:
                sign_ext = 0xfffff << 12

        elif opcode in isa.INST_B:
            imm_12 = getBit(inst, 31)
            imm_10_5 = getBits(inst, 30, 25)
            imm_4_1 = getBits(inst, 11, 8)
            imm_11 = getBits(inst, 7, 7)
            imm = (
                (imm_12 << 12)
                | (imm_11 << 11)
                | (imm_10_5 << 5)
                | (imm_4_1 << 1))
            if sign:
                sign_ext = 0x7ffff << 13

        elif opcode in isa.INST_U:
            imm_31_12 = getBits(inst, 31, 12)
            imm = imm_31_12 << 12

        elif opcode in isa.INST_J:
            imm_20 = getBit(inst, 31)
            imm_10_1 = getBits(inst, 30, 21)
            imm_11 = getBits(inst, 20, 20)
            imm_19_12 = getBits(inst, 19, 12)
            imm = (
                (imm_20 << 20)
                | (imm_19_12 << 12)
                | (imm_11 << 11)
                | (imm_10_1 << 1))
            if sign:
                sign_ext = 0x7ff << 21

        return (sign_ext | imm)

    def dec_csr(self, inst, opcode, f3, rd_idx, rs1_idx):
        csr_addr = 0
        csr_read_val = 0
        csr_write_en = False
        csr_isImm = False
        csr_uimm = rs1_idx

        if self.is_csr(opcode, f3):
            csr_addr = getBits(inst, 31, 20)
            csr_isImm = self.is_csr_imm(f3)
            # Note that we do a CSR read regardless of which CSR instruction.
            # The spec says for example that, for CSRRW, if rd=x0, no read
            # should happen to the CSR. -> But our CSR implementation has no
            # side effects on a read, so it's safe to always read.
            csr_read_val = self.csr.read(csr_addr)
            csr_write_en = True
            if f3 in [isa.CSR_F3['CSRRW'], isa.CSR_F3['CSRRWI']]:
                if rd_idx == isa.I_REGS['x0']:
                    csr_read_val = 0
            elif f3 in [isa.CSR_F3['CSRRS'], isa.CSR_F3['CSRRC'],
                        isa.CSR_F3['CSRRSI'], isa.CSR_F3['CSRRCI']]:
                if rs1_idx == 0:
                    csr_write_en = False

        # TODO: Check for illegal instruction (e.g. write to RO CSR)

        return csr_addr, csr_read_val, csr_write_en, csr_isImm, csr_uimm

    def check_exception(self):
        pc, inst, opcode, f3, f7 = self.check_exception_inputs
        illinst = False

        if pc > self.pc_bound:
            raise PCOutOfBoundException(pc)

        # Illegal instruction if bits 1:0 of inst != b11
        if (inst & 0x3) != 0x3:
            raise IllegalInstructionException(self.pc, inst)

        if opcode not in isa.OPCODES.values():
            raise IllegalInstructionException(self.pc, inst)

        if opcode == isa.OPCODES['OP-IMM']:
            if f3 == 0b001 and f7 != 0:  # SLLI
                raise IllegalInstructionException(self.pc, inst)
                illinst = True
            elif f3 == 0b101 and not (f7 == 0 or f7 == 0b0100000):  # SRLI,SRAI
                raise IllegalInstructionException(self.pc, inst)
                illinst = True

        if opcode == isa.OPCODES['OP']:
            if not (f7 == 0 or f7 == 0b0100000):
                raise IllegalInstructionException(self.pc, inst)
                illinst = True
            elif f7 == 0b0100000 and not (f3 == 0b000 or f3 == 0b101):
                raise IllegalInstructionException(self.pc, inst)
                illinst = True

        if opcode == isa.OPCODES['JALR']:
            if f3 != 0:
                raise IllegalInstructionException(self.pc, inst)
                illinst = True

        if opcode == isa.OPCODES['BRANCH']:
            if f3 == 2 or f3 == 3:
                raise IllegalInstructionException(self.pc, inst)
                illinst = True

        if opcode == isa.OPCODES['LOAD']:
            if f3 == 3 or f3 == 6 or f3 == 7:
                raise IllegalInstructionException(self.pc, inst)
                illinst = True

        if opcode == isa.OPCODES['STORE']:
            if f3 > 2:
                raise IllegalInstructionException(self.pc, inst)
                illinst = True  # noqa: F841

        # TODO: do something with illinst

        # TODO: Return some exception type
        return False


class EXStage(Module):
    """Execute stage.

    Inputs:
        IDEX_i: Interface from IDStage.

    Outputs:
        EXMEM_o: Interface to MEMStage.
    """
    def __init__(self):
        super().__init__()
        self.IDEX_i = Input(
            IDEX_t, sensitive_methods=[self.process, self.passThrough])

        self.registerStableCallbacks([self.check_exception])

        self.EXMEM_o = Output(EXMEM_t)
        self.exmem_val = EXMEM_t()

    def writeOutput(self):
        self.EXMEM_o.write(EXMEM_t(
            self.exmem_val.rd,
            self.exmem_val.we,
            self.exmem_val.wb_sel,
            self.exmem_val.take_branch,
            self.exmem_val.alu_res,
            self.exmem_val.pc4,
            self.exmem_val.rs2,
            self.exmem_val.mem,
            self.exmem_val.funct3,
            self.exmem_val.csr_addr,
            self.exmem_val.csr_read_val,
            self.exmem_val.csr_write_en,
            self.exmem_val.csr_write_val
        ))

    def passThrough(self):
        val = self.IDEX_i.read()
        self.exmem_val.rd = val.rd
        self.exmem_val.we = val.we
        self.exmem_val.wb_sel = val.wb_sel
        self.exmem_val.rs2 = val.rs2
        self.exmem_val.mem = val.mem
        self.exmem_val.funct3 = val.funct3
        self.exmem_val.csr_addr = val.csr_addr
        self.exmem_val.csr_write_en = val.csr_write_en
        self.exmem_val.csr_read_val = val.csr_read_val

        self.writeOutput()

    def process(self):
        # Read inputs
        val: IDEX_t = self.IDEX_i.read()
        opcode = val.opcode
        rs1 = val.rs1
        rs2 = val.rs2
        imm = val.imm
        pc = val.pc
        f3 = val.funct3
        f7 = val.funct7
        csr_write_en = val.csr_write_en
        csr_read_val = val.csr_read_val

        # Check for branch/jump
        take_branch = False
        if opcode == isa.OPCODES['BRANCH']:
            take_branch = self.branch(f3, rs1, rs2)
        elif opcode == isa.OPCODES['JAL'] or opcode == isa.OPCODES['JALR']:
            take_branch = True

        pc4 = pc + 4

        # ALU
        alu_res = self.alu(opcode, rs1, rs2, imm, pc, f3, f7)

        # Check for exceptions
        self.check_exception_inputs = (take_branch, alu_res, pc)

        # CSR
        csr_write_val = 0
        if csr_write_en:
            csr_write_val = self.csr(f3, csr_read_val, rs1)

        # Outputs
        self.exmem_val.take_branch = take_branch
        self.exmem_val.pc4 = pc4
        self.exmem_val.alu_res = alu_res
        self.exmem_val.csr_write_val = csr_write_val
        self.writeOutput()

    def alu(self, opcode, rs1, rs2, imm, pc, f3, f7):
        """Implements arithmetic-logic unit (ALU)

        Args: TODO
            opcode ([type]): [description]
            rs1 ([type]): [description]
            rs2 ([type]): [description]
            imm ([type]): [description]
            pc ([type]): [description]
            f3 ([type]): [description]
            f7 ([type]): [description]

        Returns:
            ALU result.
        """

        # Helpers
        def _slt(val1, val2):
            """ SLT[I] instruction

            Args:
                val1: Value of register rs1
                val2: rs2 / Sign-extended immediate

            Returns:
                1 if val1 < val2 (signed comparison)
                0 otherwise
            """

            msb_r = getBit(val1, 31)
            msb_i = getBit(val2, 31)

            # Check if both operands are positive
            if (msb_r == 0) and (msb_i == 0):
                if val1 < val2:
                    return 1
                else:
                    return 0
            # val1 negative; val2 positive
            elif (msb_r == 1) and (msb_i == 0):
                return 1
            # val1 positive, val2 negative
            elif (msb_r == 0) and (msb_i == 1):
                return 0
            # both negative
            else:
                if val2 < val1:
                    return 1
                else:
                    return 0

        def _sltu(val1, val2):
            """ SLT[I]U instruction

            Args:
                val1: Value of register rs1
                val2: rs2 / Sign-extended immediate

            Returns:
                1 if val1 < val2 (unsigned comparison)
                0 otherwise
            """

            if val1 < val2:
                return 1
            else:
                return 0

        def _sll(val1, val2):
            """ SLL[I] instruction

            Args:
                val1: Value of register rs1
                val2: rs2 / Immediate

            Returns:
                Logical left shift of val1 by val2 (5 bits)
            """

            # Mask so that bits above bit 31 turn to zero (for Python)
            return (MASK_32 & (val1 << (0x1f & val2)))

        def _srl(val1, val2):
            """ SRL[I] instruction

            Args:
                val1: Value of register rs1
                val2: rs2 / Immediate

            Returns:
                Logical right shift of val1 by val2 (5 bits)
            """

            # Mask so that bits above bit 31 turn to zero (for Python)
            return (MASK_32 & (val1 >> (0x1f & val2)))

        def _sra(val1, val2):
            """ SRA[I] instruction

            Args:
                val1: Value of register rs1
                val2: rs2 / Immediate

            Returns:
                Arithmetic right shift of val1 by val2 (5 bits)
            """

            msb_r = getBit(val1, 31)
            shamt = 0x1f & val2
            # Mask so that bits above bit 31 turn to zero (for Python)
            rshift = (MASK_32 & (val1 >> shamt))
            if msb_r == 0:
                return rshift
            else:
                # Fill upper bits with 1s
                return (MASK_32 & (rshift | (0xffffffff << (XLEN - shamt))))

        # ------------------
        # ALU start
        # ------------------

        # Select operands
        op1 = op2 = 0
        # op1
        if (opcode == isa.OPCODES['AUIPC']
                or opcode == isa.OPCODES['JAL']
                or opcode == isa.OPCODES['BRANCH']):
            op1 = pc
        else:
            op1 = rs1
        # op2
        if opcode != isa.OPCODES['OP']:
            op2 = imm
        else:
            op2 = rs2

        # Perform ALU op
        alu_res = 0
        if opcode == isa.OPCODES['LUI']:
            alu_res = op2

        elif (opcode == isa.OPCODES['AUIPC']
              or opcode == isa.OPCODES['JAL']
              or opcode == isa.OPCODES['BRANCH']
              or opcode == isa.OPCODES['LOAD']
              or opcode == isa.OPCODES['STORE']):
            alu_res = op1 + op2

        elif opcode == isa.OPCODES['JALR']:
            alu_res = 0xfffffffe & (op1 + op2)

        elif opcode == isa.OPCODES['OP-IMM']:
            if f3 == 0b000:  # ADDI
                alu_res = op1 + op2
            elif f3 == 0b010:  # SLTI
                alu_res = _slt(op1, op2)
            elif f3 == 0b011:  # SLTIU
                alu_res = _sltu(op1, op2)
            elif f3 == 0b100:  # XORI
                alu_res = op1 ^ op2
            elif f3 == 0b110:  # ORI
                alu_res = op1 | op2
            elif f3 == 0b111:  # ANDI
                alu_res = op1 & op2
            elif f3 == 0b001:  # SLLI
                # TODO: We could remove this check if IDStage catches
                # f7!=0 case
                if f7 == 0:
                    alu_res = _sll(op1, op2)
            elif f3 == 0b101:
                if f7 == 0:  # SRLI
                    alu_res = _srl(op1, op2)
                elif f7 == 0b0100000:  # SRAI
                    alu_res = _sra(op1, op2)

        elif opcode == isa.OPCODES['OP']:
            if f7 == 0:
                if f3 == 0b000:  # ADD
                    alu_res = op1 + op2
                elif f3 == 0b001:  # SLL
                    alu_res = _sll(op1, op2)
                elif f3 == 0b010:  # SLT
                    alu_res = _slt(op1, op2)
                elif f3 == 0b011:  # SLTU
                    alu_res = _sltu(op1, op2)
                elif f3 == 0b100:  # XOR
                    alu_res = op1 ^ op2
                elif f3 == 0b101:  # SRL
                    alu_res = _srl(op1, op2)
                elif f3 == 0b110:  # OR
                    alu_res = op1 | op2
                elif f3 == 0b111:  # AND
                    alu_res = op1 & op2

            elif f7 == 0b0100000:
                if f3 == 0b000:  # SUB
                    alu_res = op1 - op2
                elif f3 == 0b101:  # SRA
                    alu_res = _sra(op1, op2)

        return MASK_32 & alu_res

    def branch(self, f3, rs1, rs2) -> bool:
        """Performs comparison of rs1 and rs2 using comp op given by f3.

        Returns:
            True if branch is taken.
        """

        # Branch less-than (BLT) logic
        def _blt(rs1, rs2):
            if msb_32(rs1) == msb_32(rs2):
                return rs1 < rs2
            elif msb_32(rs1) == 1:
                return True
            else:
                return False

        if f3 == 0:               # BEQ
            return rs1 == rs2
        elif f3 == 1:             # BNE
            return rs1 != rs2
        elif f3 == 4:             # BLT
            return _blt(rs1, rs2)
        elif f3 == 5:             # BGE
            return not _blt(rs1, rs2)
        elif f3 == 6:             # BLTU
            return rs1 < rs2
        elif f3 == 7:             # BGEU
            return rs1 >= rs2

    def check_exception(self):
        take_branch, alu_res, pc = self.check_exception_inputs
        # --- Branch/jump target misaligned ------
        if take_branch:
            if alu_res & 0x3 != 0:
                # raise Exception(f"Target instruction address misaligned exception at PC = 0x{pc:08X}")  # noqa: E501
                raise InstructionAddressMisalignedException(pc)

    def csr(self, f3, csr_read_val, rs1):
        ret_val = 0
        if f3 in [isa.CSR_F3['CSRRW'], isa.CSR_F3['CSRRWI']]:
            ret_val = rs1
        elif f3 in [isa.CSR_F3['CSRRS'], isa.CSR_F3['CSRRSI']]:
            ret_val = rs1 | csr_read_val
        elif f3 in [isa.CSR_F3['CSRRC'], isa.CSR_F3['CSRRCI']]:
            ret_val = ~rs1 & csr_read_val
        return ret_val


class MEMStage(Module):
    """Memory stage.

    Inputs:
        EXMEM_i: Interface from EXStage.
        XT_i: Interface from IF (entropy extraction signals)

    Outputs:
        MEMWB_o: Interface to WBStage.
        TXT_o: Output to IF/extractor (flush ready signal)
    """
    def __init__(self, dmem_read: ReadPort, dmem_write: WritePort):
        super().__init__()
        self.EXMEM_i = Input(EXMEM_t)
        self.XT_i = Input(XTIF_t)
        self.MEMWB_o = Output(MEMWB_t)
        self.load_val = Wire(int, [self.process_load])
        self.TXT_o = Output(TXT_t)

        self.registerStableCallbacks([self.check_exception])

        self.flush_ready = Reg(bool, False)
        self.flush_ready_w = Wire(bool)
        self.flush_ready.next << self.flush_ready_w
        self.flush_state = Reg(int, 0, sensitive_methods=[self.process])
        # self.flush_state_w = Wire(int)
        # self.flush_state.next << self.flush_state_w

        self.entropy_offset = Reg(int, 0)

        # Main memory
        self.read_port = dmem_read
        self.write_port = dmem_write
        self.load_val << self.read_port.rdata_o
        self.w = 1  # data width
        self.signext_w = 0  # signext width

        self.out_val = MEMWB_t()

    def write_output(self):
        self.MEMWB_o.write(MEMWB_t(
            rd=self.out_val.rd,
            we=self.out_val.we,
            alu_res=self.out_val.alu_res,
            pc4=self.out_val.pc4,
            mem_rdata=self.out_val.mem_rdata,
            wb_sel=self.out_val.wb_sel,
            csr_addr=self.out_val.csr_addr,
            csr_read_val=self.out_val.csr_read_val,
            csr_write_en=self.out_val.csr_write_en,
            csr_write_val=self.out_val.csr_write_val
        ))
        self.TXT_o.write(TXT_t(self.flush_ready.cur.read()))

    def process_load(self):
        load_val = self.load_val.read()
        if self.signext_w != 0:
            load_val = signext(load_val, self.signext_w)

        self.out_val.mem_rdata = load_val
        self.write_output()

    def process(self):
        # Read inputs
        in_val = self.EXMEM_i.read()
        xt = self.XT_i.read()         # entropy extractor/fetch input
        if xt.flush_bits:
            op = STORE
            f3 = 2
            addr = ENTROPY_ADDRESS
            mem_wdata = 0
            if len(xt.entropy) < 16:
                for _ in range(len(xt.entropy)+1, 17):
                    xt.entropy.append(0)
        else:
            addr = in_val.alu_res
            mem_wdata = in_val.rs2
            op = in_val.mem
            f3 = in_val.funct3

        self.check_exception_inputs = (op, addr, f3)

        # Set inputs for memory module
        we = False
        re = False
        state = self.flush_state.cur.read()
        if xt.flush_bits and not self.flush_ready.cur.read():
            entropy_offset = self.entropy_offset.cur.read()
            entropy_addr = ENTROPY_ADDRESS + entropy_offset
            entropy_write_value = self.set_entropy_write_value(state, xt)
            self.entropy_offset.next.write(entropy_offset + 4)
            self.read_port.addr_i.write(entropy_addr)
            self.write_port.wdata_i.write(entropy_write_value)
        else:
            self.read_port.addr_i.write(addr)
            self.write_port.wdata_i.write(mem_wdata)
        self.signext_w = 0

        if state == 2:
            self.flush_ready_w.write(True)
            # self.flush_state.next.write(0)
        
        if self.flush_ready.cur.read() and state != 2:
            self.flush_ready_w.write(False)

        if op == LOAD:                                          # Read memory
            re = True
            if f3 == 0:  # LB
                self.w = 1
                self.signext_w = 8
            elif f3 == 1:  # LH
                self.w = 2
                self.signext_w = 16
            elif f3 == 2:  # LW
                self.w = 4
            elif f3 == 4:  # LBU
                self.w = 1
            elif f3 == 5:  # LHU
                self.w = 2
            else:
                raise Exception(f'ERROR (MEMStage, process): Illegal f3 {f3}')

        elif op == STORE:                                       # Store memory
            we = True
            if f3 == 0:  # SB
                self.w = 1
            elif f3 == 1:  # SH
                self.w = 2
            elif f3 == 2:  # SW
                self.w = 4
            else:
                raise Exception(f'ERROR (MEMStage, process): Illegal f3 {f3}')
        # else:
        #     raise Exception('ERROR (MEMStage, process): Invalid op {}'.format(op)) # noqa: E501

        # TODO: Illegal address execption handling

        self.read_port.width_i.write(self.w)
        self.read_port.re_i.write(re)
        self.write_port.we_i.write(we)

        # Outputs
        self.out_val.rd = in_val.rd
        self.out_val.we = in_val.we
        self.out_val.alu_res = in_val.alu_res
        self.out_val.pc4 = in_val.pc4
        self.out_val.wb_sel = in_val.wb_sel
        self.out_val.csr_addr = in_val.csr_addr
        self.out_val.csr_read_val = in_val.csr_read_val
        self.out_val.csr_write_en = in_val.csr_write_en
        self.out_val.csr_write_val = in_val.csr_write_val
        self.write_output()
    
    def set_entropy_write_value(self, state, xt):
        if state == 0:
            w1 = str(bin(xt.entropy[0]))[2:]
            w2 = str(bin(xt.entropy[1]))[2:]
            w3 = str(bin(xt.entropy[2]))[2:]
            w4 = str(bin(xt.entropy[3]))[2:]
            w5 = str(bin(xt.entropy[4]))[2:]
            w6 = str(bin(getBits(xt.entropy[5], 5, 4)))[2:]
            self.flush_state.next.write(state + 1)
        if state == 1:
            w1 = str(bin(getBits(xt.entropy[5], 3, 0)))[2:]
            w2 = str(bin(xt.entropy[6]))[2:]
            w3 = str(bin(xt.entropy[7]))[2:]
            w4 = str(bin(xt.entropy[8]))[2:]
            w5 = str(bin(xt.entropy[9]))[2:]
            w6 = str(bin(getBits(xt.entropy[10], 5, 2)))[2:]
            self.flush_state.next.write(state + 1)
        if state == 2:
            w1 = str(bin(getBits(xt.entropy[10], 1, 0)))[2:]
            w2 = str(bin(xt.entropy[11]))[2:]
            w3 = str(bin(xt.entropy[12]))[2:]
            w4 = str(bin(xt.entropy[13]))[2:]
            w5 = str(bin(xt.entropy[14]))[2:]
            w6 = str(bin(xt.entropy[15]))[2:]
            self.flush_state.next.write(0)
        return int((w1 + w2 + w3 + w4 + w5 + w6), 2)


    def check_exception(self):
        op, addr, f3 = self.check_exception_inputs

        if f3 == 0:
            return

        op_str = "load from" if op == LOAD else "store to"

        if f3 == 1:  # Half word
            if addr & 0x1 != 0:
                logger.warning(f"Misaligned {op_str} address 0x{addr:08X}.")
        elif f3 == 2:  # Word
            if addr & 0x11 != 0:
                logger.warning(f"Misaligned {op_str} address 0x{addr:08X}.")


class WBStage(Module):
    """Write-back stage.

    Inputs:
        MEMWB_i: Interface from MEMStage.
    """
    def __init__(self, regf: Regfile):
        super().__init__()
        self.regfile = regf

        self.MEMWB_i = Input(MEMWB_t)
        self.csr_write_addr_o = Output(int)
        self.csr_write_en_o = Output(bool)
        self.csr_write_val_o = Output(int)

    def process(self):
        # Read inputs
        in_val = self.MEMWB_i.read()
        rd = in_val.rd
        we = in_val.we
        alu_res = in_val.alu_res
        pc4 = in_val.pc4
        mem_rdata = in_val.mem_rdata
        wb_sel = in_val.wb_sel
        csr_write_en = in_val.csr_write_en
        csr_read_val = in_val.csr_read_val
        csr_addr = in_val.csr_addr
        csr_write_val = in_val.csr_write_val

        wb_val = 0
        # Default to no write.
        # If write, then `writeRequest()` below will
        # enable write in regfile.
        self.regfile.we = False

        if we:
            if wb_sel == 0:  # ALU op
                wb_val = alu_res
            elif wb_sel == 1:  # PC+4 (JAL)
                wb_val = pc4
            elif wb_sel == 2:  # Load
                wb_val = mem_rdata
            elif wb_sel == 3:  # CSR
                wb_val = csr_read_val
            else:
                raise Exception(
                    f'ERROR (WBStage, process): Invalid wb_sel {wb_sel}')

            self.regfile.writeRequest(rd, wb_val)

        self.csr_write_addr_o.write(csr_addr)
        self.csr_write_val_o.write(csr_write_val)
        self.csr_write_en_o.write(csr_write_en)


class BranchUnit(Module):
    """Branch unit.

    Inputs:
        pc_i: Program counter (PC)
        take_branch_i: Whether to take the branch or not
        target_i: Branch target address

    Outputs:
        npc_o: Next PC
    """
    def __init__(self):
        super().__init__()
        self.pc_i = Input(int)
        self.take_branch_i = Input(bool)
        self.target_i = Input(int)
        self.npc_o = Output(int)

    def process(self):
        # Read inputs
        pc = self.pc_i.read()
        take_branch = self.take_branch_i.read()
        target = self.target_i.read()

        # Compute NPC
        npc = pc + 4
        if take_branch:
            npc = target

        # Outputs
        self.npc_o.write(npc)
