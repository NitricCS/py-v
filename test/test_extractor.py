import pytest
from pyv.simulator import Simulator
from pyv.extractor import Extractor, IFXT_t, XTIF_t, TXT_t

@pytest.fixture(scope="function")
def extractor():
    extractor = Extractor()
    extractor._init()
    return extractor

class TestEntropyExtractor():
    '''Entropy extractor module tests.
    Use an extractor fixture to verify entropy and signal outputs with given instruction inputs.
    Every test uses a newly instantiated extractor module.
    '''
    @pytest.mark.extraction
    def test_extractor(self, sim: Simulator, extractor: Extractor):
        '''Base functionality test.
        Input: arbitrary instruction
        Verifications:
            - entropy output value
            - high extraction active signal
            - low ready and flush signals
        '''
        # set input
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))
        sim.step()

        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert out.entropy == [61]
        assert not out.ready
        assert out.active
        assert not out.flush_bits
    
    @pytest.mark.extraction
    def test_extractor_stop(self, sim: Simulator, extractor: Extractor):
        '''Stop/signal processing test.
        Input: STOP instruction
        Verifications:
            - low extraction active signal
            - high ready signal
        '''
        # set input
        extractor.IFXT_i.write(IFXT_t(0xffffffff))
        sim.step()

        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert out.ready
        assert not out.active
    
    @pytest.mark.extraction
    def test_extractor_consecutive(self, sim: Simulator, extractor: Extractor):
        '''Entropy register fill test.
        Input: two consecutive instructions
        Verifications:
            - entropy output list value and length
            - low flush signal
        '''
        # set input
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
        sim.step()

        extractor.IFXT_i.write(IFXT_t(0xf8a42633))  # entropy = 60
        sim.step()

        # read output and verify
        out = extractor.XTIF_o.read()
        assert len(out.entropy) == 2
        assert out.entropy == [61, 60]
        assert not out.flush_bits
    
    @pytest.mark.extraction
    def test_extractor_mixed_instructions(self, sim: Simulator, extractor: Extractor):
        '''Instruction type distinguishment test.
        Input: consecutive instructions of different types
        Verifications:
            - entropy output list value and length
            - low flush signal
        '''
        # set input
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
        sim.step()

        extractor.IFXT_i.write(IFXT_t(0xf8a42637))  # not R type
        sim.step()

        extractor.IFXT_i.write(IFXT_t(0xf8a42633))  # entropy = 60
        sim.step()

        # read output and verify
        out = extractor.XTIF_o.read()
        assert len(out.entropy) == 2
        assert out.entropy == [61, 60]
        assert not out.flush_bits
    
    # flush signal
    @pytest.mark.extraction
    def test_extractor_flush_signal(self, sim: Simulator, extractor: Extractor):
        '''Flush signal high/low test
        Input: 16 consecutive instructions, then flush ready signal
        Verifications:
            - entropy output list value and length
            - flush signal set high, then low
        '''
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
        assert len(out.entropy) == 16
        assert out.entropy == [61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60, 61, 60]
        assert out.flush_bits

        # mimic flush ready signal
        extractor.TXT_i.write(TXT_t(True))
        # one more step
        extractor.IFXT_i.write(IFXT_t(0xfaa42633))  # entropy = 61
        sim.step()
        # read output and verify
        out: XTIF_t = extractor.XTIF_o.read()
        assert not out.flush_bits
        assert out.entropy == []