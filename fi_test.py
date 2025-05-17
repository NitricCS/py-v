import re
import sqlite3
import programs
from matplotlib import pyplot as plt
import numpy as np
from datetime import datetime
from pyv.exceptions import IllegalInstructionException, InstructionAddressMisalignedException, PCOutOfBoundException, SegmentationFaultException
from pyv.simulator import Simulator
from testbench import Testbench

conn = sqlite3.connect('data/fi_full.db')
c = conn.cursor()

# def insert_result(program_name, bit_index, cycle, num_bits, fi_result, end_cycle, entropy_corr):
def insert_result(program_name, bit_index, cycle, num_bits, fi_result, end_cycle):
    # c.execute(f"INSERT INTO {program_name} (program_name, fi_bit_index, fi_cycle, num_bits, fi_result, end_cycle, entropy_corrupted) VALUES (\'{program_name}\', {bit_index}, {cycle}, \'{num_bits}\', \'{fi_result}\', \'{end_cycle}\', \'{entropy_corr}\')")
    c.execute(f"INSERT INTO {program_name} (program_name, fi_bit_index, fi_cycle, num_bits, fi_result, end_cycle) VALUES (\'{program_name}\', {bit_index}, {cycle}, \'{num_bits}\', \'{fi_result}\', \'{end_cycle}\')")
    conn.commit()

def clear_table(program_name):
    c.execute(f"DELETE FROM {program_name}")
    conn.commit()

def inject_faults(program,
                  core_type: str,
                  cycle_start: int,
                  cycle_end: int,
                  fi_index: int,
                  num_bits: int) -> list:
    program_name = re.sub("_entropy", "", program.__name__)
    # program_name = program.__name__
    for fi_cycle in range(cycle_start, cycle_end):
        # entropy_corr = 0
        fi_params = (fi_cycle, fi_index, num_bits)
        try:
            program(core_type, fi_params)
            if not Testbench.bench.result_is_correct(program_name):
                fi_result = 'target_meet'
                print("### TARGET MEET ###")
            else:
                fi_result = 'no_effect'
        except PCOutOfBoundException:
            fi_result = 'pc_out_of_bound'
            print("### PC OUT OF BOUND ###")
        except SegmentationFaultException:
            fi_result = 'seg_fault'
            print("### MEMORY INDEX ERROR ###")
        except InstructionAddressMisalignedException:
            fi_result = 'misaligned_access'
            print("### INSTRUCTION ADDRESS MISALIGNED ###")
        except IllegalInstructionException:
            fi_result = 'ill_inst'
            print("### INSTRUCTION MEMORY CORRUPTED ###")
        except Exception:
            fi_result = 'funct_violation'
            print("### PROCESSOR FUNCTIONING VIOLATED ###")
        finally:
            end_cycle = Simulator.globalSim.getCycles()
            # if not Testbench.bench.entropy_is_correct(program_name):
                # entropy_corr = 1
                # print("### ENTROPY CORRUPTED ###")
            # insert_result(program.__name__, fi_index, fi_cycle, num_bits, fi_result, end_cycle, entropy_corr)
            # insert_result(program.__name__, fi_index, fi_cycle, num_bits, fi_result, end_cycle)
            Simulator.globalSim.clear()

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

def run_bad_bit_test(settings):
    clear_table(settings["program"].__name__)
    for fault_type in ["flip", "set", "clear"]:
        for bit_index in range(0, 24):
            print(f"\nInjecting \'{fault_type}\' faults into bit {bit_index}")
            settings["fi_index"] = bit_index
            settings["fi_type"] = fault_type
            inject_faults(**settings)

def run_fi_test(settings):
    clear_table(settings["program"].__name__)

    bits = [i for i in range(31)]
    for bit_index in bits:
        num_bits_range = [i for i in range (1, (32 - bit_index)+1)]
        for num_bits in num_bits_range:
            print(f"\nInjecting {num_bits} fault(s) starting with bit {bit_index}")
            settings["fi_index"] = bit_index
            settings["num_bits"] = num_bits
            inject_faults(**settings)

if __name__ == "__main__":
    bench = Testbench()
    settings = {
        "program": programs.atoi,
        "core_type": "single",
        "cycle_start": 68,
        "cycle_end": 69,
        "fi_index": 8,
        "num_bits": 1
    }

    # run_fi_test(settings)
    inject_faults(**settings)
