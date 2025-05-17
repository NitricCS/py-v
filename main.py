import time
from pyv.exceptions import IllegalInstructionException, InstructionAddressMisalignedException, PCOutOfBoundException, SegmentationFaultException
from pyv.models.model import Model
from pyv.models.singlecycle import SingleCycleModel
from pyv.models.singlecycle_entropy import SingleCycleEntropyModel
from pyv.simulator import Simulator
from pyv.log import logger
from testbench import Testbench

import programs


def execute_test(
        core_type: str,
        num_cycles: int) -> Model:

    # Create core instance
    if core_type == 'single':
        core = SingleCycleModel()
    elif core_type == 'single_entropy':
        core = SingleCycleEntropyModel()

    # Load instructions into memory
    core.load_instructions(
        [0x13, 0x03, 0x10, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0xa0,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0xb3, 0x02, 0x00, 0x00,
         0xb3, 0x02, 0x03, 0x00,
         0x13, 0x05, 0x00, 0x7d,
         0x33, 0x03, 0x50, 0x00,
         0x23, 0x28, 0x65, 0x02,
         0x63, 0x00, 0x00, 0x00,
         0xff, 0xff, 0xff, 0xff]
    )
    # Set probes
    core.setProbes([])

    start = time.perf_counter()
    core.run(num_cycles)
    end = time.perf_counter()

    print(f"Simulation done at cycle {core.getCycles()} after {end-start}s.")

    return core

def entropy_test(core_type="single_entropy"):
    num_cycles = 500

    core = execute_test(core_type, num_cycles)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4))

def main():
    bench = Testbench()
    programs.memset()

if __name__ == '__main__':
    main()
