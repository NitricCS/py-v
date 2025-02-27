import time
from datetime import datetime
from pyv.exceptions import IllegalInstructionException, InstructionAddressMisalignedException, PCOutOfBoundException, SegmentationFaultException
from pyv.models.model import Model
from pyv.models.singlecycle import SingleCycleModel
from pyv.models.singlecycle_entropy import SingleCycleEntropyModel
from pyv.simulator import Simulator
from pyv.log import logger

def execute_bin(
        core_type: str,
        program_name: str,
        path_to_bin: str,
        num_cycles: int,
        fi_params = (None, None, None, None)) -> Model:
    
    print(f"\nRunning {program_name} on core {core_type}")

    # Create core instance
    if core_type == 'single':
        core = SingleCycleModel()
    elif core_type == 'single_entropy':
        core = SingleCycleEntropyModel()

    # Load binary into memory
    core.load_binary(path_to_bin)
    # Set probes
    core.setProbes([])
    # Set fault injection cycle
    fi_cycle = fi_params[0]
    if fi_cycle:
        core.setFICycle(fi_cycle)
        core.setFIParams(fi_params)
        print(f"FI on cycle {fi_cycle}")

    # Simulate
    start = time.perf_counter()
    logger.info(f"Starting timestamp: {time.perf_counter()}")
    core.run(num_cycles)
    end = time.perf_counter()

    print(f"Simulation done at cycle {core.getCycles()} after {end-start}s.")

    return core

def fibonacci(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = 'programs/fibonacci/fibonacci.bin'
    program_name="fibonacci"
    num_cycles = 137

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    result = core.readDataMem(2048, 4)
    print("Program result: ", result, "\n")
    return result

def fibonacci_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = 'programs/fibonacci/fibonacci_e.bin'
    program_name="fibonacci with entropy"
    num_cycles = 178

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    result = core.readDataMem(2048, 4)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", result, "\n")
    return result

def atoi(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/atoi/atoi.bin"
    program_name="atoi"
    num_cycles = 800

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def atoi_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/atoi/atoi_e.bin"
    program_name="atoi with entropy"
    num_cycles = 2417

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def strcpy(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/strcpy/strcpy.bin"
    program_name="strcpy"
    num_cycles = 161

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program results: ", core.readDataMem(2048, 8), core.readDataMem(2082, 8), "\n")
    return (core.readDataMem(2048, 8), core.readDataMem(2082, 8))

def strcpy_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/strcpy/strcpy_e.bin"
    program_name="strcpy with entropy"
    num_cycles = 265

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program results: ", core.readDataMem(2048, 8), core.readDataMem(2082, 8), "\n")
    return (core.readDataMem(2048, 8), core.readDataMem(2082, 8))

def memset(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/memset/memset.bin"
    program_name="memset"
    num_cycles = 30

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def memset_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/memset/memset_e.bin"
    program_name="memset with entropy"
    num_cycles = 108

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)