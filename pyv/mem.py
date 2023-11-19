from dataclasses import dataclass
from pyv.module import Module
from pyv.port import Input, Output
from pyv.util import MASK_32, PyVObj
import pyv.log as log
from pyv.clocked import Clocked, MemBase

logger = log.getLogger(__name__)


class ReadPort(PyVObj):
    def __init__(self,
        re_i: Input[bool],
        width_i: Input[int],
        addr_i: Input[int],
        rdata_o: Output[int]
    ):
        super().__init__()

        self.re_i = re_i
        """Read-enable input"""
        self.width_i = width_i
        """Data width input (1, 2, or 4)"""
        self.addr_i = addr_i
        """Address input (also for write)"""
        self.rdata_o = rdata_o
        """Read port 0 Read data output"""

class WritePort(PyVObj):
    def __init__(self,
        we_i: Input[bool],
        wdata_i: Input[int]
    ):
        super().__init__()

        self.we_i = we_i
        """Write-enable input"""
        self.wdata_i = wdata_i
        """Write data input"""

# TODO: Check if addr is valid
class Memory(Module, Clocked):
    """Simple memory module with 2 read ports and 1 write port

    A memory is represented by a simple list of bytes.

    Byte-ordering: Little-endian
    """

    def __init__(self, size: int = 32):
        """Memory constructor.

        Args:
            size: Size of memory in bytes.
        """
        super().__init__()
        MemBase.add_to_mem_list(self)
        self.mem = [ 0 for i in range(0,size) ]
        """Memory array. List of length `size`."""

        # Read port 0
        self.read_port0 = ReadPort(
            re_i=Input(bool, [self.process_read0]),
            width_i=Input(int, [self.process_read0]),
            addr_i=Input(int, [self.process_read0]),
            rdata_o=Output(int)
        )

        # Read port 1
        self.read_port1 = ReadPort(
            re_i=Input(bool, [self.process_read1]),
            width_i=Input(int, [self.process_read1]),
            addr_i=Input(int, [self.process_read1]),
            rdata_o=Output(int)
        )

        # Write port (uses addr, width from read port 0)
        self.write_port = WritePort(
            we_i=Input(bool, [None]),
            wdata_i=Input(int, [None])
        )

    def _read(self, addr, w):
        # During the processing of the current cycle, it might occur that
        # an unstable port value is used as the address. However, the port
        # will eventually become stable, so we should "allow" that access
        # by just returning a dummy value, e.g., 0.
        #
        # Note: An actual illegal address exception caused by a running
        # program should be handled synchronously, i.e. with the next
        # active clock edge (tick).
        try:
            if w == 1: # byte
                val = MASK_32 & self.mem[addr]
            elif w == 2: # half word
                val = MASK_32 & (self.mem[addr+1]<<8 | self.mem[addr])
            elif w == 4: # word
                val = MASK_32 & (self.mem[addr+3]<<24 | self.mem[addr+2]<<16 | self.mem[addr+1]<<8 | self.mem[addr])
            else:
                raise Exception('ERROR (Memory ({}), read): Invalid width {}'.format(self.name, w))

            logger.debug("MEM ({}): read value 0x{:08X} from address 0x{:08X}".format(self.name, val, addr))
        except IndexError:
            logger.warn("Potentially illegal memory address 0x{:08X}. This might be normal during cycle processing.".format(addr))
            val = 0

        return val

    def process_read0(self):
        re = self.read_port0.re_i.read()
        addr = self.read_port0.addr_i.read()
        w = self.read_port0.width_i.read()

        if re:
            val = self._read(addr, w)
        else:
            val = 0

        self.read_port0.rdata_o.write(val)

    def process_read1(self):
        re = self.read_port1.re_i.read()
        addr = self.read_port1.addr_i.read()
        w = self.read_port1.width_i.read()

        if re:
            val = self._read(addr, w)
        else:
            val = 0

        self.read_port1.rdata_o.write(val)

    def _tick(self):
        we = self.write_port.we_i.read()
        addr = self.read_port0.addr_i.read()
        wdata = self.write_port.wdata_i.read()
        w = self.read_port0.width_i.read()


        if we:
            if not (w == 1 or w == 2 or w == 4):
                raise Exception('ERROR (Memory ({}), write): Invalid width {}'.format(self.name, w)) 
            logger.debug("MEM {}: write 0x{:08X} to address 0x{:08X}".format(self.name, wdata, addr))

            if w == 1: # byte
                self.mem[addr] = 0xff & wdata
            elif w == 2: # half word
                self.mem[addr] = 0xff & wdata
                self.mem[addr+1] = (0xff00 & wdata)>>8
            elif w == 4: # word
                self.mem[addr] = 0xff & wdata
                self.mem[addr+1] = (0xff00 & wdata)>>8 
                self.mem[addr+2] = (0xff0000 & wdata)>>16
                self.mem[addr+3] = (0xff000000 & wdata)>>24

    # TODO: when memory gets loaded with program *before* simulation, simulation start
    # will cause a reset. So for now, we skip the reset here.
    def _reset(self):
        return
        """Reset memory.

        All elements are set to 0.
        """
        for i in range(0, len(self.mem)):
            self.mem[i] = 0