"""Domain tests against known ground truth. Run with: python3 -m unittest discover tests"""
import unittest

from satoshi_tracker.domain.balance import RewardBalance, RewardStatus, reward_status
from satoshi_tracker.domain.bitcoin import (GENESIS_ADDRESS, format_btc, parse_btc, parse_extranonce,
                                            pubkey_to_address, script_address)
from satoshi_tracker.domain.block import Block
from satoshi_tracker.domain.patoshi import Confidence, classify, estimate_true_patoshi, matches_nonce_lsb

GENESIS_PUBKEY = ("04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c"
                  "384df7ba0b8d578a4c702b6bf11d5f")
BLOCK9_PUBKEY = ("0411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482ecad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b"
                 "8b64f9d4c03f999b8643f656b412a3")
# genesis coinbase scriptSig: <ffff001d> <04> "The Times 03/Jan/2009 ..."
GENESIS_COINBASE = "04ffff001d0104455468652054696d65732030332f4a616e2f32303039"


def block(height, extranonce, nonce=0):
    return Block(height, f"h{height}", "2009-01-01 00:00:00", nonce, extranonce, "", f"a{height}")


class BitcoinTest(unittest.TestCase):
    def test_genesis_address(self):
        self.assertEqual(pubkey_to_address(GENESIS_PUBKEY), GENESIS_ADDRESS)

    def test_block9_address(self):
        self.assertEqual(pubkey_to_address(BLOCK9_PUBKEY), "12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S")

    def test_p2pk_script_maps_to_address(self):
        self.assertEqual(script_address("41" + BLOCK9_PUBKEY + "ac", "p2pk"), "12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S")

    def test_extranonce(self):
        self.assertEqual(parse_extranonce(GENESIS_COINBASE), 4)
        self.assertIsNone(parse_extranonce("00"))

    def test_btc_round_trip(self):
        self.assertEqual(parse_btc("50.00002188"), 5_000_002_188)
        self.assertEqual(format_btc(5_000_002_188), "50.00002188")


class PatoshiTest(unittest.TestCase):
    def test_lsb_ranges(self):
        self.assertEqual(sum(matches_nonce_lsb(i) for i in range(256)), 50)
        self.assertTrue(matches_nonce_lsb(0) and matches_nonce_lsb(58))
        self.assertFalse(matches_nonce_lsb(10) or matches_nonce_lsb(59))

    def test_steep_line_is_high_isolated_point_is_low(self):
        steep = [block(h, 10 * h) for h in range(100, 140)]      # 10 ExtraNonce per block
        lone = [block(500, 3)]
        result = {c.block.height: c.confidence for c in classify(steep + lone)}
        self.assertEqual(result[120], Confidence.HIGH)
        self.assertEqual(result[500], Confidence.LOW)

    def test_shallow_line_is_not_high(self):
        shallow = [block(h, h // 4) for h in range(0, 200, 2)]  # 1 ExtraNonce per 8 blocks
        self.assertTrue(all(c.confidence == Confidence.LOW for c in classify(shallow)))

    def test_estimate_uses_negative_control(self):
        self.assertAlmostEqual(estimate_true_patoshi(54_317, 28_746), 22_539.45, places=2)


class BalanceTest(unittest.TestCase):
    def balance(self, status):
        return RewardBalance(9, "addr", "tx", 5_000_000_000, status, "", 44_000_000, "now")

    def test_spent_reward_excluded_from_total(self):
        self.assertEqual(self.balance(RewardStatus.SPENT).total_sats, 44_000_000)
        self.assertEqual(self.balance(RewardStatus.UNSPENT).total_sats, 5_044_000_000)

    def test_genesis_is_flagged(self):
        self.assertEqual(reward_status(0, spent=False), RewardStatus.GENESIS)
        self.assertEqual(reward_status(9, spent=True), RewardStatus.SPENT)


if __name__ == "__main__":
    unittest.main()
