from unittest.mock import MagicMock, patch
import pytest
from tabulate import tabulate
from pyv.csr import CSRUnit
from pyv.simulator import Simulator
from pyv.extractor import Extractor, XTIF_t, TXT_t
from pyv.stages_entropy import IFStage, IDStage, EXStage, MEMStage, WBStage, BranchUnit, IFID_t, IDEX_t, EXMEM_t, MEMWB_t
from pyv.reg import Regfile
from pyv.util import MASK_32
from pyv.mem import Memory
from pyv.port import Wire


def test_sanity():
    assert True


# ---------------------------------------
# Test data types
# ---------------------------------------
def test_data_types():
    def check_attrs(type_obj, attr_list):
        for attr in attr_list:
            assert hasattr(type_obj, attr)

    foo = IFID_t()
    attr_list = ['inst', 'pc']
    check_attrs(foo, attr_list)

    foo = IDEX_t()
    attr_list = ['rs1', 'rs2', 'imm', 'pc', 'rd', 'we', 'wb_sel', 'opcode', 'funct3', 'funct7', 'mem']
    check_attrs(foo, attr_list)

    foo = EXMEM_t()
    attr_list = ['rd', 'we', 'wb_sel', 'take_branch', 'alu_res', 'pc4', 'rs2', 'mem', 'funct3']
    check_attrs(foo, attr_list)

    foo = MEMWB_t()
    attr_list = ['rd', 'we', 'alu_res', 'pc4', 'mem_rdata', 'wb_sel']
    check_attrs(foo, attr_list)


# ---------------------------------------
# Test FETCH
# ---------------------------------------
class TestIFStage:
    @pytest.fixture(scope='function')
    def imem(self):
        imem = Memory(1024)
        imem._init()
        return imem

    @pytest.fixture(scope='function')
    def extractor(self):
        extractor = Extractor()
        extractor._init()
        return extractor
    
    @pytest.fixture(scope='function')
    def fetch(self, imem):
        fetch = IFStage(imem.read_port1)
        fetch._init()
        return fetch

    @pytest.mark.extraction
    @pytest.mark.skip(reason="No longer a valid regression test after activating pipeline blocking")
    def test_IFStage(self, sim, imem, fetch):
        # SW a0,-20(s0) = SW, x10, -20(x8)
        # 0xfea42623
        imem.mem[0:4] = [0x23, 0x26, 0xa4, 0xfe]

        fetch.npc_i.write(0x00000000)
        sim.step()

        out = fetch.IFID_o.read()
        assert out.inst == 0xfea42623
        assert out.pc == 0x00000000
    
    @pytest.mark.extraction
    @pytest.mark.regression
    def test_IFStage_regression(self, sim, imem, fetch):
        # SW a0,-20(s0) = SW, x10, -20(x8)
        # 0xfea42623
        imem.mem[0:4] = [0x23, 0x26, 0xa4, 0xfe]

        fetch.npc_i.write(0x00000000)
        fetch.XTIF_i.write(XTIF_t(entropy=[], active=False, ready=True, flush_bits=False))
        sim.step()
        fetch.XTIF_i.write(XTIF_t(entropy=[], active=False, ready=False, flush_bits=False))
        sim.step()        

        out = fetch.IFID_o.read()
        assert out.inst == 0xfea42623
        assert out.pc == 0x00000000
  
    @pytest.mark.extraction
    def test_IF_XT_integr(self, sim, extractor, fetch, imem):
        extractor.IFXT_i << fetch.IFXT_o
        fetch.XTIF_i << extractor.XTIF_o

        imem.mem[0:4] = [0x33, 0x26, 0xa4, 0xfa]
        fetch.npc_i.write(0x00000000)
        sim.step()

        # verify that extractor receives instruction and returns correct entropy
        if_out = fetch.IFXT_o.read()
        assert if_out.inst == 0xfaa42633       # correct instruction out of fetch
        ext_in = extractor.IFXT_i.read()
        assert ext_in.inst == 0xfaa42633       # correct instruction enters extractor
        ext_out = extractor.XTIF_o.read().entropy
        assert ext_out == [61]                 # correct entropy out of extractor
        if_in = fetch.XTIF_i.read().entropy
        assert if_in == [61]                   # correct entropy enters fetch

        sim.step()

        out_xt = fetch.XT_o.read()
        assert out_xt.entropy ==  [61]
        assert not out_xt.ready
        assert out_xt.active
        assert not out_xt.flush_bits
    
    @pytest.mark.extraction
    def test_IF_XT_signals(self, sim, extractor, fetch, imem):
        extractor.IFXT_i << fetch.IFXT_o
        fetch.XTIF_i << extractor.XTIF_o

        imem.mem[0:4] = [0xff, 0xff, 0xff, 0xff]
        fetch.npc_i.write(0x00000000)
        sim.step()

        out_xt = fetch.XT_o.read()
        assert out_xt.ready
        assert not out_xt.active
    
    @pytest.mark.extraction
    def test_IF_XT_flow(self, sim, extractor, fetch, imem):
        extractor.IFXT_i << fetch.IFXT_o
        fetch.XTIF_i << extractor.XTIF_o

        # initialize instruction memory
        for i in range(0, 64, 8):
            imem.mem[i:i+4] = [0x33, 0x26, 0xa4, 0xfa]
            imem.mem[i+4:i+8] = [0x33, 0x26, 0xa4, 0xf8]
        pc = 0x00000000

        headers = ["Instruction", "Entropy HEX", "Entropy BIN"]
        instruction = 0
        results = []
        for _ in range(0, 16):
            fetch.npc_i.write(pc)     # send PC to fetch
            sim.step()                # run a cycle
            fetch_out = fetch.IFID_o.read()
            inst_nxt = fetch_out.inst          # need to remember this
            fetch_eb = fetch.XT_o.read().entropy
            if fetch_eb:
                entropy = fetch_eb[-1]
            pc += 4
            if instruction != 0:
                results.append([instruction, hex(entropy), bin(entropy)])
            instruction = inst_nxt
        
        sim.step()                    # one more for good measure (entropy propagates)
        out_xt = fetch.XT_o.read()
        entropy = out_xt.entropy[-1]
        results.append([instruction, hex(entropy), bin(entropy)])

        with open("test.log", "w") as f:
            f.write("=== Integration Test: Entropy Extractor in Fetch ===\n\n")
            f.write(tabulate(results, headers=headers))
        
        assert len(out_xt.entropy) == 16
        assert out_xt.entropy == [61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60]
        assert out_xt.flush_bits
    
    @pytest.mark.extraction
    @pytest.mark.debug
    def test_XT_pipeline_blocking(self, sim, extractor, fetch, imem):
        extractor.IFXT_i << fetch.IFXT_o
        fetch.XTIF_i << extractor.XTIF_o

        # initialize instruction memory
        imem.mem[0:4] = [0x33, 0x26, 0xa4, 0xfa]
        imem.mem[4:8] = [0x33, 0x26, 0xa4, 0xfe]
        imem.mem[8:12] = [0xff, 0xff, 0xff, 0xff]
        pc = 0x00000000

        fetch.npc_i.write(pc)                    # send PC to fetch
        sim.step()                               # run a cycle
        if_out = fetch.IFXT_o.read()
        assert if_out.inst == 0xfaa42633         # verify correct instruction out of fetch
        ifid_out = fetch.IFID_o.read()
        assert ifid_out.inst == 0x00000013       # correct instruction to next stages

        pc += 16        # dummy PC value to fuzz in the next steps
        
        fetch.npc_i.write(pc)                    # send PC to fetch
        sim.step()                               # run a cycle to out_pc == 4
        if_out = fetch.IFXT_o.read()
        assert if_out.inst == 0xfea42633         # verify correct instruction out of fetch
        ifid_out = fetch.IFID_o.read()
        assert ifid_out.inst == 0x00000013       # correct instruction to next stages
        assert ifid_out.pc == 4                  # verify correct PC

        fetch.npc_i.write(pc)                    # send PC to fetch
        sim.step()                               # run to out_pc == 8
        if_out = fetch.IFXT_o.read()
        assert if_out.inst == 0xffffffff         # verify STOP instruction out of fetch
        ifid_out = fetch.IFID_o.read()
        assert ifid_out.inst == 0x00000013       # correct instruction to next stages
        assert ifid_out.pc == 8                  # verify correct PC
        out_xt = fetch.XT_o.read()
        assert out_xt.ready                      # verify ready set by extractor
        assert not out_xt.active                 # verify active lowered by extractor

        fetch.npc_i.write(pc)                    # send PC to fetch
        sim.step()                               # run to out_pc == 12
        if_out = fetch.IFXT_o.read()
        assert if_out.inst == 0x000000000        # verify STOP instruction out of fetch
        ifid_out = fetch.IFID_o.read()
        assert ifid_out.pc == 12                 # verify PC is not taken from input
        assert ifid_out.inst == 0x00000013       # verify correct instruction to next stages

        fetch.npc_i.write(pc)                    # send PC to fetch
        extractor.TXT_i.write(TXT_t(flush_bits_ready=True))       # set flush ready signal artificially
        sim.step()
        ifid_out = fetch.IFID_o.read()
        assert ifid_out.pc == 0                  # verify PC reset
        assert ifid_out.inst == 0xfaa42633       # verify correct instruction out of fetch


