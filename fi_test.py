import sqlite3
from pyv.exceptions import IllegalInstructionException, InstructionAddressMisalignedException, PCOutOfBoundException, SegmentationFaultException
from pyv.simulator import Simulator
import programs
from matplotlib import pyplot as plt, numpy as np
from datetime import datetime


class Testbench():
    def __init__(self):
        self.entropy_result = []
        self.program_result = []
        self.expected_results = {
            "memset": ['0xff', '0x4', '0x0', '0x0'],
            "strcpy": (['0x53', '0x61', '0x6d', '0x70', '0x6c', '0x65', '0x0', '0x0'], ['0x63', '0x6f', '0x70', '0x69', '0x65', '0x64', '0x0', '0x0']),
            "fibonacci": ['0x37', '0x0', '0x0', '0x0'],
            "atoi": ['0xd2', '0x4', '0x0', '0x0']
        }


expected_results = {
    "memset": ['0xff', '0x4', '0x0', '0x0'],
    "strcpy": (['0x53', '0x61', '0x6d', '0x70', '0x6c', '0x65', '0x0', '0x0'], ['0x63', '0x6f', '0x70', '0x69', '0x65', '0x64', '0x0', '0x0']),
    "fibonacci": ['0x37', '0x0', '0x0', '0x0'],
    "atoi": ['0xd2', '0x4', '0x0', '0x0']
}

conn = sqlite3.connect('data/fi.db')
c = conn.cursor()

def insert_result(program_name, bit_index, cycle, fi_type, fi_result):
    c.execute(f"INSERT INTO {program_name} (program_name, fi_bit_index, fi_cycle, fi_type, fi_result) VALUES (\'{program_name}\', {bit_index}, {cycle}, \'{fi_type}\', \'{fi_result}\')")
    conn.commit()

def clear_table(program_name):
    c.execute(f"DELETE FROM {program_name}")
    conn.commit()

def inject_faults(program,
                  core_type: str,
                  cycle_start: int,
                  cycle_end: int,
                  fi_index: int,
                  num_bits: int,
                  fi_type: str) -> list:
    expected_result = expected_results[program.__name__]
    for fi_cycle in range(cycle_start, cycle_end):
        fi_params = (fi_cycle, fi_index, num_bits, fi_type)
        try:
            res = program(core_type, fi_params)
            if res != expected_result:
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
            insert_result(program.__name__, fi_index, fi_cycle, fi_type, fi_result)
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
        bits = [i for i in range(4, 31) if i not in [6, 12, 14]]
        for bit_index in bits:
            print(f"\nInjecting \'{fault_type}\' faults into bit {bit_index}")
            settings["fi_index"] = bit_index
            settings["fi_type"] = fault_type
            inject_faults(**settings)

def run_fi_test(settings):
    clear_table(settings["program"].__name__)

    bits = [i for i in range(4, 31) if i not in [6, 12, 14]]
    for bit_index in bits:
        print(f"\nInjecting \'{settings["fault_type"]}\' faults into bit {bit_index}")
        settings["fi_index"] = bit_index
        settings["fi_type"] = settings["fault_type"]
        inject_faults(**settings)

if __name__ == "__main__":
    settings = {
        "program": programs.memset,
        "core_type": "single_entropy",
        "cycle_start": 1,
        "cycle_end": 106,
        "fi_index": 0,
        "num_bits": 1,
        "fi_type": "flip"
    }

    fi_results = run_bad_bit_test(settings)
