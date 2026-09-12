"""Palettised textures, which are what makes real artwork fit in 4 MB."""

import unittest

import numpy as np
from PIL import Image

from ncc import palette


def gradient(width=32, height=32, alpha=255):
    data = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            data[y, x] = (x * 8 % 256, y * 8 % 256, (x + y) * 4 % 256, alpha)
    return Image.fromarray(data, 'RGBA')


class SwizzleTests(unittest.TestCase):
    def test_a_256_entry_table_swaps_bits_three_and_four(self):
        """The GS reads a CSM1 table in that order, and nothing else does.

        Getting it wrong recolours the picture in bands of eight, which looks
        like somebody else's palette rather than like a bug -- so it is worth
        an assertion rather than an eyeball.
        """
        entries = list(range(256))
        out = palette.clut_swizzle(entries)
        self.assertEqual(out[8], 16)
        self.assertEqual(out[16], 8)
        self.assertEqual(out[0], 0)
        self.assertEqual(out[7], 7)
        self.assertEqual(out[24], 24)

    def test_the_swizzle_is_its_own_inverse(self):
        entries = list(range(256))
        self.assertEqual(palette.clut_swizzle(palette.clut_swizzle(entries)),
                         entries)

    def test_a_16_entry_table_is_left_alone(self):
        entries = list(range(16))
        self.assertEqual(palette.clut_swizzle(entries), entries)


class QuantiseTests(unittest.TestCase):
    def test_four_bit_uses_at_most_sixteen_entries(self):
        indices, table = palette.quantise(gradient(), bits=4)
        self.assertLessEqual(int(indices.max()), 15)
        self.assertEqual(len(table), 16)

    def test_eight_bit_uses_at_most_256_entries(self):
        indices, table = palette.quantise(gradient(), bits=8)
        self.assertLessEqual(int(indices.max()), 255)
        self.assertEqual(len(table), 256)

    def test_an_image_with_no_transparency_gets_the_whole_table(self):
        """Spending index 0 on transparency that does not exist throws away a
        colour, and several real textures land on exactly 256."""
        image = Image.fromarray(
            np.random.RandomState(1).randint(0, 256, (16, 16, 4), dtype=np.uint8)
            | np.array([0, 0, 0, 255], dtype=np.uint8), 'RGBA')
        _, table = palette.quantise(image, bits=4, dither=False)
        self.assertNotEqual(table[0], (0, 0, 0, 0),
                            'index 0 was reserved for transparency that is not there')

    def test_transparent_pixels_become_index_zero(self):
        data = np.asarray(gradient()).copy()
        data[0:4, :, 3] = 0
        indices, table = palette.quantise(Image.fromarray(data, 'RGBA'), bits=4)
        self.assertTrue((indices[0:4, :] == 0).all())
        self.assertEqual(table[0], (0, 0, 0, 0))

    def test_a_flat_colour_survives_exactly(self):
        image = Image.new('RGBA', (8, 8), (200, 100, 50, 255))
        indices, table = palette.quantise(image, bits=4, dither=False)
        rebuilt = np.asarray(palette.to_image(indices, table))
        np.testing.assert_allclose(rebuilt[..., :3], 200 * (rebuilt[..., :3] // 200),
                                   atol=256)
        self.assertEqual(tuple(rebuilt[0, 0][:3]), (200, 100, 50))

    def test_eight_bit_is_lossless_when_the_source_has_few_enough_colours(self):
        """Which is the case for every texture on a model of this era, because
        they were palettised when the game shipped."""
        rng = np.random.RandomState(7)
        table = rng.randint(0, 256, (200, 3), dtype=np.uint8)
        picked = table[rng.randint(0, 200, (24, 24))]
        data = np.dstack([picked, np.full((24, 24, 1), 255, dtype=np.uint8)])
        image = Image.fromarray(data, 'RGBA')
        indices, entries = palette.quantise(image, bits=8, dither=False)
        rebuilt = np.asarray(palette.to_image(indices, entries))
        np.testing.assert_array_equal(rebuilt[..., :3], data[..., :3])


class PackingTests(unittest.TestCase):
    def test_four_bit_indices_pack_two_to_a_byte_low_nibble_first(self):
        raw = palette.pack(np.array([[1, 2, 3, 4]], dtype=np.uint8), 4)
        self.assertEqual(raw, bytes((0x21, 0x43)))

    def test_an_odd_count_is_padded_rather_than_truncated(self):
        raw = palette.pack(np.array([[1, 2, 3]], dtype=np.uint8), 4)
        self.assertEqual(raw, bytes((0x21, 0x03)))

    def test_eight_bit_indices_pass_through(self):
        raw = palette.pack(np.array([[9, 200]], dtype=np.uint8), 8)
        self.assertEqual(raw, bytes((9, 200)))

    def test_the_table_is_written_as_rgba_bytes(self):
        raw = palette.clut_bytes([(1, 2, 3, 0x80)] * 16, 4)
        self.assertEqual(len(raw), 64)
        self.assertEqual(raw[:4], bytes((1, 2, 3, 0x80)))


class CostTests(unittest.TestCase):
    def test_four_bit_is_a_fraction_of_the_cost_of_32_bit(self):
        from ncc import ps2budget
        full = ps2budget.cost(128, 128, 'PSMCT32')
        small = palette.cost(128, 128, 4)
        self.assertLess(small * 6, full)

    def test_the_colour_table_is_counted(self):
        """It lives in graphics memory too, and a hundred of them add up."""
        from ncc import ps2budget
        self.assertGreater(palette.cost(128, 128, 8),
                           ps2budget.cost(128, 128, 'PSMT8'))


if __name__ == '__main__':
    unittest.main()
