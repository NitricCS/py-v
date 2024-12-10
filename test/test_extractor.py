import pytest
from pyv.simulator import Simulator
from pyv.csr import CSRUnit
from pyv.reg import Regfile
from pyv.extractor import Extractor, IFXT_t, XTIF_t, TXT_t

@pytest.fixture(scope="function")
def extractor():
    regf = Regfile()
    csr = CSRUnit()
    extractor = Extractor(regf, csr)
    extractor._init()
    return extractor

class TestEntropyExtractor():
    # initialization and base functionality
    @pytest.mark.current
    def test_extractor(self, sim: Simulator, extractor: Extractor):
        # set input
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))
        sim.step()

        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert out.entropy_bits == [61]
        assert not out.ready
        assert out.active
        assert not out.flush_bits
    
    # active/ready functionality
    def test_extractor_stop(self, sim: Simulator, extractor: Extractor):
        # set input
        extractor.IFXT_i.write(IFXT_t(0xffffffff))
        sim.step()

        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert out.ready
        assert not out.active
    
    # enrtopy list forming
    def test_extractor_consecutive(self, sim: Simulator, extractor: Extractor):
        # set input
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
        sim.step()

        extractor.IFXT_i.write(IFXT_t(0xf8a42633))  # entropy = 60
        sim.step()

        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert len(out.entropy_bits) == 2
        assert out.entropy_bits == [61, 60]
        assert not out.flush_bits
    
    # flush signal
    def test_extractor_flush_signal(self, sim: Simulator, extractor: Extractor):
        extractor.TXT_i.write(TXT_t(False))
        # 16 cycles
        for _ in range(0, 8):
            # set input 1 and do a cycle
            extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
            sim.step()
            # set input 2 and do a cycle
            extractor.IFXT_i.write(IFXT_t(0xf8a42633))  # entropy = 60
            sim.step()

        # validate output
        out: XTIF_t = extractor.XTIF_o.read()
        assert len(out.entropy_bits) == 16
        assert out.entropy_bits == [61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60]
        assert out.flush_bits

        # mimic flush ready signal
        extractor.TXT_i.write(TXT_t(True))
        # one more step
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
        sim.step()
        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert not out.flush_bits