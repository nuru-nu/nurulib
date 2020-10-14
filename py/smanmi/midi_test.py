import unittest

from . import midi


class TestCommand(unittest.TestCase):

    def test_parse_note(self):
        command = midi.Command('1: C#2 on')
        self.assertEqual(command.kind, 'note')
        self.assertEqual(command.name, '1: C#2')
        self.assertEqual(command.value, 'on')

    def test_parse_controller(self):
        command = midi.Command('3: X2=123')
        self.assertEqual(command.kind, 'controller')
        self.assertEqual(command.name, '3: X2')
        self.assertEqual(command.value, 123)

    def test_parse_fails(self):
        with self.assertRaises(AssertionError):
            midi.Command('0: C#2 on')
        with self.assertRaises(AssertionError):
            midi.Command('1: C#2 of')
        with self.assertRaises(ValueError):
            midi.Command('')

    def test_bytes_reversible(self):
        s = '1: C#2 on'
        command = midi.Command.from_bytes(midi.Command(s).bytes)
        self.assertEqual(s, str(command))
        s = '16: X2=12'
        command = midi.Command.from_bytes(midi.Command(s).bytes)
        self.assertEqual(s, str(command))
