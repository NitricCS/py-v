import time
from datetime import datetime
from pyv.exceptions import IllegalInstructionException, InstructionAddressMisalignedException, PCOutOfBoundException, SegmentationFaultException
from pyv.models.model import Model
from pyv.models.singlecycle import SingleCycleModel
from pyv.models.singlecycle_entropy import SingleCycleEntropyModel
from pyv.simulator import Simulator

import matplotlib.pyplot as plt
import numpy as np


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
    core.run(num_cycles)
    end = time.perf_counter()

    print(f"Simulation done at cycle {core.getCycles()} after {end-start}s.")

    return core

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


# def loop_acc():
#     core_type = 'single'
#     program_name = 'LOOP_ACC'
#     path_to_bin = 'programs/loop_acc/loop_acc.bin'
#     num_cycles = 2010

#     core = execute_bin(core_type, program_name, path_to_bin, num_cycles)

#     # Print register and memory contents
#     print("x1 = " + str(core.readReg(1)))
#     print("x2 = " + str(core.readReg(2)))
#     print("x5 = " + str(core.readReg(5)))
#     print("pc = " + str(hex(core.readPC())))
#     print("mem@4096 = ", core.readDataMem(4096, 4))
#     print("")


# def fibonacci():
#     core_type = 'single'
#     program_name = 'FIBONACCI'
#     path_to_bin = 'programs/fibonacci/fibonacci.bin'
#     num_cycles = 140

#     core = execute_bin(core_type, program_name, path_to_bin, num_cycles)

#     # Print result
#     print("Result = ", core.readDataMem(2048, 4))
#     print("")


# def endless_loop():
#     core_type = 'single'
#     program_name = 'ENDLESS_LOOP'
#     path_to_bin = 'programs/endless_loop/endless_loop.bin'
#     num_cycles = 1000

#     execute_bin(core_type, program_name, path_to_bin, num_cycles)

def fibonacci(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = 'programs/fibonacci/fibonacci.bin'
    program_name="fibonacci"
    num_cycles = 140

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    result = core.readDataMem(2048, 4)
    print("Program result: ", result, "\n")
    return result

def fibonacci_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = 'programs/fibonacci/fibonacci_e.bin'
    program_name="fibonacci with entropy"
    num_cycles = 220

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    result = core.readDataMem(2048, 4)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", result, "\n")
    return result

def simple(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/test/test.bin"
    program_name="memory write test"
    num_cycles = 200
    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")

def atoi(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/atoi/atoi.bin"
    program_name="atoi"
    num_cycles = 1000

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def atoi_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/atoi/atoi_e.bin"
    program_name="atoi with entropy"
    num_cycles = 3000

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def strcpy(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/strcpy/strcpy.bin"
    program_name="strcpy"
    num_cycles = 180

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program results: ", core.readDataMem(2048, 8), core.readDataMem(2082, 8), "\n")
    return (core.readDataMem(2048, 8), core.readDataMem(2082, 8))

def strcpy_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/strcpy/strcpy.bin"
    program_name="strcpy with entropy"
    num_cycles = 1500

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program results: ", core.readDataMem(2048, 8), core.readDataMem(2082, 8), "\n")
    return (core.readDataMem(2048, 8), core.readDataMem(2082, 8))

def itoa(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/itoa/itoa.bin"
    program_name="itoa"
    num_cycles = 1000

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 8), core.readDataMem(2082, 8), "\n")
    return core.readDataMem(2048, 8)

def memset(core_type="single", fi_params=(None, None, None, None)):
    path_to_bin = "programs/memset/memset.bin"
    program_name="memset"
    num_cycles = 40

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def memset_entropy(core_type="single_entropy", fi_params=(None, None, None, None)):
    path_to_bin = "programs/memset/memset_e.bin"
    program_name="memset with entropy"
    num_cycles = 600

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_params)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def entropy_test(core_type="single_entropy"):
    num_cycles = 500

    core = execute_test(core_type, num_cycles)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4))

def inject_faults(program,
                  core_type: str,
                  cycle_start: int,
                  cycle_end: int,
                  expected_result,
                  fi_index: int,
                  num_bits: int,
                  fi_type: str) -> list:
    fi_results = []
    for fi_cycle in range(cycle_start, cycle_end):
        fi_params = (fi_cycle, fi_index, num_bits, fi_type)
        try:
            res = program(core_type, fi_params)
            if res != expected_result:
                fi_results.append("Target meet")
                print("### TARGET MEET ###")
            else:
                fi_results.append("No effect")
        except PCOutOfBoundException:
            fi_results.append("PC out of bound")
            print("### PC OUT OF BOUND ###")
        except SegmentationFaultException:
            fi_results.append("Other issue")
            print("### MEMORY INDEX ERROR ###")
        except InstructionAddressMisalignedException:
            fi_results.append("Other issue")
            print("### INSTRUCTION ADDRESS MISALIGNED ###")
        except IllegalInstructionException:
            fi_results.append("Illegal instruction")
            print("### INSTRUCTION MEMORY CORRUPTED ###")
        except Exception:
            fi_results.append("Processor broke")
            print("### PROCESSOR FUNCTIONING VIOLATED ###")
        finally:
            Simulator.globalSim.clear()
    return fi_results

def plot_fi_results(program, fi_results: list, cycle_start: int, cycle_end: int, fi_index: int, num_bits: int, fi_type: str):
    x = np.arange(cycle_start, cycle_end, 1)
    y = np.array(fi_results)
    y_mapping = {'Target meet': 5, 'Processor broke': 4, 'Illegal instruction': 3, 'PC out of bound': 2, 'Other issue': 1, 'No effect': 0}
    y_mapped = [y_mapping[val] for val in y]

    plt.figure(figsize=(12, 6))
    plt.scatter(x, y_mapped, c='blue', marker='d')
    plt.yticks(list(y_mapping.values()), list(y_mapping.keys()))
    plt.xlabel('Fault Injection Cycle')
    plt.ylabel('Effect')
    plt.xticks(np.arange(min(x), max(x)+1, 4.0))
    plt.title(f"{program.__name__} · {num_bits} bit {fi_type} on bit {fi_index}")

    now = datetime.now()
    ts = now.strftime("%y%m%d_%H%M")

    plt.savefig(f"figs/{program.__name__}_{ts}.png")


def main():
    settings = {
        "program": atoi_entropy,
        "core_type": "single_entropy",
        "cycle_start": 40,
        "cycle_end": 60,
        "expected_result": ['0xd2', '0x4', '0x0', '0x0'],
        "fi_index": 28,
        "num_bits": 1,
        "fi_type": "flip"
    }

    # fi_results = inject_faults(**settings)

    # plt_settings = (settings["program"], fi_results, settings["cycle_start"], settings["cycle_end"], settings["fi_index"], settings["num_bits"], settings["fi_type"])
    # plot_fi_results(*plt_settings)

    # fi_results = inject_faults(fibonacci_entropy, "single_entropy", 30, 32, ['0x37', '0x0', '0x0', '0x0'])
    # plot_fi_results(fibonacci, fi_results, 30, 32)

    # entropy_test()
    # atoi()
    atoi_entropy()
    # strcpy()
    # strcpy_entropy()
    # memset()
    # memset_entropy()
    # fibonacci()
    # fibonacci_entropy()


if __name__ == '__main__':
    main()
