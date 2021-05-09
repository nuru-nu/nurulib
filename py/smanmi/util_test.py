import unittest

from . import util


class TestUtil(unittest.TestCase):

    def test_get(self):
        d = dict(a=dict(b='c'), d=1)
        self.assertEqual(util.get(d, 'a.b'), 'c')
        self.assertEqual(util.get(d, 'd'), 1)

    def test_update(self):
        d = dict(a=dict(b='c'), d=1)
        util.update(d, dict(d=2))
        self.assertEqual(d, dict(a=dict(b='c'), d=2))
        util.update(d, {'a.b': 'x'})
        self.assertEqual(d, dict(a=dict(b='x'), d=2))
        d = dict(a=dict(t=[0]))
        util.update(d, {'a.t': [1]}, transients=['a.t'])
        self.assertEqual(d, dict(a=dict(t=[0, 1])))