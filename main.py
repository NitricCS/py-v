import time
from pyv.isa import IllegalInstructionException
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
        fi_cycle: int = None) -> Model:
    
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
    if fi_cycle:
        core.setFICycle(fi_cycle)
        print(f"FI on cycle {fi_cycle}")
    
    if core_type == 'single_entropy':
        print("=== Entropy space before execution: ", core.readDataMem(1024, 12))
    print("=== Memory before execution: ", core.readDataMem(2048, 4))

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

def fibonacci(core_type="single", fi_cycle=None):
    path_to_bin = 'programs/fibonacci/fibonacci.bin'
    program_name="fibonacci"
    num_cycles = 140

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_cycle)
    result = core.readDataMem(2048, 4)
    print("Program result: ", result, "\n")
    return result

def fibonacci_entropy(core_type="single_entropy", fi_cycle=None):
    path_to_bin = 'programs/fibonacci/fibonacci_e.bin'
    program_name="fibonacci with entropy"
    num_cycles = 220

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_cycle)
    result = core.readDataMem(2048, 4)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", result, "\n")
    return result

def simple(core_type="single", fi_cycle=None):
    path_to_bin = "programs/test/test.bin"
    program_name="memory write test"
    num_cycles = 200
    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_cycle)
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")

def atoi(core_type="single", fi_cycle=None):
    path_to_bin = "programs/atoi/atoi.bin"
    program_name="atoi"
    num_cycles = 1000

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_cycle)
    print("Program result: ", core.readDataMem(2048, 4), "\n")
    return core.readDataMem(2048, 4)

def atoi_entropy(core_type="single_entropy", fi_cycle=None):
    path_to_bin = "programs/atoi/atoi.bin"
    program_name="atoi with entropy"
    num_cycles = 1000

    core = execute_bin(core_type, program_name, path_to_bin, num_cycles, fi_cycle)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4), "\n")

def entropy_test(core_type="single_entropy"):
    num_cycles = 500

    core = execute_test(core_type, num_cycles)
    print("=== Entropy: ", core.readDataMem(1024, 12))
    print("=== Program result: ", core.readDataMem(2048, 4))

def inject_faults(program, core_type: str, cycle_start: int, cycle_end: int, expected_result) -> list:
    fi_results = []
    for fi_cycle in range(cycle_start, cycle_end):
        try:
            res = program(core_type, fi_cycle)
            if res != expected_result:
                fi_results.append("Target meet")
                print("### TARGET MEET ###")
            else:
                fi_results.append("No effect")
            # print(res)
        except IllegalInstructionException:
            fi_results.append("PC out of bound")
            print("### PC OUT OF BOUND ###")
        # except IndexError:
        #     fi_results.append("Other issue")
        #     print("### MEMORY INDEX ERROR ###")
        finally:
            Simulator.globalSim.clear()
    return fi_results

def plot_fi_results(program, fi_results: list, cycle_start: int, cycle_end: int):
    x = np.arange(cycle_start, cycle_end, 1)
    y = np.array(fi_results)
    y_mapping = {'Target meet': 3, 'PC out of bound': 2, 'Other issue': 1, 'No effect': 0}
    y_mapped = [y_mapping[val] for val in y]

    plt.figure(figsize=(10, 6))
    plt.scatter(x, y_mapped, c='blue', marker='d')
    plt.yticks(list(y_mapping.values()), list(y_mapping.keys()))
    plt.xlabel('Fault Injection Cycle')
    plt.ylabel('Effect')
    plt.xticks(np.arange(min(x), max(x)+1, 2.0))
    plt.title(program.__name__)

    plt.show()


def main():
    fi_results = inject_faults(fibonacci, "single", 59, 60, ['0x37', '0x0', '0x0', '0x0'])
    # fi_results = inject_faults(fibonacci_entropy, "single_entropy", 30, 32, ['0x37', '0x0', '0x0', '0x0'])
    # plot_fi_results(fibonacci, fi_results, 30, 60)

    # entropy_test()
    # atoi()
    # atoi_entropy()
    # fibonacci()
    # fibonacci_entropy()
    # simple()
    # simple_entropy()


if __name__ == '__main__':
    main()