# ---------------------------------------
# Test DECODE
# ---------------------------------------

@pytest.fixture
def decode():
    regf = Regfile()
    csr = CSRUnit()
    decode = IDStage(regf, csr)
    decode._init()
    return decode


@pytest.fixture
def csr():
    csr = CSRUnit()
    csr._init()
    return csr


class TestIDStage:
    def test_constructor(self):
        regf = Regfile()
        csr = CSRUnit()
        decode = IDStage(regf, csr)

        assert regf == decode.regfile
        assert csr == decode.csr
        assert decode.IFID_i._type == IFID_t
        assert decode.IDEX_o._type == IDEX_t

    def test_decImm(self, decode: IDStage):
        # --- Test I-type -------------------------
        # 001100110000 10000 000 00001 0010011
        inst = 0b00110011000010000000000010010011
        imm = decode.decImm(0b00100, inst)
        assert imm == 0b001100110000

        # Test sign-ext
        # 101100110000 10000 000 00001 0010011
        inst = 0b10110011000010000000000010010011
        imm = decode.decImm(0b00100, inst)
        assert imm == 0xFFFFFB30

        # --- Test S-type -------------------------
        # 0111010 00000 00000 010 11100 0100011
        inst = 0b01110100000000000010111000100011
        imm = decode.decImm(0b01000, inst)
        assert imm == 0b011101011100

        # Test sign-ext
        # 1111010 00000 00000 010 11100 0100011
        inst = 0b11110100000000000010111000100011
        imm = decode.decImm(0b01000, inst)
        assert imm == 0xFFFFFF5C

        # --- Test B-type -------------------------
        # 0 100110 00000 00000 000 0110 1 1100011
        inst = 0b01001100000000000000011011100011
        imm = decode.decImm(0b11000, inst)
        assert imm == 0b0110011001100

        # Test sign-ext
        # 1 100110 00000 00000 000 0110 1 1100011
        inst = 0b11001100000000000000011011100011
        imm = decode.decImm(0b11000, inst)
        assert imm == 0xFFFFFCCC

        # --- Test U-type -------------------------
        # 00001011001111000101 00000 0110111
        inst = 0b00001011001111000101000000110111
        imm = decode.decImm(0b01101, inst)
        assert imm == 0x0B3C5000

        # Test sign-ext
        # 10001011001111000101 00000 0110111
        inst = 0b10001011001111000101000000110111
        imm = decode.decImm(0b01101, inst)
        assert imm == 0x8B3C5000

        # --- Test J-type -------------------------
        # 0 1111010110 0 00011010 00000 1101111
        inst = 0b01111010110000011010000001101111
        imm = decode.decImm(0b11011, inst)
        assert imm == 0x1A7AC

        # Test sign-ext
        # 1 1111010110 0 00011010 00000 1101111
        inst = 0b11111010110000011010000001101111
        imm = decode.decImm(0b11011, inst)
        assert imm == 0xFFF1A7AC

    def test_exception(self, caplog, sim: Simulator, decode: IDStage):
        # --- Illegal Instruction -----------------
        pc = 0

        # No exception for valid instruction
        inst = 0x23  # store
        decode.IFID_i.write(IFID_t(inst, pc))
        sim.step()

        # --- Inst[1:0] != 2'b11
        inst = 0x10
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()

        # --- Unsupported RV32base Opcodes
        inst = 0x1F  # opcode = 0011111
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()

        # --- Illegal combinations of funct3, funct7

        # ADDI - SRAI -> opcode = 0010011
        # If funct3 == 1 => funct7 == 0
        inst = 0x02001013  # funct7 = 1
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()
        # If funct3 == 5 => funct7 == {0, 0100000}
        inst = 0xc0005013  # funct7 = 1100000
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()

        # ADD - AND -> opcode = 0110011
        # If funct7 != {0, 0100000} -> illegal
        inst = 0x80000033  # funct7 = 1000000
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()
        # If funct7 == 0100000 => funct3 == {0, 5}
        inst = 0x40002033  # funct3 = 2
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()

        # JALR -> opcode = 1100111 => funct3 == 0
        inst = 0x00005067  # funct3 = 5
        pc += 1
        decode.IFID_i.write(IFID_t(inst, pc))
        with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
            sim.step()

        # BEQ - BGEU -> opcode = 1100011 => funct3 = {0,1,4,5,6,7}
        funct3 = [2, 3]
        for f3 in funct3:
            pc += 1
            inst = 0x63 | (f3 << 12)
            decode.IFID_i.write(IFID_t(inst, pc))
            with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
                sim.step()

        # LB - LHU -> opcode = 0000011 => funct3 = {0,1,2,4,5}
        funct3 = [3, 6, 7]
        for f3 in funct3:
            pc += 1
            inst = 0x3 | (f3 << 12)
            decode.IFID_i.write(IFID_t(inst, pc))
            with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
                sim.step()

        # SB, SH, SW -> opcode = 0100011 => funct3 = {0,1,2}
        funct3 = [3, 4, 5, 6, 7]
        for f3 in funct3:
            pc += 1
            inst = 0x23 | (f3 << 12)
            decode.IFID_i.write(IFID_t(inst, pc))
            with pytest.raises(Exception, match=f"Illegal instruction @ PC = 0x{pc:08X} detected: '0x{inst:08x}'"):
                sim.step()

    def test_wbSel(self, decode: IDStage):
        res = decode.wb_sel(0b11011, 0)
        assert res == 1
        res = decode.wb_sel(0, 0)
        assert res == 2
        res = decode.wb_sel(0b01100, 0)
        assert res == 0
        res = decode.wb_sel(0b11100, 1)
        assert res == 3

    def test_IDStage(self, sim: Simulator, decode: IDStage):
        def validate(out: IDEX_t, rs1, rs2, imm, pc, rd, we, wb_sel, opcode, funct3, funct7, mem):
            if rs1 is not None:
                assert out.rs1 == rs1
            if rs2 is not None:
                assert out.rs2 == rs2
            if imm is not None:
                assert out.imm == imm
            assert out.pc == pc
            if rd is not None:
                assert out.rd == rd
            assert out.we == we
            assert out.wb_sel == wb_sel
            assert out.opcode == opcode
            if funct3 is not None:
                assert out.funct3 == funct3
            if funct7 is not None:
                assert out.funct7 == funct7
            assert out.mem == mem

        # ---- SW a0,-20(s0) = SW, x10, -20(x8) (x8=rs1, x10=rs2)

        # Write some values into the relevant registers
        decode.regfile.regs[8] = 0x80000000
        decode.regfile.regs[10] = 42

        # Set input
        decode.IFID_i.write(IFID_t(0xfea42623, 0x80000004))
        sim.step()

        # Validate outputs
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=0x80000000,
            rs2=42,
            imm=0xffffffec,
            pc=0x80000004,
            rd=0x0C,
            we=False,
            wb_sel=0,
            opcode=0b01000,
            funct3=2,
            funct7=None,
            mem=2
        )

        # ---- Test OP-IMM -----------------------------------
        # addi x7, x3, 89
        decode.regfile.regs[3] = 120
        decode.regfile.we = False
        decode.IFID_i.write(IFID_t(0x05918393, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=120,
            rs2=None,
            imm=89,
            pc=0x80000004,
            rd=7,
            we=True,
            wb_sel=0,
            opcode=0b00100,
            funct3=0,
            funct7=None,
            mem=0
        )

        # ---- Test SHAMT -----------------------------------
        # srli x8, x1, 8
        decode.regfile.regs[1] = 120
        decode.regfile.we = False
        decode.IFID_i.write(IFID_t(0x0080d413, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=120,
            rs2=None,
            imm=8,
            pc=0x80000004,
            rd=8,
            we=True,
            wb_sel=0,
            opcode=0b00100,
            funct3=0b101,
            funct7=0,
            mem=0
        )

        # ---- Test OP -----------------------------------
        # SUB x14, x7, x5
        decode.regfile.writeRequest(7, 43)
        sim.step()
        decode.regfile.writeRequest(5, 12)
        sim.step()

        decode.IFID_i.write(IFID_t(0x40538733, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=43,
            rs2=12,
            imm=None,
            pc=0x80000004,
            rd=14,
            we=True,
            wb_sel=0,
            opcode=0b01100,
            funct3=0,
            funct7=0b0100000,
            mem=0
        )

        # ---- Test LOAD -----------------------------------
        # LW x15, x8, 0x456
        decode.regfile.writeRequest(8, 0x40000000)
        sim.step()
        decode.IFID_i.write(IFID_t(0x45642783, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=0x40000000,
            rs2=None,
            imm=0x456,
            pc=0x80000004,
            rd=15,
            we=True,
            wb_sel=2,
            opcode=0b00000,
            funct3=0b010,
            funct7=None,
            mem=1
        )

        # ---- Test JALR -----------------------------------
        # jalr x13, 1025(x28)
        decode.regfile.writeRequest(28, 0x40000000)
        sim.step()
        decode.IFID_i.write(IFID_t(0x401e06e7, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=0x40000000,
            rs2=None,
            imm=1025,
            pc=0x80000004,
            rd=13,
            we=True,
            wb_sel=0,
            opcode=0b11001,
            funct3=0b000,
            funct7=None,
            mem=0
        )

        # ---- Test BRANCH -----------------------------------
        # bne x4, x8, 564
        decode.regfile.regs[4] = 42
        decode.regfile.regs[8] = 12
        decode.regfile.we = False
        decode.IFID_i.write(IFID_t(0x22821a63, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=42,
            rs2=12,
            imm=564,
            pc=0x80000004,
            rd=None,
            we=False,
            wb_sel=0,
            opcode=0b11000,
            funct3=0b001,
            funct7=None,
            mem=0
        )

        # ---- Test AUIPC -----------------------------------
        # auipc x6, 546
        decode.IFID_i.write(IFID_t(0x00222317, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=None,
            rs2=None,
            imm=546 << 12,
            pc=0x80000004,
            rd=6,
            we=True,
            wb_sel=0,
            opcode=0b00101,
            funct3=None,
            funct7=None,
            mem=0
        )

        # ---- Test LUI -----------------------------------
        # lui x12, 123
        decode.IFID_i.write(IFID_t(0x0007b637, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=None,
            rs2=None,
            imm=123 << 12,
            pc=0x80000004,
            rd=12,
            we=True,
            wb_sel=0,
            opcode=0b01101,
            funct3=None,
            funct7=None,
            mem=0
        )

        # ---- Test JAL -----------------------------------
        # jal x9, 122
        decode.IFID_i.write(IFID_t(0x07a004ef, 0x80000004))
        sim.step()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            rs1=None,
            rs2=None,
            imm=122,
            pc=0x80000004,
            rd=9,
            we=True,
            wb_sel=1,
            opcode=0b11011,
            funct3=None,
            funct7=None,
            mem=0
        )

        # TODO: Test FENCE

        # TODO: Test ECALL / EBREAK

    def test_csr(self, sim: Simulator, decode: IDStage):
        def validate(out: IDEX_t, csr_addr=None, csr_read_val=None, csr_write_en=None, rs1=None, rd=None, wb_sel=None, f3=None, we=None):
            if csr_addr is not None:
                assert out.csr_addr == csr_addr
            if csr_read_val is not None:
                assert out.csr_read_val == csr_read_val
            if rs1 is not None:
                assert out.rs1 == rs1
            if rd is not None:
                assert out.rd == rd
            if wb_sel is not None:
                assert out.wb_sel == wb_sel
            if csr_write_en is not None:
                assert out.csr_write_en == csr_write_en
            if f3 is not None:
                assert out.funct3 == f3
            if we is not None:
                assert out.we == we

        # Not a CSR inst
        decode.IFID_i.write(IFID_t(0x07a004ef, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0,
            csr_read_val=0,
            csr_write_en=False
        )

        # csrrw x5, misa, x12
        decode.regfile.regs[12] = 0x89
        decode.csr.csr_bank.csrs[0x301]._csr_reg.cur.write(0x42)
        decode.IFID_i.write(IFID_t(0x301612f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=True,
            rs1=0x89,
            rd=5,
            wb_sel=3,
            f3=1,
            we=1
        )

        # csrrw: rd=x0 -> no read from CSR
        # csrrw x0, misa, x12
        decode.IFID_i.write(IFID_t(0x30161073, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0,
            csr_write_en=True,
            rd=0,
            wb_sel=3,
            f3=1,
            we=1
        )

        # csrrs/csrrc: rs1=x0 -> no write to CSR
        # csrrs x5, misa, x0
        decode.IFID_i.write(IFID_t(0x301022f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=False,
            rd=5,
            wb_sel=3,
            f3=2,
            we=1
        )

        # csrrc x5, misa, x0
        decode.IFID_i.write(IFID_t(0x301032f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=False,
            rd=5,
            wb_sel=3,
            f3=3,
            we=1
        )

        # csrrs/csrrc: rd=0 -> read has to happen regardless
        # csrrs x0, misa, x12
        with patch.object(decode.csr, 'read', MagicMock()) as read_mock:
            decode.IFID_i.write(IFID_t(0x30162073, 0x80000004))
            sim.run_comb_logic()
            read_mock.assert_called_with(0x301)

        # csrrc x0, misa, x12
        with patch.object(decode.csr, 'read', MagicMock()) as read_mock:
            decode.IFID_i.write(IFID_t(0x30163073, 0x80000004))
            sim.run_comb_logic()
            read_mock.assert_called_with(0x301)

        # CSR-imm instructions
        # csrrwi x5, misa, 26
        decode.IFID_i.write(IFID_t(0x301d52f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=True,
            rs1=26,
            rd=5,
            wb_sel=3,
            f3=5,
            we=1
        )

        # csrrwi x0, misa, 26
        decode.IFID_i.write(IFID_t(0x301d5073, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0,
            csr_write_en=True,
            rs1=26,
            rd=0,
            wb_sel=3,
            f3=5,
            we=1
        )

        # csrrsi x5, misa, 26
        decode.IFID_i.write(IFID_t(0x301d62f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=True,
            rs1=26,
            rd=5,
            wb_sel=3,
            f3=6,
            we=1
        )

        # csrrsi x5, misa, 0
        decode.IFID_i.write(IFID_t(0x301062f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=False,
            rs1=0,
            rd=5,
            wb_sel=3,
            f3=6,
            we=1
        )

        # csrrci x5, misa, 26
        decode.IFID_i.write(IFID_t(0x301d72f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=True,
            rs1=26,
            rd=5,
            wb_sel=3,
            f3=7,
            we=1
        )

        # csrrci x5, misa, 0
        decode.IFID_i.write(IFID_t(0x301072f3, 0x80000004))
        sim.run_comb_logic()
        out = decode.IDEX_o.read()
        validate(
            out=out,
            csr_addr=0x301,
            csr_read_val=0x42,
            csr_write_en=False,
            rs1=0,
            rd=5,
            wb_sel=3,
            f3=7,
            we=1
        )


# ---------------------------------------
# Test EXECUTE
# ---------------------------------------

@pytest.fixture
def ex() -> EXStage:
    ex = EXStage()
    ex._init()
    return ex


class TestEXStage:
    def test_constructor(self, ex: EXStage):
        assert ex.IDEX_i._type == IDEX_t
        assert ex.EXMEM_o._type == EXMEM_t

    def test_passThrough(self, sim: Simulator, ex: EXStage):
        ex.IDEX_i.write(IDEX_t(
            rd=1,
            we=1,
            wb_sel=2,
            rs2=23,
            mem=1,
            funct3=5,
            csr_addr=123,
            csr_write_en=True,
            csr_read_val=45)
        )

        sim.step()

        out = ex.EXMEM_o.read()
        assert out.rd == 1
        assert out.we == 1
        assert out.wb_sel == 2
        assert out.rs2 == 23
        assert out.mem == 1
        assert out.funct3 == 5
        assert out.csr_addr == 123
        assert out.csr_write_en == True
        assert out.csr_read_val == 45

    def test_alu(self, ex: EXStage):
        # LUI
        res = ex.alu(0b01101, 0, 0, 0x41AF3000, 0, 0, 0)
        assert res == 0x41AF3000

        # AUIPC
        res = ex.alu(0b00101, 0, 0, 0x41AF3000, 0x10000000, 0, 0)
        assert res == 0x51AF3000

        # JAL
        res = ex.alu(0b11011, 0, 0, 0xB5E64, 0x80000000, 0, 0)
        assert res == 0x800B5E64

        res = ex.alu(0b11011, 0, 0, 0xffffffec, 0x90000000, 0, 0)
        assert res == 0x8FFFFFEC

        # JALR
        res = ex.alu(0b11001, 0x40000000, 0, 0x401, 0, 0, 0)
        assert res == 0x40000400

        res = ex.alu(0b11001, 0x90000000, 0, 0xffffffec, 0, 0, 0)
        assert res == 0x8FFFFFEC

        # BRANCH
        res = ex.alu(0b11000, 0, 0, 0xD58, 0x80000000, 0, 0)
        assert res == 0x80000D58

        res = ex.alu(0b11000, 0, 0, 0xffffffec, 0x90000000, 0, 0)
        assert res == 0x8FFFFFEC

        # LOAD
        res = ex.alu(0b00000, 0x60000000, 0, 0x7D2, 0, 0, 0)
        assert res == 0x600007D2

        # STORE
        res = ex.alu(0b01000, 0x60000000, 0, 0x7D2, 0, 0, 0)
        assert res == 0x600007D2

        # ADDI
        res = ex.alu(0b00100, 0x42, 0, 0x4593, 0, 0b000, 0)
        assert res == 0x45D5

        # SLTI
        res = ex.alu(opcode=0b00100, rs1=0, rs2=0, imm=0, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=1, rs2=0, imm=1, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=3, rs2=0, imm=7, pc=0, f3=0b010, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b00100, rs1=0x80000000, rs2=0, imm=0, pc=0, f3=0b010, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b00100, rs1=0x7fffffff, rs2=0, imm=0xfffff800, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=0x80000000, rs2=0, imm=0xfffff800, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=0xfffff800, rs2=0, imm=0x80000000, pc=0, f3=0b010, f7=0)
        assert res == 1

        # SLTIU
        res = ex.alu(opcode=0b00100, rs1=0, rs2=0, imm=0, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=1, rs2=0, imm=1, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=3, rs2=0, imm=7, pc=0, f3=0b011, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b00100, rs1=7, rs2=0, imm=3, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b00100, rs1=0, rs2=0, imm=0xfffff800, pc=0, f3=0b011, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b00100, rs1=0x80000000, rs2=0, imm=0xfffff800, pc=0, f3=0b011, f7=0)
        assert res == 1

        # XORI
        res = ex.alu(opcode=0b00100, rs1=0x00ff0f00, rs2=0, imm=0xffffff0f, pc=0, f3=0b100, f7=0)
        assert res == 0xff00f00f

        res = ex.alu(opcode=0b00100, rs1=0x00ff08ff, rs2=0, imm=0x0000070f, pc=0, f3=0b100, f7=0)
        assert res == 0x00ff0ff0

        # ORI
        res = ex.alu(opcode=0b00100, rs1=0xff00ff00, rs2=0, imm=0xffffff0f, pc=0, f3=0b110, f7=0)
        assert res == 0xffffff0f

        res = ex.alu(opcode=0b00100, rs1=0x00ff00ff, rs2=0, imm=0x0000070f, pc=0, f3=0b110, f7=0)
        assert res == 0x00ff07ff

        # ANDI
        res = ex.alu(opcode=0b00100, rs1=0xff00ff00, rs2=0, imm=0xffffff0f, pc=0, f3=0b111, f7=0)
        assert res == 0xff00ff00

        res = ex.alu(opcode=0b00100, rs1=0x00ff00ff, rs2=0, imm=0x0000070f, pc=0, f3=0b111, f7=0)
        assert res == 0x0000000f

        # SLLI
        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=0, pc=0, f3=0b001, f7=0)
        assert res == 0x00000001

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=1, pc=0, f3=0b001, f7=0)
        assert res == 0x00000002

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=7, pc=0, f3=0b001, f7=0)
        assert res == 0x00000080

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=31, pc=0, f3=0b001, f7=0)
        assert res == 0x80000000

        res = ex.alu(opcode=0b00100, rs1=0xffffffff, rs2=0, imm=7, pc=0, f3=0b001, f7=0)
        assert res == 0xffffff80

        res = ex.alu(opcode=0b00100, rs1=0x21212121, rs2=0, imm=14, pc=0, f3=0b001, f7=0)
        assert res == 0x48484000

        # SRLI
        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=0, pc=0, f3=0b101, f7=0)
        assert res == 0x00000001

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=1, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=7, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b00100, rs1=0x00000001, rs2=0, imm=31, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b00100, rs1=0xffffffff, rs2=0, imm=7, pc=0, f3=0b101, f7=0)
        assert res == 0x01ffffff

        res = ex.alu(opcode=0b00100, rs1=0x21212121, rs2=0, imm=14, pc=0, f3=0b101, f7=0)
        assert res == 0x00008484

        # SRAI
        res = ex.alu(opcode=0b00100, rs1=0x7fffffff, rs2=0, imm=0, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0x7fffffff

        res = ex.alu(opcode=0b00100, rs1=0x7fffffff, rs2=0, imm=1, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0x3fffffff

        res = ex.alu(opcode=0b00100, rs1=0x81818181, rs2=0, imm=1, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xc0c0c0c0

        res = ex.alu(opcode=0b00100, rs1=0x81818181, rs2=0, imm=7, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xff030303

        res = ex.alu(opcode=0b00100, rs1=0x81818181, rs2=0, imm=31, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xffffffff

        # ADD
        res = ex.alu(opcode=0b01100, rs1=0x42, rs2=0x4593, imm=0, pc=0, f3=0b000, f7=0)
        assert res == 0x45D5

        # SUB
        res = ex.alu(opcode=0b01100, rs1=0, rs2=0, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0x00000000

        res = ex.alu(opcode=0b01100, rs1=1, rs2=1, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0x00000000

        res = ex.alu(opcode=0b01100, rs1=3, rs2=7, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0xfffffffc

        res = ex.alu(opcode=0b01100, rs1=0, rs2=0xffff8000, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0x00008000

        res = ex.alu(opcode=0b01100, rs1=0, rs2=0x00007fff, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0xffff8001

        res = ex.alu(opcode=0b01100, rs1=0x7fffffff, rs2=0xffff8000, imm=0, pc=0, f3=0b000, f7=0b0100000)
        assert res == 0x80007fff

        # SLL
        res = ex.alu(opcode=0b01100, rs1=1, rs2=0, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0x00000001

        res = ex.alu(opcode=0b01100, rs1=1, rs2=1, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0x00000002

        res = ex.alu(opcode=0b01100, rs1=1, rs2=7, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0x00000080

        res = ex.alu(opcode=0b01100, rs1=1, rs2=31, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0x80000000

        res = ex.alu(opcode=0b01100, rs1=0xffffffff, rs2=7, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0xffffff80

        res = ex.alu(opcode=0b01100, rs1=0x21212121, rs2=14, imm=0, pc=0, f3=0b001, f7=0b0000000)
        assert res == 0x48484000

        # SLT
        res = ex.alu(opcode=0b01100, rs1=0, imm=0, rs2=0, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=1, imm=0, rs2=1, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=3, imm=0, rs2=7, pc=0, f3=0b010, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b01100, rs1=0x80000000, imm=0, rs2=0, pc=0, f3=0b010, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b01100, rs1=0x7fffffff, imm=0, rs2=0xfffff800, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=0x80000000, imm=0, rs2=0xfffff800, pc=0, f3=0b010, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=0xfffff800, imm=0, rs2=0x80000000, pc=0, f3=0b010, f7=0)
        assert res == 1

        # SLTU
        res = ex.alu(opcode=0b01100, rs1=0, imm=0, rs2=0, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=1, imm=0, rs2=1, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=3, imm=0, rs2=7, pc=0, f3=0b011, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b01100, rs1=7, imm=0, rs2=3, pc=0, f3=0b011, f7=0)
        assert res == 0

        res = ex.alu(opcode=0b01100, rs1=0, imm=0, rs2=0xfffff800, pc=0, f3=0b011, f7=0)
        assert res == 1

        res = ex.alu(opcode=0b01100, rs1=0x80000000, imm=0, rs2=0xfffff800, pc=0, f3=0b011, f7=0)
        assert res == 1

        # XOR
        res = ex.alu(opcode=0b01100, rs1=0x00ff0f00, rs2=0xffffff0f, imm=0, pc=0, f3=0b100, f7=0)
        assert res == 0xff00f00f

        res = ex.alu(opcode=0b01100, rs1=0x00ff08ff, rs2=0x0000070f, imm=0, pc=0, f3=0b100, f7=0)
        assert res == 0x00ff0ff0

        # SRL
        res = ex.alu(opcode=0b01100, rs1=0x00000001, imm=0, rs2=0, pc=0, f3=0b101, f7=0)
        assert res == 0x00000001

        res = ex.alu(opcode=0b01100, rs1=0x00000001, imm=0, rs2=1, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b01100, rs1=0x00000001, imm=0, rs2=7, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b01100, rs1=0x00000001, imm=0, rs2=31, pc=0, f3=0b101, f7=0)
        assert res == 0x00000000

        res = ex.alu(opcode=0b01100, rs1=0xffffffff, imm=0, rs2=7, pc=0, f3=0b101, f7=0)
        assert res == 0x01ffffff

        res = ex.alu(opcode=0b01100, rs1=0x21212121, imm=0, rs2=14, pc=0, f3=0b101, f7=0)
        assert res == 0x00008484

        # SRA
        res = ex.alu(opcode=0b01100, rs1=0x7fffffff, imm=0, rs2=0, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0x7fffffff

        res = ex.alu(opcode=0b01100, rs1=0x7fffffff, imm=0, rs2=1, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0x3fffffff

        res = ex.alu(opcode=0b01100, rs1=0x81818181, imm=0, rs2=1, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xc0c0c0c0

        res = ex.alu(opcode=0b01100, rs1=0x81818181, imm=0, rs2=7, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xff030303

        res = ex.alu(opcode=0b01100, rs1=0x81818181, imm=0, rs2=31, pc=0, f3=0b101, f7=0b0100000)
        assert res == 0xffffffff

        # OR
        res = ex.alu(opcode=0b01100, rs1=0xff00ff00, imm=0, rs2=0xffffff0f, pc=0, f3=0b110, f7=0)
        assert res == 0xffffff0f

        res = ex.alu(opcode=0b01100, rs1=0x00ff00ff, imm=0, rs2=0x0000070f, pc=0, f3=0b110, f7=0)
        assert res == 0x00ff07ff

        # AND
        res = ex.alu(opcode=0b01100, rs1=0xff00ff00, imm=0, rs2=0xffffff0f, pc=0, f3=0b111, f7=0)
        assert res == 0xff00ff00

        res = ex.alu(opcode=0b01100, rs1=0x00ff00ff, imm=0, rs2=0x0000070f, pc=0, f3=0b111, f7=0)
        assert res == 0x0000000f

    def test_branch(self, ex: EXStage):
        # BEQ
        res = ex.branch(f3=0, rs1=0, rs2=0)
        assert res == True

        res = ex.branch(f3=0, rs1=1, rs2=1)
        assert res == True

        res = ex.branch(f3=0, rs1=-1, rs2=-1)
        assert res == True

        res = ex.branch(f3=0, rs1=0, rs2=1)
        assert res == False

        res = ex.branch(f3=0, rs1=1, rs2=0)
        assert res == False

        res = ex.branch(f3=0, rs1=-1, rs2=1)
        assert res == False

        # BNE
        res = ex.branch(f3=1, rs1=0, rs2=0)
        assert res == False

        res = ex.branch(f3=1, rs1=1, rs2=1)
        assert res == False

        res = ex.branch(f3=1, rs1=-1, rs2=-1)
        assert res == False

        res = ex.branch(f3=1, rs1=0, rs2=1)
        assert res == True

        res = ex.branch(f3=1, rs1=1, rs2=0)
        assert res == True

        res = ex.branch(f3=1, rs1=-1, rs2=1)
        assert res == True

        # BLT
        res = ex.branch(f3=4, rs1=0, rs2=1)
        assert res == True

        res = ex.branch(f3=4, rs1=MASK_32 & (-1), rs2=1)
        assert res == True

        res = ex.branch(f3=4, rs1=MASK_32 & (-2), rs2=MASK_32 & (-1))
        assert res == True

        res = ex.branch(f3=4, rs1=1, rs2=0)
        assert res == False

        res = ex.branch(f3=4, rs1=1, rs2=MASK_32 & (-1))
        assert res == False

        res = ex.branch(f3=4, rs1=MASK_32 & (-1), rs2=MASK_32 & (-2))
        assert res == False

        res = ex.branch(f3=4, rs1=1, rs2=MASK_32 & (-2))
        assert res == False

        # BGE
        res = ex.branch(f3=5, rs1=0, rs2=0)
        assert res == True

        res = ex.branch(f3=5, rs1=1, rs2=1)
        assert res == True

        res = ex.branch(f3=5, rs1=MASK_32 & (-1), rs2=MASK_32 & (-1))
        assert res == True

        res = ex.branch(f3=5, rs1=1, rs2=0)
        assert res == True

        res = ex.branch(f3=5, rs1=1, rs2=MASK_32 & (-1))
        assert res == True

        res = ex.branch(f3=5, rs1=MASK_32 & (-1), rs2=MASK_32 & (-2))
        assert res == True

        res = ex.branch(f3=5, rs1=0, rs2=1)
        assert res == False

        res = ex.branch(f3=5, rs1=MASK_32 & (-1), rs2=1)
        assert res == False

        res = ex.branch(f3=5, rs1=MASK_32 & (-2), rs2=MASK_32 & (-1))
        assert res == False

        res = ex.branch(f3=5, rs1=MASK_32 & (-2), rs2=1)
        assert res == False

        # BLTU
        res = ex.branch(f3=6, rs1=0x00000000, rs2=0x00000001)
        assert res == True

        res = ex.branch(f3=6, rs1=0xfffffffe, rs2=0xffffffff)
        assert res == True

        res = ex.branch(f3=6, rs1=0x00000000, rs2=0xffffffff)
        assert res == True

        res = ex.branch(f3=6, rs1=0x00000001, rs2=0x00000000)
        assert res == False

        res = ex.branch(f3=6, rs1=0xffffffff, rs2=0xfffffffe)
        assert res == False

        res = ex.branch(f3=6, rs1=0xffffffff, rs2=0x00000000)
        assert res == False

        res = ex.branch(f3=6, rs1=0x80000000, rs2=0x7fffffff)
        assert res == False

        # BGEU
        res = ex.branch(f3=7, rs1=0x00000000, rs2=0x00000000)
        assert res == True

        res = ex.branch(f3=7, rs1=0x00000001, rs2=0x00000001)
        assert res == True

        res = ex.branch(f3=7, rs1=0xffffffff, rs2=0xffffffff)
        assert res == True

        res = ex.branch(f3=7, rs1=0x00000001, rs2=0x00000000)
        assert res == True

        res = ex.branch(f3=7, rs1=0xffffffff, rs2=0xfffffffe)
        assert res == True

        res = ex.branch(f3=7, rs1=0xffffffff, rs2=0x00000000)
        assert res == True

        res = ex.branch(f3=7, rs1=0x00000000, rs2=0x00000001)
        assert res == False

        res = ex.branch(f3=7, rs1=0xfffffffe, rs2=0xffffffff)
        assert res == False

        res = ex.branch(f3=7, rs1=0x00000000, rs2=0xffffffff)
        assert res == False

        res = ex.branch(f3=7, rs1=0x7fffffff, rs2=0x80000000)
        assert res == False

    def test_pc4(self, sim: Simulator, ex: EXStage):
        ex.IDEX_i.write(IDEX_t(
            pc=42
        ))
        sim.step()
        assert ex.EXMEM_o.read().pc4 == (42 + 4)

    def test_take_branch(self, sim: Simulator, ex: EXStage):
        def step_and_assert(expected):
            sim.step()
            assert ex.EXMEM_o.read().take_branch == expected

        # BEQ (B-type) -> take_branch should be set
        ex.IDEX_i.write(IDEX_t(opcode=0b11000, funct3=0, rs1=42, rs2=42))
        step_and_assert(True)

        # JAL
        ex.IDEX_i.write(IDEX_t(opcode=0b11011))
        step_and_assert(True)

        # JALR
        ex.IDEX_i.write(IDEX_t(opcode=0b11001))
        step_and_assert(True)

        # LUI
        ex.IDEX_i.write(IDEX_t(opcode=0b01101))
        step_and_assert(False)

        # AUIPC
        ex.IDEX_i.write(IDEX_t(opcode=0b00101))
        step_and_assert(False)

        # LOAD
        ex.IDEX_i.write(IDEX_t(opcode=0b00000))
        step_and_assert(False)

        # STORE
        ex.IDEX_i.write(IDEX_t(opcode=0b01000))
        step_and_assert(False)

        # OP-IMM (I-type)
        ex.IDEX_i.write(IDEX_t(opcode=0b00100))
        step_and_assert(False)

        # OP (R-type)
        ex.IDEX_i.write(IDEX_t(opcode=0b01100))
        step_and_assert(False)

        # FENCE
        ex.IDEX_i.write(IDEX_t(opcode=0b00011))
        step_and_assert(False)

        # ECALL / EBREAK
        ex.IDEX_i.write(IDEX_t(opcode=0b11100))
        step_and_assert(False)

    def test_csr(self, sim: Simulator, ex: EXStage):
        # csrrw
        ex.IDEX_i.write(IDEX_t(
            rs1=34,
            funct3=1,
            csr_read_val=123,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 34

        # csrrs
        ex.IDEX_i.write(IDEX_t(
            rs1=0xCCCC_CCCC,
            funct3=2,
            csr_read_val=0xAAAA_AAAA,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 0xEEEE_EEEE

        # csrrc
        ex.IDEX_i.write(IDEX_t(
            rs1=0xCCCC_CCCC,
            funct3=3,
            csr_read_val=0xAAAA_AAAA,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 0x2222_2222

        # csrrwi
        ex.IDEX_i.write(IDEX_t(
            rs1=26,
            funct3=5,
            csr_read_val=0xAAAA_AAAA,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 26

        # csrrsi
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1A,
            funct3=6,
            csr_read_val=0xAAAA_AAAA,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 0xAAAA_AABA

        # csrrci
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1A,
            funct3=7,
            csr_read_val=0xAAAA_AAAA,
            csr_write_en=True
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        assert out.csr_write_val == 0xAAAA_AAA0

    def test_EXStage(self, sim: Simulator, ex: EXStage):
        def validate(out: EXMEM_t, take_branch, alu_res, pc4, rd, we, wb_sel, rs2, mem, funct3):
            # Generated outputs
            assert out.take_branch == take_branch
            assert out.alu_res == alu_res

            # pc4 already covered by test_pc4, and is also independent from inst
            if pc4 is not None:
                assert out.pc4 == pc4

            # Pass-throughs are optional
            if rd is not None:
                assert out.rd == rd
            if we is not None:
                assert out.we == we
            if wb_sel is not None:
                assert out.wb_sel == wb_sel
            if rs2 is not None:
                assert out.rs2 == rs2
            if mem is not None:
                assert out.mem == mem
            if funct3 is not None:
                assert out.funct3 == funct3

        # LUI x24, 0xaffe
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=0xaffe << 12,
            pc=0x80000000,
            rd=24,
            we=True,
            wb_sel=0,
            opcode=0b01101
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0xaffe << 12,
            pc4=0x80000004,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # AUIPC x24, 0xaffe
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=0xaffe << 12,
            pc=0x80000004,
            rd=24,
            we=True,
            wb_sel=0,
            opcode=0b00101
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0x8AFFE004,
            pc4=0x80000008,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # JAL x13, 0x2DA89
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=0x2DA8A << 1,
            pc=0x80000008,
            rd=13,
            we=True,
            wb_sel=1,
            opcode=0b11011
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=True,
            alu_res=0x8005B51C,
            pc4=0x8000000C,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # JALR x13, x28, 0x401 (note: reg x28 not explictly needed; EXStage receives value of rs1)
        ex.IDEX_i.write(IDEX_t(
            rs1=0x4200,
            rs2=0,
            imm=0x401,
            pc=0x8000000C,
            rd=13,
            we=True,
            wb_sel=1,
            opcode=0b11001
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=True,
            alu_res=0x4600,
            pc4=0x80000010,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # B-type
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=32,
            pc=0x80000010,
            funct3=0,
            opcode=0b11000
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=True,
            alu_res=0x80000030,
            pc4=0x80000014,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # LOAD
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1000,
            imm=0x32,
            pc=0x80000014,
            funct3=0,
            opcode=0b00000
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0x1032,
            pc4=0x80000018,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # STORE
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1000,
            rs2=0x2000,
            imm=0x42,
            pc=0x80000018,
            funct3=0,
            opcode=0b01000
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0x1042,
            pc4=0x8000001C,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # I-type
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1000,
            imm=0x52,
            pc=0x8000001C,
            funct3=0,
            opcode=0b00100
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0x1052,
            pc4=0x80000020,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

        # R-type (OP)
        ex.IDEX_i.write(IDEX_t(
            rs1=0x1000,
            rs2=0x2000,
            pc=0x80000020,
            funct3=0,
            opcode=0b01100
        ))
        sim.step()
        out = ex.EXMEM_o.read()
        validate(
            out=out,
            take_branch=False,
            alu_res=0x3000,
            pc4=0x80000024,
            rd=None,
            we=None,
            wb_sel=None,
            rs2=None,
            mem=None,
            funct3=None
        )

    def test_exception(self, caplog, sim: Simulator, ex: EXStage):
        pc = 0x80004000

        # --- Misaligned instruction address ---------
        # JAL x13, 0x2DA89
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=0x2DA89 << 1,
            pc=pc,
            rd=13,
            opcode=0b11011
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # JALR x13, rs1, 0xA8A
        ex.IDEX_i.write(IDEX_t(
            rs1=0x80100000,
            rs2=0,
            imm=0xA8A,
            pc=pc,
            rd=13,
            opcode=0b11001
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BEQ
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=0,
            imm=0xA8B << 1,
            pc=pc,
            funct3=0,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BNE
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=1,
            imm=0xA8B << 1,
            pc=pc,
            funct3=1,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BLT
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=1,
            imm=0xA8B << 1,
            pc=pc,
            funct3=4,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BGE
        ex.IDEX_i.write(IDEX_t(
            rs1=1,
            rs2=0,
            imm=0xA8B << 1,
            pc=pc,
            funct3=5,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BLTU
        ex.IDEX_i.write(IDEX_t(
            rs1=0,
            rs2=1,
            imm=0xA8B << 1,
            pc=pc,
            funct3=6,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # BGEU
        ex.IDEX_i.write(IDEX_t(
            rs1=1,
            rs2=0,
            imm=0xA8B << 1,
            pc=pc,
            funct3=7,
            opcode=0b11000
        ))
        with pytest.raises(Exception, match=f"Target instruction address misaligned exception at PC = 0x{pc:08X}"):
            sim.step()
        pc += 4

        # No exception for not-taken branch
        # BEQ
        ex.IDEX_i.write(IDEX_t(
            rs1=1,
            rs2=0,
            imm=0xA8B << 1,
            pc=pc,
            funct3=0,
            opcode=0b11000
        ))
        sim.step()
        pc += 4


# ---------------------------------------
# Test MEMORY
# ---------------------------------------
class TestMEMStage:
    @pytest.fixture()
    def mem(self):
        dmem = Memory(1024)
        # Load memory
        dmem.mem[0:4] = [0xef, 0xbe, 0xad, 0xde]
        dmem.mem[4:8] = [0x23, 0x01, 0xde, 0xba]
        return dmem

    @pytest.fixture()
    def mem_stage(self, mem: Memory):
        return MEMStage(mem.read_port0, mem.write_port)

    def test_constructor(self, mem_stage):
        # Check Port types
        assert mem_stage.EXMEM_i._type == EXMEM_t
        assert mem_stage.MEMWB_o._type == MEMWB_t

    def test_passThrough(self, mem_stage, sim):
        mem_stage._init()

        mem_stage.EXMEM_i.write(EXMEM_t(
            rd=1,
            we=1,
            wb_sel=2,
            pc4=0xdeadbeef,
            alu_res=0xaffeaffe,
            csr_addr=123,
            csr_read_val=42,
            csr_write_en=True,
            csr_write_val=34
        ))
        sim.step()
        out = mem_stage.MEMWB_o.read()
        assert out.rd == 1
        assert out.we == 1
        assert out.wb_sel == 2
        assert out.pc4 == 0xdeadbeef
        assert out.alu_res == 0xaffeaffe
        assert out.csr_addr == 123
        assert out.csr_read_val == 42
        assert out.csr_write_en == True
        assert out.csr_write_val == 34

    def test_load(self, mem_stage, sim):
        mem_stage._init()

        # LB
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=2,  # addr
            funct3=0  # lb
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0xffffffad

        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=5,  # addr
            funct3=0  # lb
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0x00000001

        # LH
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=2,  # addr
            funct3=1  # lh
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0xffffdead

        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=4,  # addr
            funct3=1  # lh
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0x00000123

        # LW
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=0,  # addr
            funct3=2  # lw
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0xdeadbeef

        # LBU
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=2,  # addr
            funct3=4  # lbu
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0xad

        # LHU
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=2,  # addr
            funct3=5  # lbu
        ))
        sim.step()
        assert mem_stage.MEMWB_o.read().mem_rdata == 0xdead

    def test_store(self, mem_stage, mem, sim):
        mem_stage._init()

        # SB
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=2,  # store
            alu_res=3,  # addr
            rs2=0xabadbabe,  # wdata
            funct3=0  # sb
        ))
        sim.step()
        assert mem.mem[3] == 0xbe

        # SH
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=2,  # store
            alu_res=0,  # addr
            rs2=0xabadbabe,  # wdata
            funct3=1  # sh
        ))
        sim.step()
        assert mem.mem[0:2] == [0xbe, 0xba]

        # SW
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=2,  # store
            alu_res=0,  # addr
            rs2=0xabadbabe,  # wdata
            funct3=2  # sw
        ))
        sim.step()
        assert mem.mem[0:4] == [0xbe, 0xba, 0xad, 0xab]
    
    @pytest.mark.extraction
    def test_store_entropy(self, mem_stage, mem, sim):
        mem_stage._init()
        mem_stage.XT_i.write(XTIF_t(entropy=[61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60], active=True, ready=False, flush_bits=True))

        # state == 0 -> 1
        sim.step()
        assert mem.mem[64:68] == [0xf7, 0x7c, 0xcf, 0xf7]
        assert not mem_stage.TXT_o.read().flush_bits_ready

        # state == 1 -> 2
        sim.step()
        assert mem.mem[68:72] == [0xcf, 0xf7, 0x7c, 0xcf]

        # state == 2 -> 0
        sim.step()
        assert mem_stage.flush_state.next.read() == 0        # verify state reset
        assert mem.mem[72:76] == [0x7c, 0xcf, 0xf7, 0x7c]    # verify last chunk is dumped
        assert mem_stage.flush_ready.cur.read()
        assert mem_stage.TXT_o.read().flush_bits_ready

        # one more step after full flush
        sim.step()
        assert mem_stage.TXT_o.read().flush_bits_ready       # verify flush ready out is back down

        # one more step after flush signal is down
        mem_stage.XT_i.write(XTIF_t(entropy=[], active=True, ready=False, flush_bits=False))
        sim.step()
        assert mem_stage.flush_state.next.read() == 0        # verify state reset
        assert not mem_stage.TXT_o.read().flush_bits_ready       # verify flush ready out is down

    @pytest.mark.extraction
    def test_store_entropy_not_full(self, mem_stage, mem, sim):
        mem_stage._init()
        mem_stage.XT_i.write(XTIF_t(entropy=[61, 60, 61, 60], active=False, ready=True, flush_bits=True))
        # state == 0 -> 1
        sim.step()
        assert mem.mem[64:68] == [0xf0, 0x3d, 0xdf, 0x03]
        # state == 1 -> 2
        sim.step()
        assert mem.mem[68:72] == [0x00, 0x00, 0x00, 0x00]
        # state == 2 -> 0
        sim.step()
        assert mem.mem[68:72] == [0x00, 0x00, 0x00, 0x00]
        

    @pytest.mark.extraction
    def test_entropy_integr(self, mem_stage, sim):
        mem_stage._init()
        extractor = Extractor()
        extractor._init()

        extractor.TXT_i << mem_stage.TXT_o
        mem_stage.XT_i << extractor.XTIF_o

        extractor.flush_bits = True
        extractor.eb_reg.cur.write([61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60])
        extractor.eb_reg.next.write([61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60])
        extractor.ready_out == False
        extractor.active_out == True

        # state == 0 -> 1
        sim.step()
        # state == 1 -> 2
        sim.step()
        # state == 2 -> 0
        sim.step()
        # one more step after full flush
        sim.step()
        assert mem_stage.TXT_o.read().flush_bits_ready       # verify flush ready out
        assert not extractor.XTIF_o.read().flush_bits

        # one more step after flush signal is down
        mem_stage.EXMEM_i.write(EXMEM_t(mem=1, alu_res=4, rs2=0xabadbabe, funct3=1))
        sim.step()
        # assert mem_stage.flush_state.next.read() == 0        # TODO find a way to verify state reset
        assert not mem_stage.TXT_o.read().flush_bits_ready       # verify flush ready out is down
    
    @pytest.mark.extraction
    @pytest.mark.visual
    def test_entropy_full_integr(self, mem_stage, mem, sim):
        mem_stage._init()
        
        extractor = Extractor()
        extractor._init()
        
        imem = Memory(1024)
        imem._init()
        fetch = IFStage(imem.read_port1)
        fetch._init()

        extractor.IFXT_i << fetch.IFXT_o
        fetch.XTIF_i << extractor.XTIF_o
        extractor.TXT_i << mem_stage.TXT_o
        mem_stage.XT_i << extractor.XTIF_o

        # initialize instruction memory
        for i in range(0, 80, 8):
            imem.mem[i:i+4] = [0x33, 0x26, 0xa4, 0xfa]
            imem.mem[i+4:i+8] = [0x33, 0x26, 0xa4, 0xf8]
        imem.mem[84:88] = [0xff, 0xff, 0xff, 0xff]
        pc = 0x00000000

        print("\n\nInitialized")
        print("Instruction fetched:", hex(fetch.IFXT_o.read().inst))
        print("Instruction forwarded:", hex(fetch.IFID_o.read().inst))
        print("Extractor output state:", extractor.XTIF_o.read())
        
        for i in range(0, 33):
            sim.step()
            print("\nCycle", i)
            print("Instruction fetched:", hex(fetch.IFXT_o.read().inst))
            print("Instruction forwarded:", hex(fetch.IFID_o.read().inst))
            print("Extractor output state:", extractor.XTIF_o.read())
            print("Memory boxes:",
                  mem.mem[64:68],
                  mem.mem[68:72],
                  mem.mem[72:76],
                  mem.mem[76:80],
                  mem.mem[80:84],
                  mem.mem[84:88])
        
        assert mem.mem[64:88] == [0xf7, 0x7c, 0xcf, 0xf7,
                                  0xcf, 0xf7, 0x7c, 0xcf,
                                  0x7c, 0xcf, 0xf7, 0x7c,
                                  0xf0, 0x3d, 0xdf, 0x03,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0]
        assert fetch.IFXT_o.read().inst == 0xfaa42633

    def test_exception(self, mem_stage, caplog, sim):
        mem_stage._init()

        # --- Load address misaligned ---------------
        # LH/LHU
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=1,  # addr
            funct3=1  # lh
        ))
        sim.step()
        assert "Misaligned load from address 0x00000001" in caplog.text
        caplog.clear()

        # LW
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=1,  # load
            alu_res=3,  # addr
            funct3=2  # lw
        ))
        sim.step()
        assert "Misaligned load from address 0x00000003" in caplog.text
        caplog.clear()

        # --- Store address misaligned --------------
        # SH
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=2,  # store
            alu_res=1,  # addr
            funct3=1  # sh
        ))
        sim.step()
        assert "Misaligned store to address 0x00000001" in caplog.text
        caplog.clear()

        # SW
        mem_stage.EXMEM_i.write(EXMEM_t(
            mem=2,  # store
            alu_res=3,  # addr
            funct3=2  # sw
        ))
        sim.step()
        assert "Misaligned store to address 0x00000003" in caplog.text
        caplog.clear()


# ---------------------------------------
# Test WRITE-BACK
# ---------------------------------------
@pytest.fixture
def wb() -> WBStage:
    regf = Regfile()
    wb = WBStage(regf)
    wb._init()
    return wb


class TestWBStage:
    def test_constructor(self, wb: WBStage):
        assert wb.MEMWB_i._type == MEMWB_t

    def test_wb(self, sim: Simulator, wb: WBStage):
        # ALU op
        wb.MEMWB_i.write(MEMWB_t(
            rd=18,
            we=1,
            alu_res=42,
            pc4=87,
            mem_rdata=0xdeadbeef,
            wb_sel=0
        ))
        sim.step()
        assert wb.regfile.read(18) == 42

        # PC+4 (JAL)
        wb.MEMWB_i.write(MEMWB_t(
            rd=31,
            we=1,
            alu_res=42,
            pc4=87,
            mem_rdata=0xdeadbeef,
            wb_sel=1
        ))
        sim.step()
        assert wb.regfile.read(31) == 87

        # Memory load
        wb.MEMWB_i.write(MEMWB_t(
            rd=4,
            we=1,
            alu_res=42,
            pc4=87,
            mem_rdata=0xdeadbeef,
            wb_sel=2
        ))
        sim.step()
        assert wb.regfile.read(4) == 0xdeadbeef

    def test_no_wb(self, sim: Simulator, wb: WBStage):
        wb.regfile.regs[25] = 1234

        val = MEMWB_t(
            we=0,
            rd=25,
            alu_res=24,
            pc4=25,
            mem_rdata=26
        )

        # ALU op
        val.wb_sel = 0
        wb.MEMWB_i.write(val)
        sim.step()
        assert wb.regfile.read(25) == 1234

        # PC+4 (JAL)
        val.wb_sel = 1
        wb.MEMWB_i.write(val)
        sim.step()
        assert wb.regfile.read(25) == 1234

        # Memory load
        val.wb_sel = 2
        wb.MEMWB_i.write(val)
        sim.step()
        assert wb.regfile.read(25) == 1234

    def test_csr(self, sim: Simulator, wb: WBStage, csr: CSRUnit):
        csr.write_addr_i << wb.csr_write_addr_o
        csr.write_en_i << wb.csr_write_en_o
        csr.write_val_i << wb.csr_write_val_o

        misa = 0x301

        wb.MEMWB_i.write(MEMWB_t(
            rd=5,
            we=1,
            alu_res=42,
            pc4=87,
            mem_rdata=0xdeadbeef,
            wb_sel=3,
            csr_addr=misa,
            csr_read_val=65,
            csr_write_en=True,
            csr_write_val=45
        ))
        sim.step()
        assert wb.regfile.regs[5] == 65
        assert csr.csr_bank.csrs[misa].csr_val_o.read() == 45

        # No CSR
        wb.MEMWB_i.write(MEMWB_t(
            rd=5,
            we=1,
            alu_res=42,
            pc4=87,
            mem_rdata=0xdeadbeef,
            wb_sel=0,
            csr_addr=misa,
            csr_read_val=65,
            csr_write_en=False,
            csr_write_val=56
        ))
        sim.step()
        assert wb.regfile.regs[5] == 42
        assert csr.csr_bank.csrs[misa].csr_val_o.read() == 45


# ---------------------------------------
# Test Branch Unit
# ---------------------------------------
def test_branch_unit(sim):
    bu = BranchUnit()
    bu._init()

    # Test ports
    assert bu.pc_i._type == int
    assert bu.take_branch_i._type == bool
    assert bu.target_i._type == int
    assert bu.npc_o._type == int

    # Test regular PC increment
    bu.pc_i.write(0x80000000)
    bu.take_branch_i.write(False)
    bu.target_i.write(0x40000000)
    sim.step()
    assert bu.npc_o.read() == 0x80000004

    # Test taken branch
    bu.pc_i.write(0x80000000)
    bu.take_branch_i.write(True)
    bu.target_i.write(0x40000000)
    sim.step()
    assert bu.npc_o.read() == 0x40000000
