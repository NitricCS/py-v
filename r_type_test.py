import time
from pyv.models.model import Model
from pyv.models.singlecycle import SingleCycleModel
from pyv.models.singlecycle_entropy import SingleCycleEntropyModel
from pyv.simulator import Simulator
from pyv.log import logger


def convert_instrustion(inst):
    return [int(f"0x{inst[6]}{inst[7]}", 16),
            int(f"0x{inst[4]}{inst[5]}", 16),
            int(f"0x{inst[2]}{inst[3]}", 16),
            int(f"0x{inst[0]}{inst[1]}", 16)]

def load_instruction_list(file):
    inst_list = []
    with open(file, "r") as f:
        for line in f:
            inst_list += convert_instrustion(line)
    return inst_list

def execute_test(
        core_type: str,
        inst_list: list,
        num_cycles: int) -> Model:

    # Create core instance
    if core_type == 'single':
        core = SingleCycleModel()
    elif core_type == 'single_entropy':
        core = SingleCycleEntropyModel()

    # Load instructions into memory
    core.load_instructions(inst_list)
    # Set probes
    core.setProbes([])

    start = time.perf_counter()
    core.run(num_cycles)
    end = time.perf_counter()

    print(f"Simulation done at cycle {core.getCycles()} after {end-start}s.")

    return core


if __name__ == "__main__":
    inst_list = load_instruction_list("data/inst/program_5.mem")
    core = execute_test(core_type='single', inst_list=inst_list, num_cycles=100)
    print("=== Program result: ", core.readDataMem(2048, 4))
